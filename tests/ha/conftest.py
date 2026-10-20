"""Make the repository's custom_components visible to Home Assistant."""

from pathlib import Path

import custom_components

_ROOT = Path(__file__).parents[2] / "custom_components"
if str(_ROOT) not in custom_components.__path__:
    custom_components.__path__.append(str(_ROOT))
