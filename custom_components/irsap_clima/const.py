"""Constants for the Irsap CLIMA integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "irsap_clima"

MANUFACTURER: Final = "Irsap"
DEFAULT_MODEL: Final = "CLIMA"
DEFAULT_NAME: Final = "CLIMA"
DEFAULT_PORT: Final = 502
DEFAULT_UNIT: Final = 1

CONF_UNIT: Final = "unit_id"
CONF_FRAMING: Final = "framing"
DEFAULT_FRAMING: Final = "tcp"
CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10

# Fan regulation (config entry options), percent
CONF_FAN_AUTO_MIN: Final = "fan_auto_min"
CONF_FAN_AUTO_MAX: Final = "fan_auto_max"
CONF_FAN_AUTO_BAND: Final = "fan_auto_band"
CONF_FAN_SILENT: Final = "fan_silent"
CONF_FAN_NIGHT: Final = "fan_night"
CONF_FAN_MAX: Final = "fan_max"
DEFAULT_FAN_AUTO_MIN: Final = 20
DEFAULT_FAN_AUTO_MAX: Final = 70
DEFAULT_FAN_AUTO_BAND: Final = 2.0  # K from the set point to reach the max
DEFAULT_FAN_SILENT: Final = 35
DEFAULT_FAN_NIGHT: Final = 20
DEFAULT_FAN_MAX: Final = 100
FAN_OFF: Final = 20  # written when the unit is switched off, like the EasyClima panel
