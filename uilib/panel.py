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

import pygame

from uilib.box import Box
from uilib.container import *
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
    def __init__(self, auto_destroy = False, decorator = None, **kwargs):
        self.sel_list = []
        self.sel = None
        self.auto_destroy = auto_destroy
        if decorator:
            self.decorator = decorator(self)
        else:
            self.decorator = None
        super(Panel,self).__init__(**kwargs)

    def del_sel_widget(self, widget):
        if self.sel is None or self.sel_list[self.sel] == widget:
            old_sel = None
        else:
            old_sel = self.sel_list[self.sel]
        previously_selectable = widget.selectable
        widget.selectable = False
        self.sel_list.remove(widget)
        if old_sel is not None:
            self.sel = self.sel_list.index(old_sel)
        else:
            self.sel = None
            if len(self.sel_list) != 0:
                if previously_selectable:
                    self._select_widget_idx(0)

    def add_sel_widget(self, widget):
        assert(widget.visible)
        self.sel_list.append(widget)
        widget.selectable = True
        if self.sel is None:
            self._select_widget_idx(0)

    def add_widget(self, widget):
        assert(widget.visible)
        widget.selectable = False
        self.sel_list.append(widget)  # TODO if a widget is not selectable, adding to sel_list seems wrong

    def _select_widget_idx(self, idx):
        if self.sel is not None:
            old = self.sel_list[self.sel]
            old.set_selected(False)
        self.sel = idx
        new = self.sel_list[idx]
        new.set_selected(True)

    def _notify_detach(self, widget):
        if widget in self.sel_list:
            self.del_sel_widget(widget)

    def input_event(self, event):
        if self.sel is not None:
            w = self.sel_list[self.sel]
            if w.input_event(event):
                return True
        if event == InputEvent.LEFT:
            self.sel_prev()
            return True
        elif event == InputEvent.RIGHT:
            self.sel_next()
            return True
        return False

    def sel_next(self):
        if len(self.sel_list) == 0:
            return
        if self.sel is None:
            new_sel = 0
        else:
            new_sel = (self.sel + 1) % len(self.sel_list)
        self._select_widget_idx(new_sel)

    def sel_prev(self):
        if len(self.sel_list) == 0:
            return
        if self.sel is None:
            new_sel = len(self.sel_list) - 1
        else:
            new_sel = (self.sel - 1) % len(self.sel_list)
        self._select_widget_idx(new_sel)

    def sel_widget(self, w):
        i = self.sel_list.index(w)
        self._select_widget_idx(i)

    def attach(self, parent):
        assert isinstance(parent, PanelStack)
        super(Panel,self).attach(parent)
        if self.decorator:
            self.decorator.attach(parent)

    def detach(self):
        assert isinstance(self.parent, PanelStack)
        super(Panel,self).detach()
        if self.decorator:
            self.decorator.detach()

    def destroy(self):
        super(Panel,self).destroy()
        if self.decorator:
            self.decorator.destroy()
            del self.decorator

    def _get_panel(self):
        return self


class RoundedPanel(Panel):
    """A panel with rounded corners.

    Non-virtual panels pre-multiply the rounded mask into the cached surface
    in `_finalize_cache()` so steady-state blits are plain. Virtual panels
    apply the mask at blit time since the mask tracks the viewport (which
    moves through the tall content surface on scroll)."""

    def __init__(self, radius: int = 10, **kwargs):
        kwargs['image_format'] = 'RGBA'
        super(RoundedPanel, self).__init__(**kwargs)
        self.radius = radius
        self._shape_mask: Optional[pygame.Surface] = None
        self._build_shape_mask()

    def _build_shape_mask(self) -> None:
        # Mask is viewport-sized. For virtual panels the cache surface is
        # content_height tall and the mask is re-applied at blit time at the
        # current viewport offset.
        size = (int(self.box.width), int(self.box.height))
        mask = pygame.Surface(size, pygame.SRCALPHA)
        mask.fill((0, 0, 0, 0))
        pygame.draw.rect(mask, (255, 255, 255, 255),
                         pygame.Rect(0, 0, size[0], size[1]), 0,
                         border_radius=self.radius)
        self._shape_mask = mask

    def _setup(self):
        super()._setup()
        # Rebuild the mask if the backing surface was just (re)allocated.
        if getattr(self, "radius", None) is not None and self.surface is not None:
            self._build_shape_mask()

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


class LcdBase:
    def dimensions(self):
        pass

    def default_format(self):
        pass

    def update(self, image, box=None):
        pass

    @property
    def has_system_splash(self) -> bool:
        return False


class PanelStack(ContainerWidget):
    def __init__(self, lcd, box: Optional[Box] = None, image_format: Optional[str] = None, use_dimming: bool = True):
        # XXX This implementation currently assumes box is at (0,0) in the LCD
        #     and the offset remains 0,0 (don't try to scroll)
        if box is None:
            box = Box((0,0), lcd.dimensions())
        if image_format is None:
            image_format = lcd.default_format()
        if use_dimming:
            image_format = 'RGBA'

        trace(self, "Panel stack initializing with box=", box)
        super(PanelStack,self).__init__(box=box, image_format=image_format)
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

    def poll_updates(self):
        if self.lcd_needs_update:
            self.refresh()

    def refresh(self):
        self.propagate_dirty(self.box.norm())
        self.lcd_needs_update = False

    def propagate_dirty(self, local_clip: Box):
        """Recompose the dirty clip region from all stacked panels, then push to LCD."""
        assert self.surface is not None
        clip = local_clip
        erase_ctx = PaintContext(self.surface, clip, frame=clip)
        self._draw_erase(erase_ctx)

        for p in self.stack:
            if self.dimmer is not None:
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

        trace(self, "updating lcd with surface", self.surface, "box=", clip)
        self.lcd.update(self.surface, clip)

    def do_draw(self, ctx: PaintContext, frame: Box):
        assert False

    def _get_stack(self):
        return self

    def push_panel(self, panel, refresh=True):
        assert panel not in self.stack
        assert isinstance(panel, Panel)

        if panel.parent is None:
            panel.attach(self)
        self.stack.append(panel)
        self.current = panel
        panel.show(refresh=False)
        if refresh:
            self.refresh()

    def pop_panel(self, panel):
        if panel is None:
            panel = self.current
        assert panel in self.stack
        self.stack.remove(panel)
        panel.hide(refresh=False)
        if panel == self.current:
            if len(self.stack) == 0:
                current = None
            else:
                current = self.stack[-1]
            self.current = current
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
        kwargs['box'] = Box(0,0,0,0)
        super(PanelDecorator,self).__init__(**kwargs)
