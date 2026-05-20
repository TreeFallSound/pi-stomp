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

from typing import Optional

import pygame

from uilib.container import *
from uilib.paint import PaintContext

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

    The rounded shape is stored as a separate alpha mask surface and applied
    at blit time (BLEND_RGBA_MULT), exactly the way the old PIL implementation
    used a mode='1' bitmap with paste(mask=…). This means children that happen
    to paint into the corner regions don't leak past the rounded edge."""

    def __init__(self, radius: int = 10, **kwargs):
        kwargs['image_format'] = 'RGBA'
        super(RoundedPanel, self).__init__(**kwargs)
        self.radius = radius
        self._shape_mask: Optional[pygame.Surface] = None
        self._build_shape_mask()

    def _build_shape_mask(self) -> None:
        # Mask is viewport-sized, not surface-sized. For virtual containers the
        # surface is content_height tall, but the rounded corners must appear
        # at the viewport edges (which is what _blit_into addresses via
        # viewport-relative local_clip).
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

    def _blit_into(self, target_surface: pygame.Surface, local_clip, dst_topleft) -> None:
        """Blit the rounded slice into the parent.

        Composite our pixels onto a small SRCALPHA scratch, multiply by the
        shape mask's matching sub-rect, then blit the result. Cost scales with
        the dirty rect, not the full panel — fast incremental updates remain
        fast."""
        assert self.surface is not None
        assert self._shape_mask is not None
        from uilib.paint import _pg_rect
        src_box = local_clip.offset(self.offset)
        src_rect = _pg_rect(src_box)
        mask_rect = _pg_rect(local_clip)
        tmp = pygame.Surface((src_rect.width, src_rect.height), pygame.SRCALPHA)
        tmp.blit(self.surface, (0, 0), area=src_rect)
        tmp.blit(self._shape_mask, (0, 0), area=mask_rect, special_flags=pygame.BLEND_RGBA_MULT)
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
    _skip_cache_push = True

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
                from uilib.paint import _pg_rect
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
