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

from typing import Optional, Tuple
from typing_extensions import override
from abc import ABC

import pygame

from uilib.box import Box
from uilib.container import ContainerWidget
from uilib.widget import Widget
from uilib.misc import InputEvent, trace
from uilib.paint import PaintContext, _pg_rect

#
# Note about coordinates:
#
# PanelStack "box" is relative to the LCD
# Panel "box" is relative to the panelstack origin
# Widget "box" is relative to the panel etc..
#


class Panel(ContainerWidget):
    """A Panel. Holds widgets, tracks selectable items, can be pushed onto a PanelStack."""

    def __init__(self, auto_destroy=False, decorator=None, no_dim=False, accepts_input=True, **kwargs):
        self.sel_list = []
        self.sel_ref = None  # currently-selected leaf widget (resolved via sel_children)
        self.auto_destroy = auto_destroy
        self.no_dim = no_dim
        self.accepts_input = accepts_input
        if decorator:
            self.decorator = decorator(self)
        else:
            self.decorator = None
        super(Panel, self).__init__(**kwargs)

    def sel_children(self):
        """Expand this panel's sel_list entries into a flat list of leaf widgets."""
        flat = []
        for entry in self.sel_list:
            flat.extend(entry.sel_children())
        return flat

    def _flat_sel(self):
        """Lazy-expand sel_list via each entry's sel_children() into a flat
        list of leaf widgets. Rebuilt on every nav — cheap for ≤30 items
        and keeps us correct when subtrees change between calls."""
        return self.sel_children()

    def del_sel_widget(self, widget):
        previously_selectable = widget.selectable
        widget.selectable = False
        if widget in self.sel_list:
            self.sel_list.remove(widget)
        flat = self._flat_sel()
        if self.sel_ref not in flat:
            self.sel_ref = None
            if flat and previously_selectable:
                self._select_widget_ref(flat[0])

    def add_sel_widget(self, widget):
        """Add a widget to the selectable list. The widget may be a leaf
        or a container that exposes its own selectables via sel_children()."""
        assert widget.visible
        if widget in self.sel_list:
            return
        self.sel_list.append(widget)
        widget.selectable = True
        if self.sel_ref is None:
            flat = self._flat_sel()
            if flat:
                self._select_widget_ref(flat[0])

    def add_widget(self, widget):
        assert widget.visible
        widget.selectable = False
        self.sel_list.append(widget)  # TODO if a widget is not selectable, adding to sel_list seems wrong

    def _select_widget_ref(self, w):
        if self.sel_ref is not None and self.sel_ref is not w:
            self.sel_ref.set_selected(False)
        self.sel_ref = w
        w.set_selected(True)

    def _notify_detach(self, widget):
        if widget in self.sel_list:
            self.del_sel_widget(widget)

    def input_event(self, event):
        if self.sel_ref is not None:
            if self.sel_ref.input_event(event):
                return True
        if event == InputEvent.LEFT:
            self.sel_prev()
            return True
        elif event == InputEvent.RIGHT:
            self.sel_next()
            return True
        return False

    def _step_sel(self, delta):
        flat = self._flat_sel()
        if not flat:
            return
        if self.sel_ref in flat:
            idx = (flat.index(self.sel_ref) + delta) % len(flat)
        else:
            idx = 0 if delta >= 0 else len(flat) - 1
        self._select_widget_ref(flat[idx])

    def sel_next(self):
        self._step_sel(1)

    def sel_prev(self):
        self._step_sel(-1)

    def sel_widget(self, w):
        flat = self._flat_sel()
        if w in flat:
            self._select_widget_ref(w)

    def attach(self, parent):
        assert isinstance(parent, PanelStack)
        super(Panel, self).attach(parent)
        if self.decorator:
            self.decorator.attach(parent)

    def detach(self):
        assert isinstance(self.parent, PanelStack)
        super(Panel, self).detach()
        if self.decorator:
            self.decorator.detach()

    def destroy(self):
        super(Panel, self).destroy()
        if self.decorator:
            self.decorator.destroy()
            del self.decorator

    def _get_panel(self):
        return self


