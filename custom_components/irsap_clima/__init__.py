"""The Irsap CLIMA integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.typing import ConfigType

from .api import ClimaClient
from .const import (
    CONF_FRAMING,
    CONF_SCAN_INTERVAL,
    CONF_UNIT,
    DEFAULT_FRAMING,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT,
    DOMAIN,
)
from .coordinator import IrsapClimaConfigEntry, IrsapClimaCoordinator
from .modbus import ModbusTcpClient
from .services import async_setup_services

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the services."""
    async_setup_services(hass)
    return True


def _migrate_registry(hass: HomeAssistant, entry: IrsapClimaConfigEntry) -> None:
    """Key device and entities on the entry id instead of the gateway address.

    Up to 0.3.2 they were keyed on "host:port:unit", so changing the gateway
    address created a second device.  The oldest registry entries (those
    holding the history) are kept and re-keyed, newer duplicates are removed.
    """
    new_uid = entry.entry_id
    ent_reg = er.async_get(hass)
    # 0.3.0-0.3.3: manual supervisor fan speed, now regulated automatically
    for ent in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if ent.domain == "number" and ent.unique_id.endswith("_supervisor_fan"):
            ent_reg.async_remove(ent.entity_id)
    entities = sorted(
        er.async_entries_for_config_entry(ent_reg, entry.entry_id),
        key=lambda e: e.created_at,
    )
    taken = {e.unique_id for e in entities}
    for ent in entities:
        if ent.unique_id.startswith(f"{new_uid}_"):
            continue
        key = ent.unique_id.split("_", 1)[1] if "_" in ent.unique_id else None
        target = f"{new_uid}_{key}"
        if key is None:
            continue
        if target in taken:
            ent_reg.async_remove(ent.entity_id)
            continue
        ent_reg.async_update_entity(ent.entity_id, new_unique_id=target)
        taken.add(target)

    dev_reg = dr.async_get(hass)
    devices = sorted(
        dr.async_entries_for_config_entry(dev_reg, entry.entry_id),
        key=lambda d: d.created_at,
    )
    keep = next((d for d in devices if (DOMAIN, new_uid) in d.identifiers), None)
    if keep is None and devices:
        keep = devices[0]
        dev_reg.async_update_device(keep.id, new_identifiers={(DOMAIN, new_uid)})
    for device in devices:
        if keep is not None and device.id != keep.id:
            for ent in er.async_entries_for_device(
                ent_reg, device.id, include_disabled_entities=True
            ):
                ent_reg.async_update_entity(ent.entity_id, device_id=keep.id)
            dev_reg.async_remove_device(device.id)


async def async_setup_entry(hass: HomeAssistant, entry: IrsapClimaConfigEntry) -> bool:
    """Set up a CLIMA unit from a config entry."""
    _migrate_registry(hass, entry)
    modbus = ModbusTcpClient(
        entry.data[CONF_HOST],
        entry.data.get(CONF_PORT, DEFAULT_PORT),
        framing=entry.data.get(CONF_FRAMING, DEFAULT_FRAMING),
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
    """Apply new options without reconnecting (fan speeds are read live)."""
    coordinator = entry.runtime_data
    coordinator.update_interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )
    await coordinator.async_request_refresh()
