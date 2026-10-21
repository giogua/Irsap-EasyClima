"""Data update coordinator for the Irsap CLIMA integration."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import REG_FAN_A, REG_FAN_B, REG_SUP_224, ClimaClient, ClimaData
from .const import CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL, DOMAIN
from .fan import FanSettings, fan_target, needs_write
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

    @property
    def fan_settings(self) -> FanSettings:
        """Fan speeds configured in the options."""
        return FanSettings.from_options(self.config_entry.options)

    async def _async_update_data(self) -> ClimaData:
        try:
            data = await self.client.async_get_data()
        except ModbusError as err:
            raise UpdateFailed(f"Cannot read the CLIMA unit: {err}") from err
        try:
            await self._async_regulate(data)
        except ModbusError as err:
            # The state was read fine; the next poll retries the regulation.
            _LOGGER.warning("CLIMA fan regulation failed: %s", err)
        return data

    async def _async_regulate(self, data: ClimaData) -> None:
        """Act as the supervisor: fan speed and supervisor mode."""
        if data.is_on is None:
            return
        if data.is_on and data.raw.get(REG_SUP_224, 0) != 0:
            _LOGGER.info(
                "CLIMA was not in supervisor mode (224=%s), fixing",
                data.raw[REG_SUP_224],
            )
            await self.client.async_ensure_supervisor_mode()
            data.raw[REG_SUP_224] = 0
        settings = self.fan_settings
        target = fan_target(data, settings)
        if needs_write(data, target, settings):
            _LOGGER.debug(
                "Fan %s%% -> %s%% (program %s)",
                data.supervisor_fan,
                target,
                data.program,
            )
            await self.client.async_set_supervisor_fan(target)
            data.raw[REG_FAN_A] = data.raw[REG_FAN_B] = target
