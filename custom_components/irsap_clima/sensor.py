"""Sensors for the Irsap CLIMA integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    EntityCategory,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import REG_ALARMS, REG_OUT, REG_PRG, REG_SEASON, REG_STAT, ClimaData
from .coordinator import IrsapClimaConfigEntry
from .entity import IrsapClimaEntity


@dataclass(frozen=True, kw_only=True)
class IrsapClimaSensorDescription(SensorEntityDescription):
    """Sensor description with a value getter."""

    value_fn: Callable[[ClimaData], Any]
    attrs_fn: Callable[[ClimaData], dict[str, Any]] | None = None


def _temp(
    key: str, fn: Callable[[ClimaData], Any], **kwargs: Any
) -> IrsapClimaSensorDescription:
    return IrsapClimaSensorDescription(
        key=key,
        translation_key=key,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=fn,
        **kwargs,
    )


SENSORS: tuple[IrsapClimaSensorDescription, ...] = (
    _temp("air_temperature", lambda d: d.air_temperature),
    _temp("water_temperature", lambda d: d.water_temperature),
    _temp(
        "water_temperature_h4",
        lambda d: d.water_temperature_h4,
        entity_registry_enabled_default=False,
    ),
    _temp(
        "effective_setpoint",
        lambda d: d.setpoint_effective,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    IrsapClimaSensorDescription(
        key="fan_speed",
        translation_key="fan_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.fan_speed,
    ),
    IrsapClimaSensorDescription(
        key="fan_hours",
        translation_key="fan_hours",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.HOURS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.fan_hours,
    ),
    IrsapClimaSensorDescription(
        key="alarms",
        translation_key="alarms",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: ", ".join(d.alarms) if d.alarms else "ok",
    ),
    IrsapClimaSensorDescription(
        key="registers",
        translation_key="registers",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda d: len(d.raw),
        attrs_fn=lambda d: {
            "STAT_104": f"{d.raw.get(REG_STAT, 0):#06x}",
            "ALR_105": f"{d.raw.get(REG_ALARMS, 0):#06x}",
            "PRG_201": f"{d.raw.get(REG_PRG, 0):#06x}",
            "OUT_9": f"{d.raw.get(REG_OUT, 0):#06x}",
            "SEASON_233": d.raw.get(REG_SEASON),
            "raw": {str(k): v for k, v in sorted(d.raw.items())},
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapClimaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors."""
    coordinator = entry.runtime_data
    async_add_entities(IrsapClimaSensor(coordinator, desc) for desc in SENSORS)


class IrsapClimaSensor(IrsapClimaEntity, SensorEntity):
    """A CLIMA sensor."""

    entity_description: IrsapClimaSensorDescription

    def __init__(self, coordinator, description: IrsapClimaSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