class ShroudedPanel(Panel):
    """A Panel that overlaps underlying panels with a semi-transparent dark shroud.

    The panel does not erase its background (so underlying PanelStack content
    shows through), then darkens it with a gradient shroud, and child widgets
    are drawn on top.
    """

    def __init__(self, shroud_alpha=64, gradient_start: float | None = None, gradient_pos=1.0, **kwargs):
        # RGBA is required: shroud compositing depends on per-pixel alpha.
        # Callers cannot override this; RGB would bake alpha against black.
        kwargs["image_format"] = "RGBA"
        super(ShroudedPanel, self).__init__(**kwargs)
        self.gradient_start = gradient_start if gradient_start is not None else shroud_alpha
        self.gradient_end = shroud_alpha
        self.gradient_pos = gradient_pos
        self._shroud_surf: Optional[pygame.Surface] = None
        self._shroud_size: Optional[tuple] = None

    def _draw_erase(self, ctx: PaintContext):
        # Clear to transparent so the shroud gradient composites correctly
        # over whatever the PanelStack has underneath.
        ctx.surface.fill((0, 0, 0, 0), ctx.surface.get_clip())

    def _make_shroud(self, w: int, h: int) -> pygame.Surface:
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        end_y = max(int(h * self.gradient_pos), 1)
        for y in range(h):
            t = min(y / end_y, 1.0)
            alpha = int(self.gradient_start + t * (self.gradient_end - self.gradient_start))
            pygame.draw.line(surf, (0, 0, 0, alpha), (0, y), (w - 1, y))
        return surf

    def _draw(self, ctx: PaintContext):
        if self.gradient_start <= 0 and self.gradient_end <= 0:
            return
        w, h = ctx.width, ctx.height
        if self._shroud_surf is None or self._shroud_size != (w, h):
            self._shroud_surf = self._make_shroud(w, h)
            self._shroud_size = (w, h)
        ox, oy = ctx._f().topleft
        ctx.surface.blit(self._shroud_surf, (ox, oy))


