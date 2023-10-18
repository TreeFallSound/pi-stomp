from uilib.container import *

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
                # XXX Maybe be smarter at picking up a new item
                if previously_selectable:
                    self._select_widget_idx(0)
        
    def add_sel_widget(self, widget):
        """Add a widget to the selectable list"""
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
    def __init__(self, radius = 10, **kwargs):
        if 'mask_format' not in kwargs:
            kwargs['mask_format'] = '1'
        super(RoundedPanel,self).__init__(**kwargs)
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

class LcdBase:
    def dimensions(self):
        pass

    def default_format(self):
        pass

    def update(self, image, box = None):
        pass

class PanelStack(ContainerWidget):
    def __init__(self, lcd, box = None, image_format = None, use_dimming = True):
        # XXX This implementation currently assumes box is at (0,0) in the LCD
        #     and the offset remains 0,0 (dont' try to scroll)
        if box is None:
            box = Box((0,0), lcd.dimensions())
        if image_format is None:
            image_format = lcd.default_format()

        trace(self, "Panel stack initializing with box=", box)
        # Dimming, when enabled, causes panels below the frontmost one to
        # be "dimmed" (the further back the more they get dimmed)
        if use_dimming:
            image_format = 'RGBA'
        super(PanelStack,self).__init__(box = box, image_format = image_format)
        self.stack = []
        self.current = None
        self.lcd = lcd
        self.visible = True
        if use_dimming:
            size = (box.width, box.height)
            self.dimmer = Image.new('RGBA', size, (0,0,0,128))
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
            if self.dimmer is not None:
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
                super(PanelStack,self)._compose(p, local_inter, inter)

        # Update LCD
        trace(self, "updating lcd with image", self.image, "box=", box)
        self.lcd.update(self.image, box)

    def _do_draw(self, image, draw, real_box):
        assert(False)
        
    def _get_stack(self):
        return self

    def push_panel(self, panel):
        assert panel not in self.stack
        assert isinstance(panel, Panel)

        # Check if we haven't been attached yet
        if panel.parent == None:
            panel.attach(self)
        self.stack.append(panel)
        # Input target
        self.current = panel
        panel.show(refresh = False)
        self.refresh()

    def pop_panel(self, panel):
        assert panel in self.stack
        self.stack.remove(panel)
        panel.hide(refresh = False)
        if panel == self.current:
            if len(self.stack) == 0:
                current = None
            else:
                current = self.stack[-1]
            self.current = current
        # queue a refresh
        self.lcd_needs_update = True
        if panel.auto_destroy:
#            panel.detach()
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
        kwargs['box'] = Box(0,0,0,0)
        super(PanelDecorator,self).__init__(**kwargs)

