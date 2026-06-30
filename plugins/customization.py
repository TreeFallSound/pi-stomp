"""Plugin customization registry.

Owns the URI → :class:`PluginCustomization` map. Plugin modules call
``register(...)`` at import time; the composition root (the handler) imports
this package once — that import *is* the explicit load — then passes ``lookup``
down as the :data:`~modalapi.plugin_customization.Customizer` for pedalboard
parsing. The :class:`PluginCustomization` *type* lives in ``modalapi`` so
``Plugin``/``Pedalboard`` never import this (higher) layer.
"""

from __future__ import annotations

from modalapi.plugin_customization import PluginCustomization

__all__ = ["PluginCustomization", "register", "lookup", "registered_uris"]

_URI_MAP: dict[str, PluginCustomization] = {}
_DEFAULT = PluginCustomization()


def register(*uris: str, customization: PluginCustomization) -> None:
    """Register a ``PluginCustomization`` for one or more LV2 URIs."""
    for uri in uris:
        _URI_MAP[uri] = customization


def lookup(uri: str | None) -> PluginCustomization:
    if not uri:
        return _DEFAULT
    return _URI_MAP.get(uri, _DEFAULT)


def registered_uris() -> frozenset[str]:
    """All URIs that have a registered customization."""
    return frozenset(_URI_MAP)
