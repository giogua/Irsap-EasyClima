"""The Irsap CLIMA integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant

from .api import ClimaClient
from .const import CONF_UNIT, DEFAULT_PORT, DEFAULT_UNIT
from .coordinator import IrsapClimaConfigEntry, IrsapClimaCoordinator
from .modbus import ModbusTcpClient

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: IrsapClimaConfigEntry) -> bool:
    """Set up a CLIMA unit from a config entry."""
    modbus = ModbusTcpClient(
        entry.data[CONF_HOST], entry.data.get(CONF_PORT, DEFAULT_PORT)
    )
    client = ClimaClient(modbus, entry.data.get(CONF_UNIT, DEFAULT_UNIT))
    coordinator = IrsapClimaCoordinator(hass, entry, client)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await client.async_close()
        raise
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IrsapClimaConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.client.async_close()
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant, entry: IrsapClimaConfigEntry
) -> None:
    """Reload when options change."""
    await hass.config_entries.async_reload(entry.entry_id)
