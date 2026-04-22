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
from uilib.panel import LcdBase


class LcdPygame(LcdBase):
    """LCD implementation that renders into a pygame Surface."""

    def __init__(self, width=320, height=240):
        self.width = width
        self.height = height
        self.surface = pygame.Surface((width, height))

    def dimensions(self):
        return (self.width, self.height)

    def default_format(self):
        return 'RGB'

    def update(self, image, box=None):
        img_w, img_h = image.size

        if box is not None:
            x0, y0, x1, y1 = box.rect
            x1 = min(x1, self.width)
            y1 = min(y1, self.height)
            # Crop if the image is larger than the dirty region
            if x0 != 0 or y0 != 0 or x1 != img_w or y1 != img_h:
                image = image.crop((x0, y0, x1, y1))
            dest = (x0, y0)
        else:
            dest = (0, 0)

        pg_surf = pygame.image.fromstring(image.tobytes(), image.size, image.mode)
        self.surface.blit(pg_surf, dest)

    def blit_scaled(self, dest_surface, dest_rect):
        """Scale the LCD surface to dest_rect and blit it onto dest_surface."""
        scaled = pygame.transform.scale(self.surface, (dest_rect.width, dest_rect.height))
        dest_surface.blit(scaled, dest_rect.topleft)
