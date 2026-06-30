"""NAM (Neural Amp Modeler) plugin customizations.

Registers custom tile colors, border, display name, and subtitle
for NAM plugin URIs.  A fullscreen panel will be added here in a
future change.
"""

from __future__ import annotations

import os
import re
import urllib.parse
from dataclasses import dataclass

from common.color import RectBorder
from modalapi.plugin import Plugin
from modalapi.plugin_customization import PluginExtraData, extra_data_as
from plugins.customization import PluginCustomization, register

NAM_URIS = (
    "http://github.com/mikeoliphant/neural-amp-modeler-lv2",
    "http://gareus.org/oss/lv2/nam#mono",
    "http://gareus.org/oss/lv2/nam#stereo",
    "https://tone3000.com/plugins/nam",
)

_NAM_YELLOW = (224, 179, 0)
_NAM_RED = (220, 20, 20)
_NAM_BLUE = (20, 30, 220)

_MODEL_RE = re.compile(r"<[^>]*#model>\s+<([^>]+)>")


@dataclass(frozen=True)
class NamData(PluginExtraData):
    """The model file referenced by a NAM instance's effect TTL."""

    model_path: str


def _parse_nam(ttl: str) -> NamData | None:
    m = _MODEL_RE.search(ttl)
    return NamData(model_path=m.group(1)) if m else None


def _model_filename(plugin: Plugin) -> str | None:
    data = extra_data_as(plugin, NamData)
    if data is None:
        return None
    decoded = urllib.parse.unquote(data.model_path)
    return os.path.basename(decoded)


def _nam_display_name(plugin: Plugin) -> str | None:
    name = _model_filename(plugin)
    if name is None:
        return None
    stem, _ = os.path.splitext(name)
    return stem


def _nam_subtitle(plugin: Plugin) -> str | None:
    name = _model_filename(plugin)
    if name is None:
        return None
    return f"NAM: {name}"


register(
    *NAM_URIS,
    customization=PluginCustomization(
        tile_active_color=_NAM_YELLOW,
        tile_border=RectBorder(
            top=_NAM_RED,
            right=_NAM_YELLOW,
            bottom=_NAM_BLUE,
            left=_NAM_YELLOW,
        ),
        display_name_fn=_nam_display_name,
        subtitle_fn=_nam_subtitle,
    ),
    extra_data_fn=_parse_nam,
)
