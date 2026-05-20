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

from uilib.widget import *


def _load(image_path: str) -> pygame.Surface:
    # convert_alpha needs a video surface; under SDL_VIDEODRIVER=dummy a
    # display surface exists after pygame.init(), so this is safe.
    surf = pygame.image.load(image_path)
    try:
        return surf.convert_alpha()
    except pygame.error:
        return surf


class ImageWidget(Widget):
    """A simple widget that paints a pygame.Surface centered in its frame."""

    def __init__(self, image_path, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(ImageWidget, self).__init__(**kwargs)
        self.image = _load(image_path)

    def _draw(self, ctx):
        width, height = self.image.get_size()
        offx = int((ctx.width - width) / 2)
        offy = int((ctx.height - height) / 2)
        ctx.paste(self.image, (offx, offy))

    def replace_img(self, image_path):
        # XXX the new image should be the same size as the original
        self.image = _load(image_path)
        self.refresh()
