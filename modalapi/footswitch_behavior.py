"""FootswitchBehavior protocol and default implementation."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol
from pistomp.category import get_category_color

if TYPE_CHECKING:
    from modalapi.plugin import Plugin
    from pistomp.beatsync import TickState
    from pistomp.footswitch import Footswitch


class LedDisplayStyle(Enum):
    SOLID = auto()
    METRONOME = auto()


class FootswitchBehavior(Protocol):
    """Defines how a footswitch behaves when bound to a plugin."""

    @property
    def momentary(self) -> bool: ...

    def output_subscriptions(self) -> Iterable[str]:
        """Return the symbols of plugin outputs that this footswitch should subscribe to."""
        ...

    def on_output(self, symbol: str, value: float) -> None:
        """Called when a subscribed output changes. The footswitch can use this to update its state."""
        ...

    def led_color(self, beat: TickState) -> tuple[int, int, int] | None:
        """Return the RGB color of the footswitch LED, or None to turn it off."""
        ...

    def led_style(self, beat: TickState) -> LedDisplayStyle: ...


class DefaultFootswitchBehavior:
    """Built-in behavior: toggle semantics, category color, no WS subscriptions."""

    def __init__(self, fs: Footswitch) -> None:
        self._fs = fs

    @property
    def momentary(self) -> bool:
        return False

    def output_subscriptions(self) -> Iterable[str]:
        return ()

    def on_output(self, symbol: str, value: float) -> None:
        pass

    def led_color(self, beat: TickState) -> tuple[int, int, int] | None:
        if not self._fs.toggled:
            return None
        if self._fs.category is not None:
            return get_category_color(self._fs.category)
        return (255, 255, 255)

    def led_style(self, beat: TickState) -> LedDisplayStyle:
        return LedDisplayStyle.SOLID


def attach_footswitch_behavior(fs: Footswitch, plugin: Plugin) -> None:
    """Attach the plugin's footswitch behavior to `fs`, or a DefaultFootswitchBehavior
    if the plugin has no `footswitch_behavior_fn` or it returns None.

    Called from every bind site (ControllerManager.bind at pedalboard load, and
    Handler._apply_midi_binding on live MIDI-learn) so the 'every footswitch
    always has a behavior' invariant holds regardless of how the binding arose."""
    fn = plugin.customization.footswitch_behavior_fn
    if fn is not None:
        b = fn(plugin)
        fs.behavior = b if b is not None else DefaultFootswitchBehavior(fs)
    else:
        fs.behavior = DefaultFootswitchBehavior(fs)
