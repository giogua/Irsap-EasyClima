"""Fan speed regulation (pure logic)."""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
if "irsap_clima_pkg" not in sys.modules:
    pkg = types.ModuleType("irsap_clima_pkg")
    pkg.__path__ = [str(ROOT / "custom_components/irsap_clima")]
    sys.modules["irsap_clima_pkg"] = pkg
api = importlib.import_module("irsap_clima_pkg.api")
fan = importlib.import_module("irsap_clima_pkg.fan")

S = fan.FanSettings()  # auto 20-70 % over 2 K, silent 35, night 20, max 100


def data(air=22.0, sp=24.0, season=5, stat=0, prg=0, f267=80, f268=None):
    d = api.ClimaData()
    d.raw.update(
        {
            0: round(air * 10),
            231: round(sp * 10),
            8: round(sp * 10),
            233: season,
            104: stat,
            201: prg,
            267: f267,
            268: f267 if f268 is None else f268,
        }
    )
    return d


def test_off_uses_minimum():
    assert fan.fan_target(data(prg=0x80), S) == 20


@pytest.mark.parametrize(("prg", "speed"), [(1, 35), (2, 20), (3, 100)])
def test_fixed_programs(prg, speed):
    d = data(prg=prg)
    assert fan.fan_target(d, S) == speed
    assert fan.needs_write(d, speed, S)  # 80 -> fixed speed, applied exactly


def test_auto_cooling_proportional_and_ramped():
    # 1 K above the set point in summer: half way, 45 %
    assert fan.fan_target(data(air=25.0, f267=100), S) == 45  # from outside the range
    assert fan.fan_target(data(air=25.0, f267=30), S) == 35  # ramp: +5 per poll
    assert fan.fan_target(data(air=25.0, f267=44), S) == 45
    # far from the set point: maximum
    assert fan.fan_target(data(air=30.0, f267=70), S) == 70
    # satisfied: back down to the minimum, ramped
    assert fan.fan_target(data(air=23.0, f267=50), S) == 45


def test_auto_heating_and_auto_season():
    winter = data(air=19.0, sp=21.0, season=3, f267=20)
    assert fan.fan_target(winter, S) == 25  # 2 K below: max, ramped from 20
    # automatic season: direction from the active mode bits
    assert fan.demand(data(air=19.0, sp=21.0, season=0, stat=0b10)) == 2.0
    assert fan.demand(data(air=19.0, sp=21.0, season=0, stat=0)) == 0.0


def test_deadband_and_limits():
    assert not fan.needs_write(data(f267=45), 46, S)
    assert fan.needs_write(data(f267=45), 48, S)
    assert fan.needs_write(data(f267=21), 20, S)  # always reach the minimum
    assert fan.needs_write(data(f267=45, f268=40), 45, S)  # registers disagree


def test_options():
    s = fan.FanSettings.from_options({"fan_auto_min": 60, "fan_auto_max": 30})
    assert (s.auto_min, s.auto_max) == (30, 60)
