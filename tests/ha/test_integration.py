"""End-to-end tests inside Home Assistant."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

sys.path.insert(0, str(Path(__file__).parents[1]))
from fake_clima import FakeClima  # noqa: E402

DOMAIN = "irsap_clima"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations."""
    return


@pytest.fixture
async def fake(socket_enabled):
    unit = FakeClima()
    await unit.start()
    yield unit
    await unit.stop()


async def _setup(hass: HomeAssistant, fake: FakeClima, unit: int = 1) -> str:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake.port,
            "unit_id": unit,
            CONF_NAME: "CLIMA",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY, result
    await hass.async_block_till_done()
    return result["result"].entry_id


async def test_full(hass: HomeAssistant, fake: FakeClima) -> None:
    entry_id = await _setup(hass, fake)
    devices = dr.async_entries_for_config_entry(dr.async_get(hass), entry_id)
    assert len(devices) == 1
    entities = er.async_entries_for_config_entry(er.async_get(hass), entry_id)
    assert all(e.device_id == devices[0].id for e in entities)

    state = hass.states.get("climate.clima")
    assert state.state == "heat"
    assert state.attributes["current_temperature"] == 21.5
    assert state.attributes["temperature"] == 21.0
    assert state.attributes["hvac_action"] == "heating"
    assert state.attributes["fan_mode"] == "auto"
    assert state.attributes["min_temp"] == 16.0
    assert hass.states.get("sensor.clima_water_temperature").state == "45.2"
    assert hass.states.get("binary_sensor.clima_heat_request").state == "on"

    await hass.services.async_call(
        "climate",
        "set_temperature",
        {"entity_id": "climate.clima", "temperature": 22.5},
        blocking=True,
    )
    assert fake.regs[231] == 225
    await hass.services.async_call(
        "climate",
        "set_fan_mode",
        {"entity_id": "climate.clima", "fan_mode": "max"},
        blocking=True,
    )
    assert fake.regs[201] == 0x0103
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.clima", "hvac_mode": "off"},
        blocking=True,
    )
    assert fake.regs[201] == 0x0183
    assert hass.states.get("climate.clima").state == "off"
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {"entity_id": "climate.clima", "hvac_mode": "cool"},
        blocking=True,
    )
    assert fake.regs[233] == 5
    assert fake.regs[201] == 0x0103
    state = hass.states.get("climate.clima")
    assert state.state == "cool"
    assert state.attributes["hvac_action"] == "cooling"


async def test_errors(hass: HomeAssistant, fake: FakeClima) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "127.0.0.1",
            CONF_PORT: fake.port,
            "unit_id": 9,
            CONF_NAME: "CLIMA",
        },
    )
    assert result["errors"] == {"base": "no_response"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_HOST: "127.0.0.1", CONF_PORT: 1, "unit_id": 1, CONF_NAME: "CLIMA"},
    )
    assert result["errors"] == {"base": "cannot_connect"}
