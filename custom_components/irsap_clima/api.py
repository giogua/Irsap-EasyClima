"""Client for Irsap CLIMA units (Innova INN-FR-B32 controller board).

Register map from Innova document N273025C ("Modbus RTU kit bridge"),
which matches the parameters of the Irsap CLIMA board (MVV1..MVV5, LLO/LHI,
ASCII/RTU jumper, PRG/season values shown by the EasyClima multizone panel).

Values marked x0.1 are tenths of a degree.  Register 201 is a bit field: only
the bits this client is meant to change are touched (read-modify-write), the
reserved bits 8-15 are always written back unchanged.

This module has no Home Assistant dependency so it can be tested standalone.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .modbus import ModbusExceptionResponse, ModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Read-only
REG_AIR_TEMP = 0  # T1, x0.1 °C
REG_WATER_TEMP_H2 = 1  # T2, x0.1 °C
REG_WATER_TEMP_H4 = 2  # T3, x0.1 °C (4-pipe units only)
REG_SETPOINT_REAL = 8  # x0.1 °C, effective set point
REG_OUT = 9  # relay outputs (bit field)
REG_MOTOR_SPEED = 15  # requested fan speed, rpm
REG_STAT = 104  # status (bit field)
REG_ALARMS = 105  # alarms (bit field)
# Read/write
REG_PRG = 201  # program / lock / standby (bit field)
REG_SP_MIN = 202  # x0.1 °C
REG_SP_MAX = 203  # x0.1 °C
REG_FAN_HOURS = 222  # fan working hours
REG_SETPOINT = 231  # x0.1 °C, absolute set point
REG_SEASON = 233  # 0 auto, 3 winter (heating), 5 summer (cooling)

POLLED_REGISTERS = (
    REG_AIR_TEMP,
    REG_WATER_TEMP_H2,
    REG_WATER_TEMP_H4,
    REG_SETPOINT_REAL,
    REG_OUT,
    REG_MOTOR_SPEED,
    REG_STAT,
    REG_ALARMS,
    REG_PRG,
    REG_SP_MIN,
    REG_SP_MAX,
    REG_FAN_HOURS,
    REG_SETPOINT,
    REG_SEASON,
)

# PRG (201)
PRG_MASK = 0x0003
PRG_LOCK = 1 << 4
PRG_STANDBY = 1 << 7
PROGRAMS = {0: "auto", 1: "silent", 2: "night", 3: "max"}

# Season (233)
SEASON_AUTO = 0
SEASON_WINTER = 3
SEASON_SUMMER = 5

# OUT (9)
OUT_EV1 = 1 << 0
OUT_EV2 = 1 << 1
OUT_CHILLER = 1 << 2
OUT_BOILER = 1 << 3

# STAT (104)
STAT_COOLING = 1 << 0
STAT_HEATING = 1 << 1
STAT_FAN_STOP_H2 = 1 << 4
STAT_FAN_STOP_H4 = 1 << 5
STAT_BAD_WATER = 1 << 6
STAT_ANTIFREEZE = 1 << 8
STAT_ALARM = 1 << 9
STAT_STANDBY = 1 << 11
STAT_COM_ERROR = 1 << 12
STAT_H2_ABSENT = 1 << 13
STAT_H4_ABSENT = 1 << 14

# ALR_STAT (105)
ALARM_BITS = {
    0: "communication",
    1: "air_probe",
    2: "h4_probe",
    3: "harmful_water",
    4: "h2_probe",
    5: "h4_water_not_suitable",
    6: "heater_high_temperature",
    7: "motor",
    8: "grid_contact_open",
    9: "h2_water_not_suitable",
    10: "filter",
    11: "air_probe_conflict",
}
ALARM_FILTER = 1 << 10


class ClimaError(Exception):
    """Generic error."""


def _signed(value: int) -> int:
    return value - 0x10000 if value & 0x8000 else value


def _probe(value: float | None) -> float | None:
    """Disconnected probes read as large negative values (e.g. -51.0)."""
    if value is None or value < -40 or value > 120:
        return None
    return value


@dataclass
class ClimaData:
    """Snapshot of the unit."""

    raw: dict[int, int] = field(default_factory=dict)

    def _temp(self, reg: int) -> float | None:
        if reg not in self.raw:
            return None
        return round(_signed(self.raw[reg]) / 10, 1)

    def _flag(self, reg: int, bit: int) -> bool | None:
        if reg not in self.raw:
            return None
        return bool(self.raw[reg] & bit)

    @property
    def air_temperature(self) -> float | None:
        """Room/return air temperature."""
        if self._flag(REG_ALARMS, 1 << 1):
            return None  # air probe alarm
        return _probe(self._temp(REG_AIR_TEMP))

    @property
    def water_temperature(self) -> float | None:
        """Water temperature on probe H2 (None if the probe is absent)."""
        if self._flag(REG_STAT, STAT_H2_ABSENT):
            return None
        return _probe(self._temp(REG_WATER_TEMP_H2))

    @property
    def water_temperature_h4(self) -> float | None:
        """Water temperature on probe H4 (4-pipe units)."""
        if self._flag(REG_STAT, STAT_H4_ABSENT):
            return None
        return _probe(self._temp(REG_WATER_TEMP_H4))

    @property
    def setpoint(self) -> float | None:
        """Configured set point."""
        return self._temp(REG_SETPOINT)

    @property
    def setpoint_effective(self) -> float | None:
        """Set point actually used by the regulation (None in standby)."""
        if self.is_on is False:
            return None
        return self._temp(REG_SETPOINT_REAL)

    @property
    def setpoint_min(self) -> float | None:
        """Lower set point limit."""
        return self._temp(REG_SP_MIN)

    @property
    def setpoint_max(self) -> float | None:
        """Upper set point limit."""
        return self._temp(REG_SP_MAX)

    @property
    def is_on(self) -> bool | None:
        """Unit not in standby."""
        standby = self._flag(REG_PRG, PRG_STANDBY)
        return None if standby is None else not standby

    @property
    def program(self) -> str | None:
        """Fan program: auto / silent / night / max."""
        if REG_PRG not in self.raw:
            return None
        return PROGRAMS[self.raw[REG_PRG] & PRG_MASK]

    @property
    def keyboard_locked(self) -> bool | None:
        """Local keyboard locked."""
        return self._flag(REG_PRG, PRG_LOCK)

    @property
    def season(self) -> int | None:
        """Raw season value (0 auto, 3 winter, 5 summer)."""
        return self.raw.get(REG_SEASON)

    @property
    def heating_mode(self) -> bool | None:
        """Active mode is heating (resolves the automatic season)."""
        return self._flag(REG_STAT, STAT_HEATING)

    @property
    def cooling_mode(self) -> bool | None:
        """Active mode is cooling."""
        return self._flag(REG_STAT, STAT_COOLING)

    @property
    def fan_speed(self) -> int | None:
        """Requested fan speed (rpm)."""
        return self.raw.get(REG_MOTOR_SPEED)

    @property
    def fan_hours(self) -> int | None:
        """Fan working hours."""
        return self.raw.get(REG_FAN_HOURS)

    @property
    def boiler_request(self) -> bool | None:
        """Heat request output (BOILER contact)."""
        return self._flag(REG_OUT, OUT_BOILER)

    @property
    def chiller_request(self) -> bool | None:
        """Cooling request output (CHILLER contact)."""
        return self._flag(REG_OUT, OUT_CHILLER)

    @property
    def water_valve(self) -> bool | None:
        """Water valve EV1 open."""
        return self._flag(REG_OUT, OUT_EV1)

    @property
    def alarm(self) -> bool | None:
        """At least one alarm."""
        stat = self._flag(REG_STAT, STAT_ALARM)
        alarms = self.raw.get(REG_ALARMS)
        if stat is None and alarms is None:
            return None
        return bool(stat) or bool(alarms)

    @property
    def alarms(self) -> list[str]:
        """Active alarm codes."""
        value = self.raw.get(REG_ALARMS, 0)
        return [name for bit, name in ALARM_BITS.items() if value & (1 << bit)]

    @property
    def filter_dirty(self) -> bool | None:
        """Maintenance required (dirty filter)."""
        return self._flag(REG_ALARMS, ALARM_FILTER)

    @property
    def antifreeze(self) -> bool | None:
        """Antifreeze protection active."""
        return self._flag(REG_STAT, STAT_ANTIFREEZE)

    @property
    def water_not_suitable(self) -> bool | None:
        """Fan stopped because the water temperature is not suitable."""
        if REG_STAT not in self.raw:
            return None
        return bool(
            self.raw[REG_STAT] & (STAT_FAN_STOP_H2 | STAT_FAN_STOP_H4 | STAT_BAD_WATER)
        )


class ClimaClient:
    """High level access to one unit."""

    def __init__(self, modbus: ModbusTcpClient, unit: int = 1) -> None:
        self.modbus = modbus
        self.unit = unit
        self._unsupported: set[int] = set()

    async def async_close(self) -> None:
        """Close the connection."""
        await self.modbus.close()

    async def async_validate(self) -> int:
        """Read the air temperature register; raises if unreachable."""
        return (await self.modbus.read_holding(self.unit, REG_AIR_TEMP))[0]

    async def async_get_data(self) -> ClimaData:
        """Read all polled registers (unsupported ones are skipped)."""
        data = ClimaData()
        for reg in POLLED_REGISTERS:
            if reg in self._unsupported:
                continue
            try:
                data.raw[reg] = (await self.modbus.read_holding(self.unit, reg))[0]
            except ModbusExceptionResponse as err:
                if err.code == 2:
                    _LOGGER.info("Register %s not supported by the unit", reg)
                    self._unsupported.add(reg)
                    continue
                raise
        return data

    async def _update_prg(
        self, set_bits: int = 0, clear_bits: int = 0, program: int | None = None
    ) -> int:
        current = (await self.modbus.read_holding(self.unit, REG_PRG))[0]
        new = (current | set_bits) & ~clear_bits
        if program is not None:
            new = (new & ~PRG_MASK) | (program & PRG_MASK)
        new &= 0xFFFF
        if new != current:
            await self.modbus.write_register(self.unit, REG_PRG, new)
        return new

    async def async_set_power(self, on: bool) -> None:
        """Switch the unit on (normal operation) or to standby."""
        if on:
            await self._update_prg(clear_bits=PRG_STANDBY)
        else:
            await self._update_prg(set_bits=PRG_STANDBY)

    async def async_set_program(self, program: str) -> None:
        """Set the fan program (auto / silent / night / max)."""
        value = next((k for k, v in PROGRAMS.items() if v == program), None)
        if value is None:
            raise ValueError(f"Unknown program {program!r}")
        await self._update_prg(program=value)

    async def async_set_keyboard_lock(self, locked: bool) -> None:
        """Lock/unlock the local keyboard."""
        if locked:
            await self._update_prg(set_bits=PRG_LOCK)
        else:
            await self._update_prg(clear_bits=PRG_LOCK)

    async def async_set_season(self, season: int) -> None:
        """Set the season (0 auto, 3 winter/heating, 5 summer/cooling)."""
        if season not in (SEASON_AUTO, SEASON_WINTER, SEASON_SUMMER):
            raise ValueError(f"Invalid season {season}")
        await self.modbus.write_register(self.unit, REG_SEASON, season)

    async def async_set_setpoint(self, value: float) -> None:
        """Set the absolute set point (°C), within the unit limits."""
        raw = round(value * 10)
        limits = await self.modbus.read_holding(self.unit, REG_SP_MIN, 1)
        low = limits[0]
        high = (await self.modbus.read_holding(self.unit, REG_SP_MAX, 1))[0]
        if not low <= raw <= high:
            raise ClimaError(
                f"Set point {value} outside the unit limits {low / 10}-{high / 10} °C"
            )
        await self.modbus.write_register(self.unit, REG_SETPOINT, raw)
