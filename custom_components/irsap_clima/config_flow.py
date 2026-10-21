"""Config flow for the Irsap CLIMA integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import ClimaClient
from .const import (
    CONF_FAN_AUTO_BAND,
    CONF_FAN_AUTO_MAX,
    CONF_FAN_AUTO_MIN,
    CONF_FAN_MAX,
    CONF_FAN_NIGHT,
    CONF_FAN_SILENT,
    CONF_FRAMING,
    CONF_SCAN_INTERVAL,
    CONF_UNIT,
    DEFAULT_FAN_AUTO_BAND,
    DEFAULT_FAN_AUTO_MAX,
    DEFAULT_FAN_AUTO_MIN,
    DEFAULT_FAN_MAX,
    DEFAULT_FAN_NIGHT,
    DEFAULT_FAN_SILENT,
    DEFAULT_FRAMING,
    DEFAULT_NAME,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_UNIT,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .coordinator import IrsapClimaConfigEntry
from .modbus import (
    FRAMING_RTU,
    FRAMING_TCP,
    ModbusConnectionError,
    ModbusError,
    ModbusTcpClient,
)

_LOGGER = logging.getLogger(__name__)


FRAMING_SELECTOR = SelectSelector(
    SelectSelectorConfig(
        options=[FRAMING_TCP, FRAMING_RTU],
        mode=SelectSelectorMode.LIST,
        translation_key=CONF_FRAMING,
    )
)


async def _validate(
    host: str, port: int, unit: int, framing: str = DEFAULT_FRAMING
) -> dict[str, str]:
    client = ClimaClient(ModbusTcpClient(host, port, retries=1, framing=framing), unit)
    try:
        await client.async_validate()
    except ModbusConnectionError as err:
        _LOGGER.warning("CLIMA setup: %s", err)
        return {"base": "cannot_connect"}
    except ModbusError as err:
        _LOGGER.warning("CLIMA setup: %s", err)
        return {"base": "no_response"}
    except Exception:
        _LOGGER.exception("Unexpected error validating %s:%s", host, port)
        return {"base": "unknown"}
    finally:
        await client.async_close()
    return {}


class IrsapClimaConfigFlow(ConfigFlow, domain=DOMAIN):
    """One entry per unit (gateway + Modbus unit id)."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the gateway address and the unit id."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            unit = int(user_input[CONF_UNIT])
            framing = user_input.get(CONF_FRAMING, DEFAULT_FRAMING)
            await self.async_set_unique_id(f"{host}:{port}:{unit}")
            self._abort_if_unique_id_configured()
            errors = await _validate(host, port, unit, framing)
            if not errors:
                return self.async_create_entry(
                    title=user_input[CONF_NAME],
                    data={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_UNIT: unit,
                        CONF_FRAMING: framing,
                    },
                )
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=65535)
                ),
                vol.Required(CONF_UNIT, default=DEFAULT_UNIT): vol.All(
                    vol.Coerce(int), vol.Range(min=1, max=247)
                ),
                vol.Required(CONF_FRAMING, default=DEFAULT_FRAMING): FRAMING_SELECTOR,
                vol.Required(CONF_NAME, default=DEFAULT_NAME): str,
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(schema, user_input),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the gateway address or the unit id."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = int(user_input[CONF_PORT])
            unit = int(user_input[CONF_UNIT])
            framing = user_input.get(CONF_FRAMING, DEFAULT_FRAMING)
            new_id = f"{host}:{port}:{unit}"
            await self.async_set_unique_id(new_id)
            if new_id != entry.unique_id:
                self._abort_if_unique_id_configured()
            coordinator = getattr(entry, "runtime_data", None)
            if new_id == entry.unique_id and coordinator is not None:
                # Same gateway: release its (single) connection before testing.
                await coordinator.client.async_close()
            errors = await _validate(host, port, unit, framing)
            if not errors:
                return self.async_update_reload_and_abort(
                    entry,
                    unique_id=new_id,
                    data_updates={
                        CONF_HOST: host,
                        CONF_PORT: port,
                        CONF_UNIT: unit,
                        CONF_FRAMING: framing,
                    },
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str,
                    vol.Required(CONF_PORT, default=entry.data[CONF_PORT]): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=65535)
                    ),
                    vol.Required(CONF_UNIT, default=entry.data[CONF_UNIT]): vol.All(
                        vol.Coerce(int), vol.Range(min=1, max=247)
                    ),
                    vol.Required(
                        CONF_FRAMING,
                        default=entry.data.get(CONF_FRAMING, DEFAULT_FRAMING),
                    ): FRAMING_SELECTOR,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: IrsapClimaConfigEntry) -> OptionsFlow:
        """Polling interval."""
        return IrsapClimaOptionsFlow()


PERCENT = vol.All(vol.Coerce(int), vol.Range(min=10, max=100))


class IrsapClimaOptionsFlow(OptionsFlow):
    """Polling interval and fan speeds."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        opts = self.config_entry.options

        def field(key: str, default: Any) -> vol.Required:
            return vol.Required(key, default=opts.get(key, default))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    field(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL): vol.All(
                        vol.Coerce(int), vol.Range(min=MIN_SCAN_INTERVAL, max=3600)
                    ),
                    field(CONF_FAN_AUTO_MIN, DEFAULT_FAN_AUTO_MIN): PERCENT,
                    field(CONF_FAN_AUTO_MAX, DEFAULT_FAN_AUTO_MAX): PERCENT,
                    field(CONF_FAN_AUTO_BAND, DEFAULT_FAN_AUTO_BAND): vol.All(
                        vol.Coerce(float), vol.Range(min=0.5, max=10)
                    ),
                    field(CONF_FAN_SILENT, DEFAULT_FAN_SILENT): PERCENT,
                    field(CONF_FAN_NIGHT, DEFAULT_FAN_NIGHT): PERCENT,
                    field(CONF_FAN_MAX, DEFAULT_FAN_MAX): PERCENT,
                }
            ),
        )
