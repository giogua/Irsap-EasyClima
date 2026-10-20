"""Binary sensors for the Irsap CLIMA integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import ClimaData
from .coordinator import IrsapClimaConfigEntry
from .entity import IrsapClimaEntity


@dataclass(frozen=True, kw_only=True)
class IrsapClimaBinaryDescription(BinarySensorEntityDescription):
    """Binary sensor description with a value getter."""

    value_fn: Callable[[ClimaData], bool | None]


BINARY_SENSORS: tuple[IrsapClimaBinaryDescription, ...] = (
    IrsapClimaBinaryDescription(
        key="heat_request",
        translation_key="heat_request",
        device_class=BinarySensorDeviceClass.HEAT,
        value_fn=lambda d: d.boiler_request,
    ),
    IrsapClimaBinaryDescription(
        key="cooling_request",
        translation_key="cooling_request",
        device_class=BinarySensorDeviceClass.COLD,
        value_fn=lambda d: d.chiller_request,
    ),
    IrsapClimaBinaryDescription(
        key="water_valve",
        translation_key="water_valve",
        device_class=BinarySensorDeviceClass.OPENING,
        value_fn=lambda d: d.water_valve,
    ),
    IrsapClimaBinaryDescription(
        key="alarm",
        translation_key="alarm",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.alarm,
    ),
    IrsapClimaBinaryDescription(
        key="filter",
        translation_key="filter",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda d: d.filter_dirty,
    ),
    IrsapClimaBinaryDescription(
        key="antifreeze",
        translation_key="antifreeze",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.antifreeze,
    ),
    IrsapClimaBinaryDescription(
        key="water_not_suitable",
        translation_key="water_not_suitable",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: d.water_not_suitable,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapClimaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up binary sensors."""
    coordinator = entry.runtime_data
    async_add_entities(IrsapClimaBinarySensor(coordinator, d) for d in BINARY_SENSORS)


class IrsapClimaBinarySensor(IrsapClimaEntity, BinarySensorEntity):
    """A CLIMA binary sensor."""

    entity_description: IrsapClimaBinaryDescription

    def __init__(self, coordinator, description: IrsapClimaBinaryDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        """Return the state."""
        return self.entity_description.value_fn(self.coordinator.data)
