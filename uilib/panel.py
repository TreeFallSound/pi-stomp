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

from PIL import ImageDraw, Image

from uilib.box import Box
from uilib.container import ContainerWidget
from uilib.misc import InputEvent, trace
from uilib.widget import Widget
from abc import ABC

#
# Note about coordinates:
#
# PanelStack "box" is relative to the LCD
# Panel "box" is relative to the panelstack origin
# Widget "box" is relative to the panel etc..
#


class Panel(ContainerWidget):
    """A Panel. This is kind of a 'window' in the traditional sense and holds
    a bunch of widgets. It also can track selectable widgets and can be
    placed into a PanelStack
    """

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
        assert(widget.visible)
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

    The panel's own backing image is transparent, so whatever the PanelStack
    has already composited shows through — then the shroud darkens it, and
    child widgets are drawn on top of the shroud.
    """

    def __init__(self, shroud_alpha=64, gradient_start: float | None = None, gradient_pos=1.0, **kwargs):
        if "image_format" not in kwargs:
            kwargs["image_format"] = "RGBA"
        super(ShroudedPanel, self).__init__(**kwargs)
        self.gradient_start = gradient_start if gradient_start is not None else shroud_alpha
        self.gradient_end = shroud_alpha
        self.gradient_pos = gradient_pos
        self._shroud = None

    def _draw_erase(self, image, draw, box):
        # Bypass inherited bkgnd_color (which would be opaque RGB); PIL draws
        # RGBA (0,0,0,0) as truly transparent on RGBA images.
        draw.rectangle(box.PIL_rect, (0, 0, 0, 0))

    def _make_shroud(self):
        w, h = self.image.size
        shroud = Image.new("RGBA", (w, h))
        end_y = max(int(h * self.gradient_pos), 1)
        for y in range(h):
            t = min(y / end_y, 1.0)
            alpha = int(self.gradient_start + t * (self.gradient_end - self.gradient_start))
            shroud.paste((0, 0, 0, alpha), (0, y, w, y + 1))
        return shroud

    def _do_draw(self, image, draw, real_box):
        # Clear to transparent so the underlying PanelStack content shows through
        self._draw_erase(image, draw, real_box)
        # Lay shroud down before children so widgets appear on top of it
        # can skip if the gradient is fully transparent
        if self.gradient_start > 0 or self.gradient_end > 0:
            if self._shroud is None or self._shroud.size != self.image.size:
                self._shroud = self._make_shroud()
            self.image.alpha_composite(self._shroud)
        # Draw children on top of the shroud
        off_real_box = real_box.deoffset(self.offset)
        self._draw(image, draw, off_real_box)
        for c in self.children:
            crb = c.box.offset(off_real_box)
            c._do_draw(image, draw, crb)
        self._draw_outline(image, draw, real_box)
        self._draw_selection(image, draw, real_box)
        if image is not self.image:
            image.paste(self.image, real_box.rect)


class RoundedPanel(Panel):
    def __init__(self, radius=10, **kwargs):
        if "mask_format" not in kwargs:
            kwargs["mask_format"] = "1"
        super(RoundedPanel, self).__init__(**kwargs)
        self.radius = radius

        # Setup mask plans
        mdraw = ImageDraw.Draw(self.mask)
        mdraw.rounded_rectangle(self.box.norm().PIL_rect, radius, 1, None, 0)

    def _draw_outline(self, image, draw, real_box):
        if self.outline != 0:
            if self.outline_color is not None:
                color = self.outline_color
            else:
                color = self.fgnd_color
            draw.rounded_rectangle(real_box.PIL_rect, self.radius, None, color, self.outline)


class LcdBase(ABC):
    def dimensions(self) -> tuple[int, int]: ...

    def default_format(self) -> str: ...

    def update(self, image, box=None) -> None: ...

    @property
    def has_system_splash(self) -> bool:
        return False


class PanelStack(ContainerWidget):
    def __init__(self, lcd, box=None, image_format=None, use_dimming=True):
        # XXX This implementation currently assumes box is at (0,0) in the LCD
        #     and the offset remains 0,0 (dont' try to scroll)
        if box is None:
            box = Box((0, 0), lcd.dimensions())
        if image_format is None:
            image_format = lcd.default_format()

        trace(self, "Panel stack initializing with box=", box)
        # Dimming, when enabled, causes panels below the frontmost one to
        # be "dimmed" (the further back the more they get dimmed)
        if use_dimming:
            image_format = "RGBA"
        super(PanelStack, self).__init__(box=box, image_format=image_format)
        self.stack = []
        self.current = None
        self.lcd = lcd
        self.visible = True
        if use_dimming:
            size = (box.width, box.height)
            self.dimmer = Image.new("RGBA", size, (0, 0, 0, 64))
        else:
            self.dimmer = None

        # We don't have a parent, establish all the defaults
        self._setup_act_attrs()
        self._setup()

        self.lcd_needs_update = False

    def poll_updates(self):
        if self.lcd_needs_update:
            self.refresh()

    def _compose(self, widget, orig_box, real_box):
        # This always called with widget = a Panel which is a direct
        # child of the stack, so we can drop orig_box
        real_box = real_box.intersection(self.box.norm())
        if not real_box.is_empty():
            self._do_refresh(widget, real_box)

    def refresh(self):
        self._do_refresh(None, self.box)
        self.lcd_needs_update = False

    def _do_refresh(self, panel, box):
        # XXX TODO: Optimize the case where there is only one panel,
        # or the refreshed box only intersects the top level one:
        # go straight to LCD ! (If we want to do stacked panels with
        # alpha this can get complicated...)

        # Erase image
        self._draw_erase(self.image, self.draw, box)

        # XXX Do some alpha blending to "dim" inactive panels ?

        # Compose panels
        for p in self.stack:
            if self.dimmer is not None and not p.no_dim:
                self.image.alpha_composite(self.dimmer, box.topleft, box.rect)
            d = p.decorator
            if d is not None:
                inter = box.intersection(d.box)
                if not inter.is_empty():
                    d.refresh(inter)
            inter = box.intersection(p.box)
            if not inter.is_empty():
                # Get intersection in panel local coordinates
                local_inter = inter.deoffset(p.box)
                super(PanelStack, self)._compose(p, local_inter, inter)

        # Update LCD
        trace(self, "updating lcd with image", self.image, "box=", box)
        self.lcd.update(self.image, box)

    def _do_draw(self, image, draw, real_box):
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

    def pop_panel(self, panel):
        # panel == None is a special case meaning just pop the current panel
        if panel is None:
            panel = self.current
        assert panel in self.stack
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
        # queue a refresh
        self.lcd_needs_update = True
        if panel.auto_destroy:
            # panel.detach()
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
