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

from uilib.widget import Widget
from PIL import Image


class ImageWidget(Widget):
    """A simple widget with an image"""

    image: Image.Image
    _image_path: str | None

    def __init__(self, image: str | Image.Image, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(ImageWidget, self).__init__(**kwargs)

        if isinstance(image, str):
            self._image_path = image
            self.image = Image.open(self._image_path)
        else:
            self._image_path = None
            self.image = image

    def _draw(self, image, draw, real_box):
        # XXX TODO Centre and crop it ? For now just centre. XXX Assume box > image size,
        # this needs to be cleaned up and made shinnier, possibly with a Box() helper
        width, height = self.image.size
        offx = int((real_box.width - width) / 2)
        offy = int((real_box.height - height) / 2)
        loc = real_box.offset((offx, offy)).topleft

        # Draw image
        mask = self.image if self.image.mode == "RGBA" else None
        image.paste(self.image, loc, mask)

    def replace_img(self, image: str | Image.Image):
        # XXX Note that the new image must be the same size as the original
        if isinstance(image, str):
            if image == self._image_path:
                return
            self._image_path = image
            self.image = Image.open(image)
        else:
            if self.image is image:
                return
            self._image_path = None
            self.image = image
        self.refresh()
