"""Climate entity: the whole unit as a thermostat."""

from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import PROGRAMS, SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER
from .coordinator import IrsapClimaConfigEntry, IrsapClimaCoordinator
from .entity import IrsapClimaEntity

SEASON_TO_HVAC = {
    SEASON_WINTER: HVACMode.HEAT,
    SEASON_SUMMER: HVACMode.COOL,
    SEASON_AUTO: HVACMode.HEAT_COOL,
}
HVAC_TO_SEASON = {v: k for k, v in SEASON_TO_HVAC.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapClimaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the climate entity."""
    async_add_entities([IrsapClimaThermostat(entry.runtime_data)])


class IrsapClimaThermostat(IrsapClimaEntity, ClimateEntity):
    """On/off, season, set point and fan program of the unit."""

    _attr_name = None  # the device name
    _attr_translation_key = "clima"
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_target_temperature_step = 0.5
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.HEAT_COOL]
    _attr_fan_modes = list(PROGRAMS.values())
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, coordinator: IrsapClimaCoordinator) -> None:
        super().__init__(coordinator, "climate")

    @property
    def current_temperature(self) -> float | None:
        """Air temperature."""
        return self.coordinator.data.air_temperature

    @property
    def target_temperature(self) -> float | None:
        """Set point."""
        return self.coordinator.data.setpoint

    @property
    def min_temp(self) -> float:
        """Lower limit configured on the unit."""
        return self.coordinator.data.setpoint_min or 16.0

    @property
    def max_temp(self) -> float:
        """Upper limit configured on the unit."""
        return self.coordinator.data.setpoint_max or 28.0

    @property
    def hvac_mode(self) -> HVACMode | None:
        """Off, or the configured season."""
        data = self.coordinator.data
        if data.is_on is None:
            return None
        if not data.is_on:
            return HVACMode.OFF
        return SEASON_TO_HVAC.get(data.season)

    @property
    def hvac_action(self) -> HVACAction | None:
        """What the unit is doing right now."""
        data = self.coordinator.data
        if data.is_on is None:
            return None
        if not data.is_on or data.unit_standby:
            return HVACAction.OFF
        if not data.fan_speed:
            return HVACAction.IDLE
        if data.heating_mode:
            return HVACAction.HEATING
        if data.cooling_mode:
            return HVACAction.COOLING
        return HVACAction.FAN

    @property
    def fan_mode(self) -> str | None:
        """Fan program."""
        return self.coordinator.data.program

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Effective set point (may differ from the configured one)."""
        data = self.coordinator.data
        return {
            "effective_setpoint": data.setpoint_effective,
            "unit_standby": data.unit_standby,
            "forced_off": data.forced_off,
            "fan_target": data.supervisor_fan,
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Switch off, or select the season and switch on."""
        await self._async_command(self._apply_hvac_mode, hvac_mode)

    async def _apply_hvac_mode(self, hvac_mode: HVACMode) -> None:
        client = self.coordinator.client
        if hvac_mode == HVACMode.OFF:
            await client.async_set_power(False)
            return
        season = HVAC_TO_SEASON[hvac_mode]
        if self.coordinator.data.season != season:
            await client.async_set_season(season)
        await client.async_set_power(True)

    async def async_turn_on(self) -> None:
        """Switch on keeping the current season."""
        await self._async_command(self.coordinator.client.async_set_power, True)

    async def async_turn_off(self) -> None:
        """Standby."""
        await self._async_command(self.coordinator.client.async_set_power, False)

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the set point (and optionally the mode)."""
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            await self._apply_hvac_mode(mode)
        if (temp := kwargs.get(ATTR_TEMPERATURE)) is not None:
            await self._async_command(self.coordinator.client.async_set_setpoint, temp)
        else:
            await self.coordinator.async_refresh()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set the fan program; the next refresh applies the matching speed."""
        await self._async_command(self.coordinator.client.async_set_program, fan_mode)
