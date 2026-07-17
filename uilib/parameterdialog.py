# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

from uilib.box import Box
from uilib.config import Config
from uilib.dialog import Dialog
from uilib.glyphs.badge import BadgeGlyph
from uilib.image import ImageWidget
from uilib.misc import InputEvent, WidgetAlign, get_text_size
from uilib.text import TextWidget
from uilib.widget import Widget
from common.contexts import (
    BindingDecl,
    ContextKind,
    ContextRef,
    ControlClass,
    ControlRef,
    EventKind,
    ParamEffect,
)
from common.parameter import Parameter, Symbol
from common.parameter_steps import ParameterSteps, effective_multiplier
from pistomp.input.dispatch import resolve_local, fire
from pistomp.input.event import ControllerEvent, EncoderEvent

from collections.abc import Callable
from functools import lru_cache

import numpy as np
import pygame
import time


# Bar geometry/colors are fixed constants so the
# rendered bar surface depends only on taper and color
@lru_cache(maxsize=None)
def _render_bar_surface(
    taper: float,
    num_points: int,
    bar_width: int,
    graph_x_offset: int,
    graph_y0: int,
    graph_width: int,
    graph_height: int,
    color: tuple,
) -> pygame.Surface:
    x = np.linspace(1, num_points, num_points)
    graph_points = num_points * ((x / len(x)) ** taper)

    surf = pygame.Surface((graph_width, graph_height), pygame.SRCALPHA)
    for idx in range(num_points):
        g = int(graph_points[idx])
        if g <= 0:
            continue
        x0 = graph_x_offset + idx * bar_width
        pygame.draw.rect(surf, color, pygame.Rect(x0, graph_y0 - g, bar_width, g), 1)
    return surf


class _GraphWidget(ImageWidget):
    """Bar graph surface. Skips the background erase: the bars are the same
    geometry in both colors, so a repaint overwrites them exactly, and the
    transparent gaps must leave the value text (which sits inside this
    widget's box) untouched."""

    def _draw_erase(self, ctx):
        pass


