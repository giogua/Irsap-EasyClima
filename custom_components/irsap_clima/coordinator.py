"""Data update coordinator for the Irsap CLIMA integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ClimaClient, ClimaData
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .modbus import ModbusError

_LOGGER = logging.getLogger(__name__)

type IrsapClimaConfigEntry = ConfigEntry[IrsapClimaCoordinator]


class IrsapClimaCoordinator(DataUpdateCoordinator[ClimaData]):
    """Polls one unit over Modbus TCP."""

    config_entry: IrsapClimaConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: IrsapClimaConfigEntry, client: ClimaClient
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            update_interval=timedelta(
                seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
            ),
        )
        self.client = client

    async def _async_update_data(self) -> ClimaData:
        try:
            return await self.client.async_get_data()
        except ModbusError as err:
            raise UpdateFailed(f"Cannot read the CLIMA unit: {err}") from err
