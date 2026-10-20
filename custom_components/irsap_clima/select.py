"""Season select: change heating/cooling without switching the unit on."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import SEASON_AUTO, SEASON_SUMMER, SEASON_WINTER
from .coordinator import IrsapClimaConfigEntry, IrsapClimaCoordinator
from .entity import IrsapClimaEntity

SEASONS = {"winter": SEASON_WINTER, "summer": SEASON_SUMMER, "auto": SEASON_AUTO}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrsapClimaConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the season select."""
    async_add_entities([IrsapClimaSeason(entry.runtime_data)])


class IrsapClimaSeason(IrsapClimaEntity, SelectEntity):
    """Season (register 233): winter = heating, summer = cooling, auto."""

    _attr_translation_key = "season"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_options = list(SEASONS)

    def __init__(self, coordinator: IrsapClimaCoordinator) -> None:
        super().__init__(coordinator, "season")

    @property
    def current_option(self) -> str | None:
        """Current season."""
        value = self.coordinator.data.season
        return next((k for k, v in SEASONS.items() if v == value), None)

    async def async_select_option(self, option: str) -> None:
        """Write the season (the on/off state is not changed)."""
        await self._async_command(
            self.coordinator.client.async_set_season, SEASONS[option]
        )
