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

from typing import TYPE_CHECKING, Optional, Tuple

from uilib.box import Box
from uilib.misc import InputEvent, WidgetAlign, trace
from uilib.paint import PaintContext

if TYPE_CHECKING:
    from uilib.container import ContainerWidget
    from uilib.panel import PanelStack

# This is the root of all evil: the Widget class, parent of all things
# displayed on the screen.
#
# Note about attribute inheritance:
#
# Some attributes (mostly colors) can be inherited from the parent by not
# specifying them (or specifying them as None).
#
# For performance reason, this "parent lookup" is done when the widget is
# visible *and* is attached to a parent and cached. A widget can be attached
# when created (via the parent constructor argument) or attached later via
# the attach() method.
#
# A widget visibility is controlled by its hide() and show() method. A widget
# can only be made visible if it's bounding box has been established (non-None)
#
# This means that the order in which you create the widget hierarchy matters,
# for example, if you create a widget C child of B, and later attach B to A,
# while you have A -> B -> C hierarchy, C will only inherit from B not from A
# unless C was invisible and only show()'n later.
#
# If no value is found in the parent, built-in defaults will be used
#
# For this to work, a subclass must call _init_attrs() **before** it calls
# super().__init__. This will ensure all attributes for the various subclasses
# are properly registered before Widget.__init__ adds the last ones and performs
# the initial parent inheritance.
#
# Note: "box" is an optional attribute at creation time. A widget without a box
# will start as invisible. A caller must then call Widget.set_box() and
# Wiget.show() later on to establish the bounding box and make it visible.
#

## TODO (in addition to the ones sprinkled in the code)
#
# - Consider clipping/cropping... this will be limited since we
#   can't really set clip rectangles in Pillow. Currently child that
#   go over the bounds of their parents are going to just do that...
#   with the resulting ugly consequences. There's an assumption that
#   widgets are well-behaved when it comes to boundaries. At least
#   when it comes to ContainerWidgets, we can (and somewhat do) do
#   something about it, but that's about it...
#
# - Placement / sizing. Do we want "auto-placement" ? Do we want a way to
#   represent things in term of percentile ? Or location of objects
#   relative to another object ? Or size relative to content (ie,
#   text widget size inherited from font) etc... ? This could lead to
#   more versatile layout for various screen sizes, but will be
#   harder to properly define.
#


