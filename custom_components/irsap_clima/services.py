"""Diagnostic services: raw Modbus register access.

Meant for troubleshooting and for mapping undocumented registers.  Writing
the wrong register can change the unit configuration, so every write is
logged as a warning.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN
from .coordinator import IrsapClimaConfigEntry
from .modbus import ModbusError

_LOGGER = logging.getLogger(__name__)

ATTR_CONFIG_ENTRY = "config_entry_id"
ATTR_ADDRESS = "address"
ATTR_VALUE = "value"
ATTR_COUNT = "count"

_ENTRY = vol.Optional(ATTR_CONFIG_ENTRY)

READ_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Required(ATTR_ADDRESS): vol.All(vol.Coerce(int), vol.Range(0, 65535)),
        vol.Optional(ATTR_COUNT, default=1): vol.All(vol.Coerce(int), vol.Range(1, 32)),
    }
)
WRITE_SCHEMA = vol.Schema(
    {
        _ENTRY: cv.string,
        vol.Required(ATTR_ADDRESS): vol.All(vol.Coerce(int), vol.Range(0, 65535)),
        vol.Required(ATTR_VALUE): vol.All(vol.Coerce(int), vol.Range(0, 65535)),
    }
)


def _entry(hass: HomeAssistant, call: ServiceCall) -> IrsapClimaConfigEntry:
    entries = [
        e
        for e in hass.config_entries.async_entries(DOMAIN)
        if e.state is ConfigEntryState.LOADED
    ]
    wanted = call.data.get(ATTR_CONFIG_ENTRY)
    if wanted:
        entries = [e for e in entries if e.entry_id == wanted]
    if len(entries) != 1:
        raise ServiceValidationError(
            "Specify the config_entry_id of a loaded CLIMA unit"
        )
    return entries[0]


async def _read(call: ServiceCall) -> ServiceResponse:
    coordinator = _entry(call.hass, call).runtime_data
    client = coordinator.client
    address, count = call.data[ATTR_ADDRESS], call.data[ATTR_COUNT]
    try:
        values = await client.modbus.read_holding(client.unit, address, count)
    except ModbusError as err:
        raise HomeAssistantError(f"Read of register {address} failed: {err}") from err
    return {"registers": {str(address + i): v for i, v in enumerate(values)}}


async def _write(call: ServiceCall) -> None:
    coordinator = _entry(call.hass, call).runtime_data
    client = coordinator.client
    address, value = call.data[ATTR_ADDRESS], call.data[ATTR_VALUE]
    _LOGGER.warning(
        "Writing raw register %s = %s (unit %s)", address, value, client.unit
    )
    try:
        await client.modbus.write_register(client.unit, address, value)
    except ModbusError as err:
        raise HomeAssistantError(f"Write of register {address} failed: {err}") from err
    await coordinator.async_request_refresh()


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the integration services."""
    hass.services.async_register(
        DOMAIN,
        "read_register",
        _read,
        schema=READ_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(DOMAIN, "write_register", _write, schema=WRITE_SCHEMA)
