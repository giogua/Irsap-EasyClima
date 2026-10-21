"""Fan speed regulation.

The CLIMA board decides *when* the fan runs (thermal demand on the AIR probe,
periodic air sampling), while the supervisor decides *how fast* it runs during
demand through registers 267/268 (percent).  The EasyClima multizone
controller does the same: it keeps writing 267/268 while the units run.

Fan modes are the native PRG programs (auto / silent / night / max), stored
on the unit itself (register 201) so they survive a Home Assistant restart.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .api import SEASON_SUMMER, SEASON_WINTER, ClimaData
from .const import (
    CONF_FAN_AUTO_BAND,
    CONF_FAN_AUTO_MAX,
    CONF_FAN_AUTO_MIN,
    CONF_FAN_MAX,
    CONF_FAN_NIGHT,
    CONF_FAN_SILENT,
    DEFAULT_FAN_AUTO_BAND,
    DEFAULT_FAN_AUTO_MAX,
    DEFAULT_FAN_AUTO_MIN,
    DEFAULT_FAN_MAX,
    DEFAULT_FAN_NIGHT,
    DEFAULT_FAN_SILENT,
    FAN_OFF,
)

FAN_STEP = 5  # max change per poll in auto mode, %
FAN_DEADBAND = 2  # do not rewrite for smaller differences, %


@dataclass(frozen=True)
class FanSettings:
    """User settings (config entry options)."""

    auto_min: int = DEFAULT_FAN_AUTO_MIN
    auto_max: int = DEFAULT_FAN_AUTO_MAX
    auto_band: float = DEFAULT_FAN_AUTO_BAND
    silent: int = DEFAULT_FAN_SILENT
    night: int = DEFAULT_FAN_NIGHT
    max: int = DEFAULT_FAN_MAX

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> FanSettings:
        """Read the settings from the config entry options."""
        low = int(options.get(CONF_FAN_AUTO_MIN, DEFAULT_FAN_AUTO_MIN))
        high = int(options.get(CONF_FAN_AUTO_MAX, DEFAULT_FAN_AUTO_MAX))
        return cls(
            auto_min=min(low, high),
            auto_max=max(low, high),
            auto_band=max(
                0.5, float(options.get(CONF_FAN_AUTO_BAND, DEFAULT_FAN_AUTO_BAND))
            ),
            silent=int(options.get(CONF_FAN_SILENT, DEFAULT_FAN_SILENT)),
            night=int(options.get(CONF_FAN_NIGHT, DEFAULT_FAN_NIGHT)),
            max=int(options.get(CONF_FAN_MAX, DEFAULT_FAN_MAX)),
        )


def demand(data: ClimaData) -> float:
    """How far the room is from the set point, in the direction to act (K, >= 0)."""
    air, setpoint = data.air_temperature, data.setpoint_effective or data.setpoint
    if air is None or setpoint is None:
        return 0.0
    if data.cooling_mode or (not data.heating_mode and data.season == SEASON_SUMMER):
        return max(0.0, air - setpoint)
    if data.heating_mode or data.season == SEASON_WINTER:
        return max(0.0, setpoint - air)
    return 0.0  # automatic season and no active mode yet


def fan_target(data: ClimaData, settings: FanSettings) -> int:
    """Fan speed % the supervisor should command now."""
    if not data.is_on:
        return FAN_OFF
    program = data.program
    if program == "silent":
        return settings.silent
    if program == "night":
        return settings.night
    if program == "max":
        return settings.max
    # auto: proportional to the distance from the set point, ramped
    ratio = min(1.0, demand(data) / settings.auto_band)
    target = round(settings.auto_min + (settings.auto_max - settings.auto_min) * ratio)
    current = data.supervisor_fan
    if current is None or not settings.auto_min <= current <= settings.auto_max:
        return target  # first run, or coming from a fixed program
    return max(current - FAN_STEP, min(current + FAN_STEP, target))


def needs_write(data: ClimaData, target: int, settings: FanSettings) -> bool:
    """Whether 267/268 must be rewritten to reach the target."""
    current = data.supervisor_fan
    other = data.raw.get(268)
    if current is None or (other is not None and other != current):
        return True
    if current == target:
        return False
    if not data.is_on or data.program != "auto":
        return True  # fixed speeds are applied exactly
    # auto: skip tiny adjustments, but always reach the limits of the range
    return abs(current - target) >= FAN_DEADBAND or target in (
        settings.auto_min,
        settings.auto_max,
    )