class RoundedPanel(Panel):
    """A panel with rounded corners.

    Non-virtual panels pre-multiply the rounded mask into the cached surface
    in `_finalize_cache()` so steady-state blits are plain. Virtual panels
    apply the mask at blit time since the mask tracks the viewport (which
    moves through the tall content surface on scroll)."""

    def __init__(self, radius: int = 10, **kwargs):
        # Set radius *before* super().__init__() — ContainerWidget.__init__
        # calls _setup() which calls _build_shape_mask(); the mask builder
        # reads self.radius. The shape mask itself is populated by _setup().
        self.radius = radius
        self._shape_mask: Optional[pygame.Surface] = None
        kwargs["image_format"] = "RGBA"
        super(RoundedPanel, self).__init__(**kwargs)

    def _build_shape_mask(self) -> pygame.Surface:
        """Build the per-corner viewport-sized alpha mask for this panel's outline shape."""
        size = (int(self.box.width), int(self.box.height))
        mask = pygame.Surface(size, pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        pygame.draw.rect(mask, (255, 255, 255, 255), pygame.Rect(0, 0, size[0], size[1]), 0, border_radius=self.radius)
        return mask

    def _setup(self):
        super()._setup()
        # _setup may have just (re)allocated the backing surface; rebuild the
        # mask so it matches the current box.
        if self.surface is not None:
            self._shape_mask = self._build_shape_mask()

    def _finalize_cache(self) -> None:
        if self.virtual or self._shape_mask is None or self.surface is None:
            return
        self.surface.blit(self._shape_mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    def _blit_into(self, target_surface: pygame.Surface, local_clip: Box, dst_topleft: Tuple[int, int]) -> None:
        if not self.virtual:
            super()._blit_into(target_surface, local_clip, dst_topleft)
            return
        # Virtual: mask follows the viewport, so we composite per-blit off a
        # viewport-local view of the tall cache. local_clip may extend past
        # the surface (viewport-clamped); clip rect intersected with view.
        assert self._shape_mask is not None
        view = self._viewport_view()
        view_rect = view.get_rect()
        clip_rect = _pg_rect(local_clip).clip(view_rect)
        if clip_rect.width <= 0 or clip_rect.height <= 0:
            return
        tmp = view.subsurface(clip_rect).copy()
        tmp.blit(self._shape_mask, (0, 0), area=clip_rect, special_flags=pygame.BLEND_RGBA_MULT)
        target_surface.blit(tmp, (int(dst_topleft[0]), int(dst_topleft[1])))

    def _draw_outline(self, ctx):
        if self.outline != 0:
            color = self.outline_color if self.outline_color is not None else self.fgnd_color
            ctx.draw_rectangle(ctx.bounds, None, color, self.outline, radius=self.radius)


class LcdBase(ABC):
    def dimensions(self) -> tuple[int, int]: ...

    def default_format(self) -> str: ...

    def update(self, image, box=None) -> None: ...

    @property
    def has_system_splash(self) -> bool:
        return False


class PanelStack(ContainerWidget):
    def __init__(self, lcd, box: Optional[Box] = None, image_format: Optional[str] = None, use_dimming: bool = True):
        # XXX This implementation currently assumes box is at (0,0) in the LCD
        #     and the offset remains 0,0 (don't try to scroll)
        if box is None:
            box = Box((0, 0), lcd.dimensions())
        if image_format is None:
            image_format = lcd.default_format()
        if use_dimming:
            image_format = "RGBA"

        trace(self, "Panel stack initializing with box=", box)
        super(PanelStack, self).__init__(box=box, image_format=image_format)
        self.stack = []
        self.current = None
        self.lcd = lcd
        self.visible = True
        if use_dimming:
            size = (int(box.width), int(box.height))
            self.dimmer: Optional[pygame.Surface] = pygame.Surface(size, pygame.SRCALPHA)
            self.dimmer.fill((0, 0, 0, 64))
        else:
            self.dimmer = None

        # We don't have a parent, establish all the defaults
        self._setup_act_attrs()
        self._setup()

        self.lcd_needs_update = False
        self._pending_lcd_clip: Optional[Box] = None  # None = full screen or nothing pending
        self.capture_callback = None

    def poll_updates(self):
        if self.lcd_needs_update:
            self._flush_lcd()

    def _flush_lcd(self):
        """Compose the pending dirty region and push to the LCD in one transfer.

        ``_pending_lcd_clip`` semantics:
          * Box       — compose that clip (if not already composed) and push it
          * None      — full screen: compose everything, push full screen
        """
        assert self.surface is not None
        clip = self._pending_lcd_clip
        if clip is None:
            clip = self.box.norm()
            self.propagate_dirty(clip)
        self.lcd.update(self.surface, clip)
        self._pending_lcd_clip = None
        self.lcd_needs_update = False

    def set_capture_callback(self, callback):
        self.capture_callback = callback

    def refresh(self, box=None):
        clip = self.box.norm() if box is None else box
        self.propagate_dirty(clip)
        self.lcd.update(self.surface, clip)
        self._pending_lcd_clip = None
        self.lcd_needs_update = False

    @override
    def propagate_dirty(self, local_clip: Box):
        """Recompose the dirty clip region from all stacked panels.

        Composes the panels into the root surface immediately (cheap
        memory-to-memory blits) but defers the LCD push.
        """
        assert self.surface is not None
        clip = local_clip
        erase_ctx = PaintContext(self.surface, clip, frame=clip)
        self._draw_erase(erase_ctx)

        for p in self.stack:
            if self.dimmer is not None and not p.no_dim:
                self.surface.blit(self.dimmer, clip.topleft, area=_pg_rect(clip))
            d = p.decorator
            if d is not None:
                inter = clip.intersection(d.box)
                if not inter.is_empty():
                    ctx = PaintContext(self.surface, inter)
                    d.do_draw(ctx, d.box)
            inter = clip.intersection(p.box)
            if not inter.is_empty():
                ctx = PaintContext(self.surface, inter)
                p.do_draw(ctx, p.box)

        trace(self, "deferring lcd update for surface", self.surface, "box=", clip)

        if self.capture_callback:
            self.capture_callback(self.surface)

        # Union this clip into the pending LCD push instead of pushing now.
        # None means a full-screen redraw is pending (from push/pop) — don't
        # shrink it back to a partial clip.
        if self._pending_lcd_clip is not None:
            self._pending_lcd_clip = self._pending_lcd_clip.union(clip)
        self.lcd_needs_update = True

    def do_draw(self, ctx: PaintContext, frame: Box):
        assert False

    def _get_stack(self):
        return self

    def push_panel(self, panel, refresh=True):
        assert panel not in self.stack
        assert isinstance(panel, Panel)

        # Check if we haven't been attached yet
        if panel.parent is None:
            panel.attach(self)
        self.stack.append(panel)
        # Input target: skip non-input panels
        if panel.accepts_input:
            self.current = panel
        panel.show(refresh=False)
        if refresh:
            self.refresh()
        else:
            # Stack changed structurally; force full-screen redraw on next flush.
            self._pending_lcd_clip = None
            self.lcd_needs_update = True

    def pop_panel(self, panel):
        if panel is None:
            panel = self.current
        assert panel is not None and panel in self.stack
        self.stack.remove(panel)
        panel.hide(refresh=False)
        if panel == self.current:
            # Walk backwards past non-input panels to find the new input target
            current = None
            for p in reversed(self.stack):
                if p.accepts_input:
                    current = p
                    break
            self.current = current
        self._pending_lcd_clip = None  # force full-screen redraw on next flush
        self.lcd_needs_update = True
        if panel.auto_destroy:
            panel.destroy()

    def find_panel_type(self, type):
        for p in self.stack:
            if isinstance(p, type):
                return p
        return None

    def input_event(self, event):
        assert isinstance(event, InputEvent)
        if self.current is not None:
            return self.current.input_event(event)
        return False


class PanelDecorator(Widget):
    def __init__(self, panel, **kwargs):
        self.panel = panel
        # Default box, will be updated by subclass
        kwargs["box"] = Box(0, 0, 0, 0)
        super(PanelDecorator, self).__init__(**kwargs)
