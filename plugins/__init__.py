"""Plugin panel registry.

Each panel implementation registers itself against the LV2 URIs it handles.
``lcd320x240.plugin_event`` and ``modhandler.show_plugin_panel`` dispatch
via this registry.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

if TYPE_CHECKING:
    from plugins.base import PluginPanel

_PanelT = TypeVar("_PanelT", bound="type[PluginPanel]")

PANELS: dict[str, type[PluginPanel]] = {}


def register_panel(*uris: str):
    """Decorator that maps one or more LV2 plugin URIs to a panel class.

    Example::

        @register_panel("http://gareus.org/oss/lv2/fil4#mono")
        class EqPanel(PluginPanel):
            ...
    """

    def decorator(cls: _PanelT) -> _PanelT:
        for u in uris:
            PANELS[u] = cls
        return cls

    return decorator
