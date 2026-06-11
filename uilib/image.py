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
from PIL import Image

from uilib.widget import Widget


def _to_surface(image: str | Image.Image) -> pygame.Surface:
    """Load an image (file path or PIL Image) as a pygame Surface.

    convert_alpha needs a video surface; under SDL_VIDEODRIVER=dummy a
    display surface exists after pygame.init(), so this is safe."""
    if isinstance(image, str):
        surf = pygame.image.load(image)
    else:
        # PIL Image — frombytes only handles RGB/RGBA, so normalise first.
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA")
        surf = pygame.image.frombytes(image.tobytes(), image.size, image.mode)
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


class ImageWidget(Widget):
    """A simple widget that paints a pygame.Surface centered in its frame."""

    def __init__(self, image: str | Image.Image, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(ImageWidget, self).__init__(**kwargs)
        self.image = _to_surface(image)

    def _draw(self, ctx):
        width, height = self.image.get_size()
        offx = int((ctx.width - width) / 2)
        offy = int((ctx.height - height) / 2)
        ctx.paste(self.image, (offx, offy))

    def replace_img(self, image: str | Image.Image):
        # XXX the new image should be the same size as the original
        self.image = _to_surface(image)
        self.refresh()
