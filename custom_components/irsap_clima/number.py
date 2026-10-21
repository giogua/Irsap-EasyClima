"""Supervisor fan speed (registers 267/268), as written by the EasyClima panel."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IrsapClimaConfigEntry, IrsapClimaCoordinator
from .entity import IrsapClimaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapClimaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up number entities."""
    async_add_entities([IrsapClimaSupervisorFan(entry.runtime_data)])


class IrsapClimaSupervisorFan(IrsapClimaEntity, NumberEntity):
    """Fan speed % commanded by the supervisor (experimental)."""

    _attr_translation_key = "supervisor_fan"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrsapClimaCoordinator) -> None:
        super().__init__(coordinator, "supervisor_fan")

    @property
    def native_value(self) -> float | None:
        """Current value."""
        return self.coordinator.data.supervisor_fan

    async def async_set_native_value(self, value: float) -> None:
        """Write 267 and 268."""
        await self._async_command(
            self.coordinator.client.async_set_supervisor_fan, int(value)
        )
