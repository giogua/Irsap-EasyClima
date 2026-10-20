"""Base entity for the Irsap CLIMA integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import ClimaError
from .const import DEFAULT_MODEL, DOMAIN, MANUFACTURER
from .coordinator import IrsapClimaCoordinator
from .modbus import ModbusError


class IrsapClimaEntity(CoordinatorEntity[IrsapClimaCoordinator]):
    """All entities of a unit belong to the same device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IrsapClimaCoordinator, key: str) -> None:
        super().__init__(coordinator)
        entry = coordinator.config_entry
        uid = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{uid}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, uid)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=DEFAULT_MODEL,
        )

    async def _async_command(
        self, func: Callable[..., Awaitable[Any]], *args: Any
    ) -> None:
        """Run a command, translate errors and refresh the state."""
        try:
            await func(*args)
        except (ModbusError, ClimaError, ValueError) as err:
            raise HomeAssistantError(f"CLIMA command failed: {err}") from err
        await self.coordinator.async_refresh()
