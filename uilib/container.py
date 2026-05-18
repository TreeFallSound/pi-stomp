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

from uilib.widget import *
from uilib.paint import PaintContext
from PIL import Image, ImageDraw

class ContainerWidget(Widget):
    """A Widget container with an Image backing store, Children are drawn inside
       the container.
       A container also supports scrolling its content.
    """
    # Inherited attributes with defaults
    INH_ATTRS = { 'image_format' : 'RGB' }

    def __init__(self, box, **kwargs):
        # Non-inherited attributes
        self.mask_format = self._get_arg(kwargs, 'mask_format', None)

        # Inheritable attributes
        self._init_attrs(ContainerWidget.INH_ATTRS, kwargs)

        self.image = None
        self.old_box = None
        self.offset = (0, 0)

        super(ContainerWidget,self).__init__(box = box, **kwargs)

        # A container doesn't need a parent to be setup so ensure that happens
        self._setup_act_attrs()
        self._setup()

    def _setup(self):
        # May adjust boundary box
        super(ContainerWidget,self)._setup()

        w = self.box.width
        h = self.box.height

        # Check if we are already setup for this box
        if (self.image != None and self.old_box != None and
            self.old_box.width == w and self.old_box.height == h):
            return

        trace(self, "container setup, box=", self.box, "old_box=", self.old_box)

        # Create new image and draw instance
        self.old_box = self.box.copy()
        self.image = Image.new(self.image_format, (w, h))
        self.draw = ImageDraw.Draw(self.image)
        self.has_alpha = self.image_format == 'RGBA'
        if self.mask_format is not None:
            self.mask = Image.new(self.mask_format, (w, h))
        else:
            self.mask = None
        
    def _visible_box(self, box):
        if box is None:
            return False
        return box.intersects(self.box.norm())

    def refresh(self):
        trace(self, "ContainerWidget.refresh: vis=", self.visible, "parent=", self.parent)
        if not self.image:
            return
        local_clip = self.box.norm()
        ctx = PaintContext(self.image, self.draw, local_clip)
        local_frame = self.box.norm()
        self._draw_erase(ctx, local_frame)
        self._draw(ctx, local_frame)
        for c in self.children:
            if c.visible:
                c._do_draw(ctx, c.box.offset(local_frame))
        self._draw_outline(ctx, local_frame)
        self._draw_selection(ctx, local_frame)
        if self.visible and self.parent is not None:
            self._propagate_dirty(local_clip)

    def _do_draw(self, ctx: PaintContext, frame: Box):
        """Draw this container into the parent surface at frame."""
        local_clip = ctx.clip.deoffset(frame).intersection(self.box.norm())
        if local_clip.is_empty():
            return

        local_frame = self.box.norm()
        if self.outline_radius is not None:
            r = self.outline_radius
            safe = Box(r, r, local_frame.width - r, local_frame.height - r)
            if not safe.contains(local_clip):
                local_clip = local_frame
        local_ctx = PaintContext(self.image, self.draw, local_clip)
        self._draw_erase(local_ctx, local_frame)
        self._draw(local_ctx, local_frame)
        for c in self.children:
            if c.visible:
                c._do_draw(local_ctx, c.box.offset(local_frame))
        self._draw_outline(local_ctx, local_frame)
        self._draw_selection(local_ctx, local_frame)

        # Blit dirty region into parent surface
        src_box = local_clip
        dst_topleft = local_clip.offset(frame).topleft
        sub = self.image.crop(src_box.rect)
        if self.mask is not None:
            sub_mask = self.mask.crop(src_box.rect)
        else:
            sub_mask = None
        if self.has_alpha and ctx.image.mode == 'RGBA':
            ctx.image.alpha_composite(sub, dst_topleft, src_box.rect)
        else:
            ctx.image.paste(sub, dst_topleft, sub_mask)

    def _propagate_dirty(self, local_clip: Box):
        """Bubble a dirty region (in our local coords) up to our parent container."""
        if not self.visible or self.parent is None:
            return
        parent_clip = local_clip.deoffset(self.offset).offset(self.box)
        self.parent._propagate_dirty(parent_clip)

    def scroll(self, offset):
        print(offset)
        self.offset = offset
        # XXX Optimize ? at least optionally for things like menus, use a local blit
        # of the backing store instead of a full refresh to work around slow text
        # drawing speed with Pillow on 64bit ?
        self.refresh()
    
    def __adj_off_step(self, off, step):
        aoff = abs(off)
        s = (aoff + (step - 1)) // step
        if off > 0:
            return s * step
        else:
            return -s * step

    def _scroll_into_view(self, box):
        b0 = box
        box = box.deoffset(self.offset)
        x0,y0,x1,y1 = box.rect
        ox,oy = self.offset
        brx,bry = self.box.width, self.box.height
        movex,movey = 0,0
        if x0 < 0:
            movex = x0
        if y0 < 0:
            movey = y0
        if x1 > brx:
            movex = x1 - brx
        if y1 > bry:
            movey = y1 - bry
        if movex != 0 or movey != 0:
            ox += self.__adj_off_step(movex, box.width)
            oy += self.__adj_off_step(movey, box.height)
            if b0.y0 == 0:
                # XXX hack to allow scrolling to reset to original location when box.y0 is 0 (container top)
                # TODO would prefer a better way
                self.scroll((ox, 0))
            else:
                self.scroll((ox, oy))
            return True
        return False

