"""Tests of the standalone client against the fake unit."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(Path(__file__).parent))
from fake_clima import FakeClima  # noqa: E402

# Load the package modules without importing Home Assistant.
pkg = types.ModuleType("irsap_clima_pkg")
pkg.__path__ = [str(ROOT / "custom_components/irsap_clima")]
sys.modules["irsap_clima_pkg"] = pkg
modbus = importlib.import_module("irsap_clima_pkg.modbus")
api = importlib.import_module("irsap_clima_pkg.api")


@pytest.fixture(params=["tcp", "rtu"])
async def env(request):
    fake = FakeClima()
    fake.framing = request.param
    await fake.start()
    client = api.ClimaClient(
        modbus.ModbusTcpClient("127.0.0.1", fake.port, framing=request.param), 1
    )
    yield fake, client
    await client.async_close()
    await fake.stop()


async def test_read(env):
    fake, client = env
    del fake.regs[2]  # unsupported register is skipped
    data = await client.async_get_data()
    assert data.air_temperature == 21.5
    assert data.water_temperature == 45.2
    assert data.water_temperature_h4 is None
    assert data.setpoint == 21.0
    assert data.is_on is True
    assert data.program == "auto"
    assert data.season == 3
    assert data.heating_mode is True
    assert data.boiler_request is True
    assert data.chiller_request is False
    assert data.water_valve is True
    assert data.fan_speed == 900
    assert data.alarm is False
    assert data.alarms == []
    data2 = await client.async_get_data()
    assert 2 not in data2.raw


async def test_prg_read_modify_write(env):
    fake, client = env
    await client.async_set_program("night")
    assert fake.regs[201] == 0x0102
    await client.async_set_power(False)
    assert fake.regs[201] == 0x0182  # standby, program and reserved bit kept
    await client.async_set_keyboard_lock(True)
    assert fake.regs[201] == 0x0192
    await client.async_set_power(True)
    await client.async_set_keyboard_lock(False)
    assert fake.regs[201] == 0x0102
    # no write when nothing changes
    n = len(fake.writes)
    await client.async_set_power(True)
    assert len(fake.writes) == n


async def test_setpoint_and_season(env):
    fake, client = env
    await client.async_set_setpoint(23.5)
    assert fake.regs[231] == 235
    with pytest.raises(api.ClimaError):
        await client.async_set_setpoint(35)
    await client.async_set_season(api.SEASON_SUMMER)
    data = await client.async_get_data()
    assert data.season == 5
    assert data.cooling_mode is True
    with pytest.raises(ValueError):
        await client.async_set_season(4)


async def test_alarms(env):
    fake, client = env
    fake.regs[105] = (1 << 10) | (1 << 7)
    fake.regs[104] |= 1 << 9
    data = await client.async_get_data()
    assert data.alarm is True
    assert data.filter_dirty is True
    assert data.alarms == ["motor", "filter"]


async def test_wrong_unit_and_unreachable(env):
    fake, client = env
    other = api.ClimaClient(
        modbus.ModbusTcpClient(
            "127.0.0.1", fake.port, timeout=0.5, retries=0, framing=fake.framing
        ),
        7,
    )
    # A Modbus TCP gateway answers "target failed to respond"; on a
    # transparent link the bus simply stays silent.
    expected = (
        modbus.ModbusExceptionResponse
        if fake.framing == "tcp"
        else modbus.ModbusTimeoutError
    )
    with pytest.raises(expected):
        await other.async_validate()
    await other.async_close()
    dead = api.ClimaClient(
        modbus.ModbusTcpClient("127.0.0.1", 1, timeout=1, retries=0), 1
    )
    with pytest.raises(modbus.ModbusConnectionError):
        await dead.async_validate()


async def test_reconnect_after_server_restart(env):
    fake, client = env
    assert (await client.async_get_data()).air_temperature == 21.5
    # drop the connection server side
    await client.modbus.close()
    fake.regs[0] = 199
    assert (await client.async_get_data()).air_temperature == 19.9


@pytest.mark.parametrize("framing", ["tcp", "rtu"])
async def test_timeout_keeps_connection(framing):
    fake = FakeClima()
    fake.framing = framing
    await fake.start()
    client = api.ClimaClient(
        modbus.ModbusTcpClient("127.0.0.1", fake.port, timeout=1, framing=framing), 1
    )
    try:
        await client.async_get_data()
        fake.drop_next = 1
        data = await client.async_get_data()
        assert data.air_temperature == 21.5
        fake.drop_next = 1
        fake.late_reply = True
        fake.regs[0] = 230
        data = await client.async_get_data()
        assert data.air_temperature == 23.0
        assert data.setpoint == 21.0  # no response mixed up after the late answer
        assert fake.connections == 1
    finally:
        await client.async_close()
        await fake.stop()


async def test_forced_off(env):
    fake, client = env
    fake.regs[247] = 0b10
    fake.regs[104] |= 1 << 11
    data = await client.async_get_data()
    assert data.forced_off is True
    assert data.unit_standby is True
    await client.async_clear_forced_off()
    assert fake.regs[247] == 0


async def test_power_on_sets_supervisor_mode(env):
    fake, client = env
    fake.regs[224] = 2
    fake.regs[201] |= 0x80
    await client.async_set_power(True)
    assert fake.regs[224] == 0
    assert not fake.regs[201] & 0x80
