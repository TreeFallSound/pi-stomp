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

import pygame

from uilib.widget import Widget


def load_surface(path: str) -> pygame.Surface:
    """Load an image file as a pygame Surface.

    convert_alpha needs a video surface; under SDL_VIDEODRIVER=dummy a
    display surface exists after pygame.init(), so this is safe."""
    surf = pygame.image.load(path)
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


class ImageWidget(Widget):
    """A simple widget that paints a pygame.Surface centered in its frame.

    Accepts a file path (loaded + cached, with same-path dedup on replace) or a
    pre-built Surface (used directly, deduped by identity).
    """

    image: pygame.Surface
    _image_path: str | None

    def __init__(self, image: str | pygame.Surface, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(ImageWidget, self).__init__(**kwargs)
        if isinstance(image, str):
            self._image_path = image
            self.image = load_surface(image)
        else:
            self._image_path = None
            self.image = image

    def _draw(self, ctx):
        width, height = self.image.get_size()
        offx = int((ctx.width - width) / 2)
        offy = int((ctx.height - height) / 2)
        ctx.paste(self.image, (offx, offy))

    def replace_img(self, image: str | pygame.Surface):
        # XXX Note that the new image must be the same size as the original
        if isinstance(image, str):
            if image == self._image_path:
                return
            self._image_path = image
            self.image = load_surface(image)
        else:
            if self.image is image:
                return
            self._image_path = None
            self.image = image
        self.refresh()
