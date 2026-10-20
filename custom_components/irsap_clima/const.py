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
CONF_SCAN_INTERVAL: Final = "scan_interval"
DEFAULT_SCAN_INTERVAL: Final = 30
MIN_SCAN_INTERVAL: Final = 10
