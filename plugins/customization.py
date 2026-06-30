"""URI → PluginCustomization registry. The type lives in `modalapi.plugin_customization`."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

from modalapi.plugin_customization import PluginCustomization, PluginExtraData

__all__ = ["PluginCustomization", "register", "lookup", "registered_uris"]


ExtraDataParser = Callable[[str], PluginExtraData | None]
_URI_MAP: dict[str, tuple[PluginCustomization, ExtraDataParser | None]] = {}


def register(
    *uris: str,
    customization: PluginCustomization,
    extra_data_fn: ExtraDataParser | None = None,
) -> None:
    """`extra_data_fn` (if given) is called by `lookup` with the plugin's `effect.ttl` contents to populate `customization.extra_data`."""
    for uri in uris:
        _URI_MAP[uri] = (customization, extra_data_fn)


def lookup(
    uri: str | None,
    bundlepath: str = "",
    instance_number: int | None = None,
) -> PluginCustomization:
    if not uri:
        return PluginCustomization()
    customization, parser = _URI_MAP.get(uri, (PluginCustomization(), None))
    if parser is not None and instance_number is not None:
        try:
            ttl = (Path(bundlepath) / f"effect-{instance_number}" / "effect.ttl").read_text(encoding="utf-8")
        except OSError:
            return customization
        extra = parser(ttl)
        if extra is not None:
            return replace(customization, extra_data=extra)
    return customization


def registered_uris() -> frozenset[str]:
    return frozenset(_URI_MAP)