class Parameterdialog(Dialog):
    # TODO detailed dimensions, colors, etc. should not be defined in uilib
    GRAPH_Y0 = 80
    GRAPH_X_OFFSET = 10
    BAR_FILLED = (255, 255, 0)  # 'yellow'
    BAR_UNFILLED = (100, 100, 240)

    def __init__(self, stack, parameter, width, height, title, title_font=None, timeout=None, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(Parameterdialog, self).__init__(width, height, title, title_font, **kwargs)
        self.stack = (
            stack  # TODO very LAME to require the stack to be passed, ideally panel would be able to pop itself
        )
        self.parameter: Parameter = parameter

        # The tweak encoder (1/2/3) TTL/config-bound to this dialog's parameter
        # (set by Lcd320x240.draw_parameter_dialog from tweak_badge_number).
        # When set, the dialog declares a PANEL row for it so a turn drives the
        # dialog's parameter through the binding table instead of falling
        # through to Modhandler._handle_encoder (which would write the tweak's
        # pedalboard-bound parameter underneath — see input/README.md).
        self._tweak_id: int | None = None

        # The nav encoder steps this dialog through the same quantized grid a v3
        # tweak encoder uses, so a detent moves the value identically whichever
        # control you turn (v2 nav, v3 nav, v3 tweak).
        self.steps = ParameterSteps.for_parameter(self.parameter)

        self.timeout = timeout
        self.expiry_time = None
        if self.timeout:
            self.reset_timeout()

        # "graph" are the y-scaled values, "actual" are the actual non-scaled values
        self.taper = self.parameter.get_taper()  # Derive from parameter type
        self.num_actual = 256  # High resolution for better stepping
        self.num_points = 60
        self.bar_width = 4
        self.actual_abscissa = np.linspace(0, self.num_actual, self.num_actual)
        self.actual_points = self._calc_graph_points(
            self.actual_abscissa, self.parameter.minimum, self.parameter.maximum
        )

        # Value at which each bar becomes filled. Nondecreasing, so the filled
        # bars are always the prefix [0, k) and a value change dirties only the
        # columns between the old and new k.
        self.bar_thresholds = self.actual_points[(np.arange(self.num_points) * self.num_actual) // self.num_points]

        self.graph_width = self.GRAPH_X_OFFSET + self.bar_width * self.num_points
        # +1 row of headroom so a max-height bar's bottom edge isn't clipped.
        self.graph_height = self.GRAPH_Y0 + 1

        self.w_value = None
        self.w_graph: _GraphWidget | None = None
        self._graph_surface: pygame.Surface | None = None
        self._bars_filled: pygame.Surface | None = None
        self._bars_unfilled: pygame.Surface | None = None
        self.last_param_value: float = self.parameter.value
        self._draw_contents()
        self._unsub: Callable[[], None] | None = self.parameter.subscribe(self._on_param_changed)

    def _on_param_changed(self, param: Parameter) -> None:
        """Every redraw path runs through here: our own detents write
        `parameter.value` and land back on this observer, same as a tweak encoder
        or a MOD-UI echo does."""
        self.steps.set_value(param.value)
        self._draw_graph()

    def _unsubscribe(self) -> None:
        if self._unsub is not None:
            self._unsub()
            self._unsub = None

    def _calc_graph_points(self, x, min, max):
        # Calculate the y-values using a logarithmic function
        points = min + (max - min) * ((x / len(x)) ** self.taper)
        return points

    def _draw_contents(self):
        if self.timeout is None:
            # Only draw close button if not using timeout autoclose
            b = TextWidget(
                box=Box.xywh(108, 100, 0, 0),
                text="Close",
                parent=self,
                outline=1,
                sel_width=3,
                outline_radius=5,
                align=WidgetAlign.NONE,
                name="ok_btn",
            )
            b.set_selected(True)
        self._draw_graph()

    def _update_text_widget(self):
        y0 = 80
        val_text = self.parameter.format(self.parameter.value)
        min_text = self.parameter.format(self.parameter.minimum)
        max_text = self.parameter.format(self.parameter.maximum)

        # Calculate centered position
        font = Config().get_font("default")
        text_width, text_height = get_text_size(val_text, font)
        x_centered = (self.box.width - text_width) // 2

        if self.w_value is None:
            self.w_value = TextWidget(
                box=Box.xywh(x_centered, 23, text_width, text_height),
                text=val_text,
                parent=self,
                align=WidgetAlign.NONE,
                name="value",
            )
            self.w_value.set_foreground("yellow")
            TextWidget(
                box=Box.xywh(0, y0, 0, 0), text=min_text, parent=self, outline=0, align=WidgetAlign.NONE, name="value"
            )
            TextWidget(
                box=Box.xywh(220, y0, 0, 0), text=max_text, parent=self, outline=0, align=WidgetAlign.NONE, name="value"
            )
        elif val_text != self.w_value.text:
            # set_text() would refresh at the *old* box, painting the new string
            # in the old (uncentered) position and pushing it before we move the
            # box — a visible stale label and a wasted SPI push. Update in place
            # and recompose the union of both boxes once, as Subtitle does.
            assert self.w_value.box is not None  # visible ⇒ box set
            old = self.w_value.box.copy()
            new = Box.xywh(x_centered, 23, text_width, text_height)
            self.w_value.text = val_text
            self.w_value.text_size_valid = False
            self.w_value.set_box(new, realign=True, refresh=False)
            self.redraw_region(old.union(new))

    def _filled_count(self, value: float) -> int:
        """Number of leading bars filled at `value`."""
        return int(np.searchsorted(self.bar_thresholds, value, side="right"))

    def _blit_bars(self, lo: int, hi: int, filled: bool) -> Box:
        """Repaint bars [lo, hi) from the matching pre-rendered surface.

        Returns the dirty rect in the graph widget's parent coords.
        """
        assert self._graph_surface is not None and self.w_graph is not None
        assert self._bars_filled is not None and self._bars_unfilled is not None
        rect = pygame.Rect(self.GRAPH_X_OFFSET + lo * self.bar_width, 0, (hi - lo) * self.bar_width, self.graph_height)
        src = self._bars_filled if filled else self._bars_unfilled
        self._graph_surface.fill((0, 0, 0, 0), rect)
        self._graph_surface.blit(src, rect.topleft, area=rect)
        return Box.xywh(*rect).offset(self.w_graph.box)

    def _draw_graph(self):
        self._update_text_widget()

        # Bars are pre-rendered once per dialog in both colors.
        # Only the strip between the old and new value needs repainting.
        value = self.parameter.value

        if self.w_graph is None:
            self._graph_surface = pygame.Surface((self.graph_width, self.graph_height), pygame.SRCALPHA)
            args = (
                self.taper,
                self.num_points,
                self.bar_width,
                self.GRAPH_X_OFFSET,
                self.GRAPH_Y0,
                self.graph_width,
                self.graph_height,
            )
            self._bars_filled = _render_bar_surface(*args, self.BAR_FILLED)
            self._bars_unfilled = _render_bar_surface(*args, self.BAR_UNFILLED)
            self.w_graph = _GraphWidget(
                image=self._graph_surface,
                box=Box.xywh(0, 0, self.graph_width, self.graph_height),
                parent=self,
                outline=0,
                sel_width=0,
            )
            k = self._filled_count(value)
            self._blit_bars(0, k, filled=True)
            self._blit_bars(k, self.num_points, filled=False)
            self.w_graph.refresh()
        else:
            k0 = self._filled_count(self.last_param_value)
            k = self._filled_count(value)
            if k != k0:
                lo, hi = (k0, k) if k > k0 else (k, k0)
                dirty = self._blit_bars(lo, hi, filled=k > k0)
                self.w_graph.refresh(dirty)

        self.last_param_value = value

    def _draw_badge(self, ctx) -> None:
        """Override of `Widget._draw_badge`: top-left corner of the dialog
        body, under the title strip (which is the decorator's, not ours) —
        the base's left-edge-centred default would land inside the bar
        graph."""
        if self._badge is None:
            return
        ctx.paste(self._badge.render(), (4, 4))

    def set_tweak_badge(self, tweak_id: int | None, badge: BadgeGlyph | None) -> None:
        """Record the badged tweak encoder id and paint its glyph. `tweak_id`
        is the 1/2/3 the binding table keys on; the glyph is purely visual."""
        self._tweak_id = tweak_id
        self.set_badge(badge)

    def reset_timeout(self):
        if self.timeout is not None:
            self.expiry_time = time.time() + self.timeout

    def tick(self):
        if self.expiry_time and time.time() > self.expiry_time:
            self.pop()

    def update_value(self, new_value: float) -> None:
        """Update display with new value (controller already calculated it)."""
        self.reset_timeout()
        self.parameter.value = new_value

    def parameter_value_change(self, direction, count: int = 1, multiplier: float = 1.0):
        self.reset_timeout()

        # Same arithmetic as EncoderController.refresh: the multiplier scales the
        # number of grid steps, not the value. effective_multiplier caps it per
        # parameter so a full-speed spin covers the same fraction of any grid.
        delta = int(round(direction * count * effective_multiplier(multiplier, self.parameter)))
        if delta == 0:
            return
        new_value = self.steps.move(delta)
        if new_value == self.parameter.value:
            return

        self.parameter.value = new_value
        if self.action is not None:
            self.action(self.object, new_value)

    def input_event(self, event):
        if event == InputEvent.CLICK:
            self.pop()
        elif event == InputEvent.LEFT:
            self.parameter_value_change(-1)
        elif event == InputEvent.RIGHT:
            self.parameter_value_change(1)
        else:
            return False
        return True

    def input_step(self, direction: int, count: int, multiplier: float = 1.0) -> bool:
        # A value slider has no intermediate states worth rendering: apply the
        # whole batch at once. On v2 the nav encoder is the only encoder, so
        # this is the sole path into the dialog and a fast spin would otherwise
        # cost one render + LCD push per detent. `multiplier` is the encoder's
        # speed factor, which the nav path otherwise discards.
        self.parameter_value_change(1 if direction > 0 else -1, count, multiplier)
        return True

    # ── table-driven tweak routing ────────────────────────────────────────
    # A tweak turn while this dialog is the top of the stack must edit the
    # dialog's parameter, not the tweak's pedalboard-bound parameter beneath
    # (the leak via Modhandler._handle_encoder — see input/README.md). We
    # declare a PANEL row for the badged tweak so the binding table resolves
    # it here, same shape as PluginPanel/ParameterWindow.

    def declare_bindings(self) -> tuple[BindingDecl, ...]:
        if self._tweak_id is None:
            return ()
        return (
            BindingDecl(
                control=ControlRef(cls=ControlClass.TWEAK, id=self._tweak_id),
                event_kind=EventKind.ROTATE,
                effects=(ParamEffect(plugin=None, symbol=self.parameter.symbol, commit=False),),
                context=ContextRef(kind=ContextKind.PANEL, name="parameter_dialog"),
            ),
        )

    def on_event(self, event: ControllerEvent) -> bool:
        if not isinstance(event, EncoderEvent):
            return False
        rows = self.declare_bindings()
        control_id = event.controller.id
        for cls in (ControlClass.TWEAK, ControlClass.VOLUME):
            decl = resolve_local(rows, ControlRef(cls=cls, id=control_id), EventKind.ROTATE)
            if decl is not None:
                return fire(decl, self, event)
        return False

    def edit_symbol(self, symbol: Symbol, rotations: int, multiplier: float = 1.0) -> bool:
        # The dialog edits a single parameter; the ParamEffect carries its
        # symbol. Forward to the same step+commit path NAV uses.
        if symbol != self.parameter.symbol:
            return False
        self.parameter_value_change(1 if rotations > 0 else -1, abs(rotations), multiplier)
        return True

    def pop(self):
        # Also unsubscribed by destroy(), but the VU calibration dialog is
        # auto_destroy=False and would otherwise stay subscribed after dismissal.
        self._unsubscribe()
        if self.parent:
            self.stack.pop_panel(self)
        self.expiry_time = None

    def destroy(self):
        self._unsubscribe()
        super().destroy()