class Widget:
    """Base Widget class, base of all UI element"""

    # Inherited attributes with defaults
    INH_ATTRS = {
        "bkgnd_color": (0, 0, 0),
        "fgnd_color": (255, 255, 255),
        "sel_color": (255, 255, 0),
        "sel_width": 2,
        "sel_radius": None,
    }

    def __init__(self, box: Box, align=None, parent=None, visible=True, object=None, **kwargs):
        """box    : Box object relative to parent
        parent : parent widget
        """
        assert box is None or isinstance(box, Box)
        assert parent is None or isinstance(parent, Widget)
        assert align is None or isinstance(align, WidgetAlign)
        if align is None:
            align = WidgetAlign.NONE

        # By default, force invisible if no box set. The caller will need to both
        # set a box *and* call widget.show()
        if box is None:
            self.visible = False
            self.box = None
        else:
            self.box = box.copy()
            self.visible = visible
        self.align = align
        self.children = []
        self.parent = None
        self.object = object
        self.selected = False
        self.selectable = False
        self._painted = False
        self._dirty = False

        # Non-inherited attributes
        self.label = self._get_arg(kwargs, "label", None)
        self.outline = self._get_arg(kwargs, "outline", 0)
        self.outline_radius = self._get_arg(kwargs, "outline_radius", None)
        self.outline_color = self._get_arg(kwargs, "outline_color", None)
        self.action = self._get_arg(kwargs, "action", None)

        # Inheritable attributes
        #
        # XXX REPLACE INH_ATTRS with Config() defaults
        self._init_attrs(Widget.INH_ATTRS, kwargs)

        trace(self, "Widget.__init__: vis=", self.visible, "parent=", parent)

        # Finally attach to parent if requested
        if parent is not None:
            self.attach(parent)

    # uncomment to verify we aren't leaking widgets
    def __del__(self):
        trace(self, "Debug deletion")

    @staticmethod
    def _get_arg(args, key, default):
        if key in args:
            return args[key]
        return default

    def _init_attrs(self, defaults, args):
        # This might be called before those were initialized:
        if not hasattr(self, "default_attrs"):
            self.default_attrs = {}
            self.explicit_attrs = {}

        # Merge default attrs
        self.default_attrs.update(defaults)

        # Add explicit ones if they exist in defaults (ie. are known attributes)
        for k in args:
            if k in self.default_attrs:
                self.explicit_attrs[k] = args[k]

    def _setup_act_attrs(self):
        # Now for any attribute we know of (defaults acts as that list)
        # figure out what value to use:
        for k in self.default_attrs:
            # If we don't already have a value for it
            if k in self.explicit_attrs and self.explicit_attrs[k] is not None:
                val = self.explicit_attrs[k]
            else:
                # Does the parent have one ? Use it, otherwise use default
                if self.parent is not None and hasattr(self.parent, k) and getattr(self.parent, k) is not None:
                    val = getattr(self.parent, k)
                else:
                    val = self.default_attrs[k]

            # This is somewhat evil but makes it easier to move attributes back
            # and forth between being "inherited" vs. not and avoids me changing
            # too much code :-)
            # It also allows children to inherit from attributes that aren't
            # marked 'inheritable'
            setattr(self, k, val)

    # Notes about drawing mechanisms
    #
    # Widgets rely on a parent having a backing image. Typically an instance of
    # ContainerWidget (such as a Panel).
    #
    # The main method for a widget subclass to override is the _draw() method.
    #
    # It takes as arguments the image to draw into, an ImageDraw instance for
    # that image (handy heh ?) and a Box instance which is bounds of the widget
    # in image coordinates (ie, with the appropriate offset applied based on
    # the location of the parent(s) of the widget).
    #
    # A widget can be refreshed explicitely by an external caller using the
    # widget's refresh() method. This will reach out to parents via _focus() and
    # _unfocus() to get the backing image and the right offset, allowing the widget
    # to redraw itself.
    #
    # As part of that process, a widget will also redraw all of its children if any,
    # which are going to draw their own children etc... via a chain of calls
    # to _do_draw().
    #
    # Note: The widget's _draw() method doesn't need to consider children, these
    # will be handled by the framework, so will be erasing of the backing prior
    # to drawing and the drawing of a boundary box and/or selection rectangle if
    # requested.
    #
    # refresh() is thus a complete redraw of a Widget and all of its children,
    # it's typically used after creating and populating a panel, or when updating
    # the content of an individual widget
    #
    # Another path through the object hierarchy is the slightly more complicated
    # _compose() path. _compose() is called by a ContainerWidget on its parent
    # when itself or one of its children have been updated. For example, a
    # ContainerWidget()'s _unfocus() calls the parent's _compose(). This is
    # specifically meant to "compose" the child Image into the parent Image (a
    # non-ContainerWidget parent will just pass "compose" up until it reaches
    # a ContainerWidget). This is an optimisation which allows only the portion
    # of the Image that was modified to be updated. This is very important on
    # SPI LCD displays where the refresh time can be very long if we try to
    # refresh too large regions.
    #
    # A Panel is basically a ContainerWidget subclass along with a mechanism
    # to handle "selection" of widgets (via a list of selectable widgets) and
    # which can be pushed onto a PanelStack.
    #
    # A PanelStack is the top of the graphical hierarchy and links panel(s) and
    # the LCD display. It "composes" the panels in the stack on top of each other
    # and routes user input to the current top-level panel. It is currently
    # a subclass of ContainerWidget but that might not always remain the case and
    # shouldn't be relied upon
    #
    # Note: Panels are always linked to a stack in order to be able to inherit
    # some attributes and for features like centering to work, as the bounding
    # box is established early and thus rely on the stack bounding box. When a
    # panel is popped off the stack, it still keeps its reference to said stack

    def _build_paint_target(self, dirty: Box) -> Tuple["ContainerWidget", Box, Box] | Tuple[None, None, None]:
        """Walk up to the nearest ContainerWidget, accumulating frame offset.

        Returns (container, frame, clip) where:
          container : the nearest ContainerWidget ancestor (owns the image)
          frame     : self.box translated into container-local coords
          clip      : dirty translated into container-local coords, clipped to container bounds
        Returns (None, None, None) if no visible ContainerWidget ancestor found.
        """
        from uilib.container import ContainerWidget

        off_x, off_y = 0, 0
        curr = self
        while curr is not None:
            if not curr.visible:
                return None, None, None
            
            off_x += curr.box.x0
            off_y += curr.box.y0
            
            parent = curr.parent
            if isinstance(parent, ContainerWidget):
                # We found our backing image owner.
                # frame = where we are in container local coords
                frame = Box.xywh(off_x, off_y, self.box.width, self.box.height)
                # clip = the dirty region re-anchored to the same container coords
                clip = dirty.offset((off_x - self.box.x0, off_y - self.box.y0))
                return (parent, frame, clip.intersection(parent._content_bounds()))
                
            curr = parent
            
        return (None, None, None)

    def _invalidate_self(self):
        """Mark this widget's own region stale and bubble it up."""
        self._dirty = True
        if self.parent is not None and self.box is not None:
            self.parent._invalidate_cache(self.box)

    def set_outline(self, width, color=None):
        self.outline = width
        self.outline_color = color
        self._invalidate_self()

    def set_selected(self, selected):
        if self.selected is not selected:
            self.selected = selected
            self._dirty = True
        if selected:
            if self.scroll_into_view():
                # Don't refresh if scroll has made it happen
                return
        self.refresh()

    def set_background(self, color):
        self.bkgnd_color = color
        self._invalidate_self()

    def set_foreground(self, color):
        self.fgnd_color = color
        self._invalidate_self()

    def set_action(self, action):
        self.action = action

    def show(self, refresh=True):
        """Make a widget visible"""
        if not self.visible:
            trace(self, "show ! refresh=", refresh)
            assert self.box is not None
            assert self.parent is not None
            self.visible = True
            if self.parent is not None:
                self._setup_act_attrs()
                self._setup()
        if refresh:
            self.refresh()

    def hide(self, refresh=True):
        """Make a widget invisible"""
        if self.visible:
            self.visible = False
            if refresh:
                self.parent.refresh()

    def set_box(self, box, realign=False, refresh=True):
        """Change/set a widget box"""
        old_visible = self.visible
        if box is None:
            self.visible = False
            self.box = None
        else:
            self.box = box.copy()
            if realign:
                self._adjust_box()
        trace(self, "box set to", str(self.box))
        if refresh and old_visible and self.parent:
            self.parent.refresh()

    def get_box(self, box):
        """Return a widget boundary box"""
        return self.box

    def get_object(self):
        return self.object

    def attach(self, parent):
        """Attach a widget to a parent"""
        trace(self, "attaching to parent", parent)
        assert self.parent is None
        self.parent = parent
        self.parent.children.append(self)
        if self.visible:
            self._setup_act_attrs()
            self._setup()
        parent._invalidate_cache()

    def detach(self):
        """Detach a widget from the parent"""
        trace(self, "Widget detach, parent=", self.parent)
        if self.parent is not None:
            parent = self.parent
            self.parent.children.remove(self)
            self.parent._notify_detach(self)
            self.parent = None
            parent._invalidate_cache()

    def _invalidate_cache(self, box=None):
        """Bubble cache invalidation up. Containers override to accumulate
        a dirty region before bubbling further. `box` is in self-local coords
        (or None ⇒ fully invalidate)."""
        if self.parent is not None:
            self.parent._invalidate_cache(box)

    def _adjust_box(self):
        trace(self, "adjusting box, parent=", self.parent)
        # We can only do this if we have a parent
        if self.parent is None:
            return
        if self.align & WidgetAlign.CENTRE_H:
            if self.box.width >= self.parent.box.width:
                self.box.x0 = 0
                self.box.x1 = self.parent.box.width
            else:
                w = self.box.width
                off = (self.parent.box.width - w) / 2
                self.box.x0 = off
                self.box.x1 = off + w
        if self.align & WidgetAlign.CENTRE_V:
            if self.box.height >= self.parent.box.height:
                self.box.y0 = 0
                self.box.y1 = self.parent.box.height
            else:
                h = self.box.height
                off = (self.parent.box.height - self.box.height) / 2
                self.box.y0 = off
                self.box.y1 = off + h
        trace(self, "adjusted box=", self.box)

    def _setup(self):
        """Setup the widget once attached to a parent"""
        # This is called after all the inherited attributes have been establishe
        self._adjust_box()

    # Because of the parent/children cross references, widgets tend to live forever,
    # this will properly get rid of them by killing the entire reference hierarchy
    def destroy(self):
        """Destroy a widget hierarchy"""
        while len(self.children) > 0:
            self.children[0].detach()
        self.detach()

    def _notify_detach(self, widget):
        if self.parent:
            self.parent._notify_detach(widget)

    def refresh(self, box=None):
        """Refresh widget (and children).

        SDL clipping (set in PaintContext.painting) keeps any out-of-frame
        primitives from leaking past the widget's frame, so we draw straight
        into the container's surface — no temp buffer.
        """
        trace(self, "Widget.refresh: vis=", self.visible, "parent=", self.parent)
        if self.parent is None or not self.visible:
            return
        if box is None:
            box = self.box
        if box is None:
            return
        container, frame, clip = self._build_paint_target(box)
        if container is None:
            return
        if clip.is_empty():
            return
        if container.virtual and not container._viewport().intersects(frame):
            self._dirty = True
            return
        ctx = PaintContext(container.surface, clip, frame=frame)
        self.do_draw(ctx, frame)
        self._painted = True
        self._dirty = False
        container.propagate_dirty(clip)

    def scroll_into_view(self):
        """Scroll parent if necessary to ensure this object is into view. Only works
           on a visible object attached to a parent
        """
        if self.visible and self.parent:
            return self.parent._scroll_into_view(self.box)
        return False

    def _scroll_into_view(self, box):
        if self.visible and self.parent:
            return self.parent._scroll_into_view(box.offset(self.box))
        return False

    def do_draw(self, ctx: PaintContext, frame: Box):
        """Draw self and children. frame is self's rect in ctx.image coords."""
        if ctx.clip.intersection(frame).is_empty():
            return
        with ctx.painting(frame) as pctx:
            assert pctx.frame is not None
            self._draw_erase(pctx)
            self._draw(pctx)
            child_origin = pctx.frame.topleft
            for c in self.children:
                if c.visible:
                    c.do_draw(pctx, c.box.offset(child_origin))
            self._draw_outline(pctx)
            self._draw_selection(pctx)

    def _draw_erase(self, ctx: PaintContext):
        erase = ctx.dirty_bounds
        if erase.is_empty():
            return
        if self.outline_radius is not None and erase == ctx.bounds:
            ctx.draw_rectangle(ctx.bounds, fill=self.bkgnd_color, radius=self.outline_radius)
        else:
            ctx.draw_rectangle(erase, fill=self.bkgnd_color)

    def _draw_outline(self, ctx: PaintContext):
        if self.outline != 0:
            color = self.outline_color if self.outline_color is not None else self.fgnd_color
            ctx.draw_rectangle(ctx.bounds, None, color, self.outline, radius=self.outline_radius)

    def _draw_selection(self, ctx: PaintContext):
        if self.selected:
            radius = self.sel_radius
            if radius is None:
                radius = self.outline_radius
            if radius == 0:
                radius = None
            ctx.draw_rectangle(ctx.bounds, None, self.sel_color, self.sel_width, radius=radius)

    def _draw(self, ctx: PaintContext):
        pass

    def sel_children(self):
        """Selection-tree expansion. Default: only self.
        Return a list of children in desired iteration order.
        Container subclasses override to expose their own selectables.
        """
        return [self]

    def input_event(self, event):
        if (event == InputEvent.CLICK or event == InputEvent.LONG_CLICK) and self.action is not None:
            if self.object is not None:
                self.action(event, self, self.object)
            else:
                self.action(event, self)
            return True
        return False

    def _get_stack(self) -> PanelStack | None:
        """Helper to return the top-level panel stack. Useful for creating pop-up dialogs
           such as text editing helpers
        """
        if self.parent is None:
            return None
        return self.parent._get_stack()

    def _get_panel(self):
        """Helper to return the top-level panel. Used mostly by the UI builder
        """
        if self.parent is None:
            return None
        return self.parent._get_panel()

    def find(self, label):
        """Search the widget hierarchy (including this one) for a labelled widget
        """
        if self.label == label:
            return self
        for c in self.children:
            w = c.find(label)
            if w is not None:
                return w
        return None
