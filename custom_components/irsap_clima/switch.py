"""Switch: lock of the unit keyboard (useful when Home Assistant is in charge)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import IrsapClimaConfigEntry, IrsapClimaCoordinator
from .entity import IrsapClimaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapClimaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up switches."""
    async_add_entities([IrsapClimaKeyboardLock(entry.runtime_data)])


class IrsapClimaKeyboardLock(IrsapClimaEntity, SwitchEntity):
    """Local keyboard lock (PRG bit 4)."""

    _attr_translation_key = "keyboard_lock"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator: IrsapClimaCoordinator) -> None:
        super().__init__(coordinator, "keyboard_lock")

    @property
    def is_on(self) -> bool | None:
        """Keyboard locked."""
        return self.coordinator.data.keyboard_locked

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Lock."""
        await self._async_command(self.coordinator.client.async_set_keyboard_lock, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Unlock."""
        await self._async_command(
            self.coordinator.client.async_set_keyboard_lock, False
        )
