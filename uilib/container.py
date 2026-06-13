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

from typing_extensions import override
from PIL import Image, ImageDraw

from uilib.box import Box
from uilib.misc import trace
from uilib.widget import Widget


class ContainerWidget(Widget):
    """A Widget container with an Image backing store, Children are drawn inside
    the container.
    A container also supports scrolling its content.
    """

    # Inherited attributes with defaults
    INH_ATTRS = {"image_format": "RGB"}

    mask: Image.Image | None

    def __init__(self, box, **kwargs):
        # Non-inherited attributes
        self.mask_format = self._get_arg(kwargs, "mask_format", None)

        # Inheritable attributes
        self._init_attrs(ContainerWidget.INH_ATTRS, kwargs)

        self.image: Image.Image | None = None
        self.old_box: Box | None = None
        self.offset = (0, 0)

        super(ContainerWidget, self).__init__(box=box, **kwargs)

        # A container doesn't need a parent to be setup so ensure that happens
        self._setup_act_attrs()
        self._setup()

    def _setup(self):
        # May adjust boundary box
        super(ContainerWidget, self)._setup()

        w = self.box.width
        h = self.box.height

        # Check if we are already setup for this box
        if self.image is not None and self.old_box is not None and self.old_box.width == w and self.old_box.height == h:
            return

        # Create new image and draw instance
        self.old_box = self.box.copy()
        self.image = Image.new(self.image_format, (w, h))
        self.draw = ImageDraw.Draw(self.image)
        self.has_alpha = self.image_format == "RGBA"
        if self.mask_format is not None:
            self.mask = Image.new(self.mask_format, (w, h))
        else:
            self.mask = None

    def _visible_box(self, box):
        """Returns if any part of the box intersects this widget"""
        if box is None:
            return False
        return box.intersects(self.box.norm())

    def _focus(self, box):
        box = box.deoffset(self.offset)
        if self.visible and self._visible_box(box):
            return (self.image, self.draw, box)
        else:
            return (None, None, None)

    def _unfocus(self, box):
        # A child updated itself, tell parent to "compose" a subsection of ourselves
        if self.visible and self.parent:
            box = box.deoffset(self.offset)
            self.parent._compose(self, box, box.offset(self.box))

    def _compose(self, widget, orig_box, real_box):
        assert isinstance(widget, ContainerWidget)

        real_box.deoffset(self.offset)  # XXX: result is discarded

        # Crop real box to this image box. This avoids trying to copy pixels
        # that are outside of it
        crop = real_box.intersection(self.box.norm())
        if crop.is_empty():
            return

        # XXX TODO: Fast path the case where no cropping occurs

        # Now create a new orig box that is cropped as well
        offset = orig_box.get_offset(real_box)
        orig_crop = crop.deoffset(offset)

        # Alpha path: If both images have alpha channels, then do an
        # alpha composition which handles the cropping
        if self.has_alpha and widget.has_alpha:
            self.image.alpha_composite(widget.image, crop.topleft, orig_crop.rect)
        else:
            sub_image = widget.image.crop(orig_crop.rect)
            if widget.mask is not None:
                sub_mask = widget.mask.crop(orig_crop.rect)
            else:
                sub_mask = None
            self.image.paste(sub_image, crop.rect, sub_mask)
            # Compose ourselves into parent if we are visible
            if self.visible and self.parent != None:
                self.parent._compose(self, crop, crop)

    @override
    def refresh(self, box: Box | None = None):
        # FIXME: ignoring box completely?
        trace(self, "ContainerWidget.refresh: vis=", self.visible, "parent=", self.parent)
        if not self.image:
            return

        # Refresh the content of the container
        self._do_draw(self.image, self.draw, self.box.norm())

        # Update into parent container (call the parent refresh who will do the job)
        # orig_box must be in widget-local image coords (matches _unfocus's
        # convention); real_box is in parent coords. Passing self.box for both
        # crops the wrong region out of widget.image whenever self.box.x0/y0 != 0.
        if self.visible and self.parent != None:
            self.parent._compose(self, self.box.norm(), self.box)

    def _do_draw(self, image, draw, real_box):
        # We replace the base Widget implementation because of how we deal with
        # offsets: The erase and outline aren't offsetted, the rest is.
        #
        # When invoked as a *child* of another widget (image is not our own
        # backing image), render into our own image+draw first, then paste the
        # result into the parent. Drawing children directly into the parent
        # image and then pasting self.image on top would wipe their pixels.
        if image is not self.image and self.image is not None:
            self._do_draw(self.image, self.draw, self.box.norm())
            image.paste(self.image, real_box.rect)
            return

        off_real_box = real_box.deoffset(self.offset)
        self._draw_erase(image, draw, real_box)
        self._draw(image, draw, off_real_box)
        for c in self.children:
            crb = c.box.offset(off_real_box)
            c._do_draw(image, draw, crb)
        self._draw_outline(image, draw, real_box)
        self._draw_selection(image, draw, real_box)

    def scroll(self, offset):
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

    def _scroll_delta(self, box: Box, movex: int, movey: int, orig_box: Box):
        """
        Translate overflow on each axis into a scroll adjustment.
        Default policy: page-snap to the moving box's own dimensions, and
        reset y to 0 when the requested box originates at the container top.
        """
        dx = self.__adj_off_step(movex, box.width) if movex else 0
        dy = self.__adj_off_step(movey, box.height) if movey else 0
        if orig_box.y0 == 0:
            dy = -self.offset[1]
        return dx, dy

    def _viewport_size(self) -> tuple[int, int]:
        return self.box.width, self.box.height

    def _scroll_into_view(self, box: Box):
        orig_box = box
        box = box.deoffset(self.offset)
        x0, y0, x1, y1 = box.rect
        brx, bry = self._viewport_size()
        movex = x0 if x0 < 0 else (x1 - brx if x1 > brx else 0)
        movey = y0 if y0 < 0 else (y1 - bry if y1 > bry else 0)
        if not (movex or movey):
            return False
        dx, dy = self._scroll_delta(box, movex, movey, orig_box)
        ox, oy = self.offset
        self.scroll((ox + dx, oy + dy))
        return True
