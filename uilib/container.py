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

from typing import Optional, Tuple

import pygame

from uilib.widget import *
from uilib.paint import PaintContext, _pg_rect


class ContainerWidget(Widget):
    """A Widget container with a pygame.Surface backing store. Children are
    drawn inside the container. A container also supports scrolling its content.
    """
    # Inherited attributes with defaults
    INH_ATTRS = { 'image_format' : 'RGB' }

    # When True, descendants should not push fresh pixels into this container's
    # cache during propagate_dirty. Used by PanelStack, whose surface is rebuilt
    # by composition on every propagate_dirty call (push-up would be wasted).
    _skip_cache_push = False

    def __init__(self, box, **kwargs):
        # Non-inherited attributes
        self.virtual = self._get_arg(kwargs, 'virtual', False)
        self._content_height = self._get_arg(kwargs, 'content_height', None)
        kwargs.pop('virtual', None)
        kwargs.pop('content_height', None)

        # Inheritable attributes
        self._init_attrs(ContainerWidget.INH_ATTRS, kwargs)

        self.surface: Optional[pygame.Surface] = None
        self.old_box = None
        self.offset: Tuple[int, int] = (0, 0)
        # When True, self.surface is trusted to hold the current rendered state
        # for any clip, and do_draw can skip the rebuild and just blit.
        # Invalidated on (re)allocation and on child attach/detach.
        self._cache_valid = False

        super(ContainerWidget,self).__init__(box = box, **kwargs)

        # A container doesn't need a parent to be setup so ensure that happens
        self._setup_act_attrs()
        self._setup()

    def _setup(self):
        # May adjust boundary box
        super(ContainerWidget,self)._setup()

        w = self.box.width
        h = self._content_height if (self.virtual and self._content_height) else self.box.height

        # Check if we are already setup for this box
        if (self.surface is not None and self.old_box is not None and
            self.old_box.width == w and self.old_box.height == self.box.height and
            self.surface.get_height() == h):
            return

        trace(self, "container setup, box=", self.box, "old_box=", self.old_box)

        # Create new pygame surface
        self.old_box = self.box.copy()
        self.has_alpha = self.image_format == 'RGBA'
        if self.has_alpha:
            self.surface = pygame.Surface((int(w), int(h)), pygame.SRCALPHA)
        else:
            self.surface = pygame.Surface((int(w), int(h)))
        self._cache_valid = False

    def _viewport(self) -> Box:
        """Visible region in content (surface) coords."""
        ox, oy = self.offset
        return Box.xywh(ox, oy, self.box.width, self.box.height)

    def _content_bounds(self) -> Box:
        """Full backing surface bounds — used as clip ceiling for children."""
        assert self.surface is not None
        return Box(0, 0, self.surface.get_width(), self.surface.get_height())

    def _visible_box(self, box):
        if box is None:
            return False
        return box.intersects(self.box.norm())

    def refresh(self):
        """Redraw the container's backing surface and notify the parent of the change."""
        trace(self, "ContainerWidget.refresh: vis=", self.visible, "parent=", self.parent)
        if self.surface is None:
            return
        if self.virtual:
            viewport = self._viewport()
            local_frame = self._content_bounds()
            ctx = PaintContext(self.surface, local_frame, frame=local_frame)
            self._draw_erase(ctx)
            self._draw(ctx)
            for c in self.children:
                if c.visible:
                    if viewport.intersects(c.box):
                        c.do_draw(ctx, c.box)
                        c._painted = True
                        c._dirty = False
                    else:
                        c._dirty = True
            self._draw_outline(ctx)
            self._draw_selection(ctx)
            self._cache_valid = True
            if self.visible and self.parent is not None:
                self.propagate_dirty(viewport)
        else:
            local_clip = self.box.norm()
            local_frame = self.box.norm()
            ctx = PaintContext(self.surface, local_clip, frame=local_frame)
            self._draw_erase(ctx)
            self._draw(ctx)
            for c in self.children:
                if c.visible:
                    c.do_draw(ctx, c.box.offset(local_frame))
            self._draw_outline(ctx)
            self._draw_selection(ctx)
            self._cache_valid = True
            if self.visible and self.parent is not None:
                self.propagate_dirty(local_clip)

    def do_draw(self, ctx: PaintContext, frame: Box):
        """Draw this container's pixels into a parent's PaintContext.

        If our cache is valid, this is a pure blit from self.surface into the
        parent surface. Otherwise we first rebuild the entire backing store
        (so future partial blits can trust it), then blit the requested clip.
        """
        assert self.surface is not None
        with ctx.painting(frame) as pctx:
            pframe = pctx.frame
            assert pframe is not None
            local_clip = pctx.clip.deoffset(pframe.topleft)
            local_frame = self.box.norm()

            # 1. Rebuild the cache only on a miss. Virtual containers maintain
            #    their cache via refresh()/scroll() and never rebuild here.
            if not self.virtual and not self._cache_valid:
                full_ctx = PaintContext(self.surface, local_frame, frame=local_frame)
                self._draw_erase(full_ctx)
                self._draw(full_ctx)
                for c in self.children:
                    if c.visible:
                        c.do_draw(full_ctx, c.box.offset(local_frame))
                self._draw_outline(full_ctx)
                self._draw_selection(full_ctx)
                self._cache_valid = True

            # 2. Blit our backing store into pctx.surface.
            dst_topleft = (pframe.x0 + local_clip.x0, pframe.y0 + local_clip.y0)
            self._blit_into(pctx.surface, local_clip, dst_topleft)

    def _blit_into(self, target_surface: pygame.Surface, local_clip: Box, dst_topleft: Tuple[int, int]):
        """Copy self.surface[local_clip + self.offset] into target_surface at dst_topleft.

        For virtual (tall) containers, local_clip is in viewport coords; we
        shift by self.offset to address the correct slice of the tall surface.
        Per-pixel alpha (SRCALPHA) is honored automatically by pygame's blit."""
        assert self.surface is not None
        src_box = local_clip.offset(self.offset)
        target_surface.blit(self.surface, _ipt(dst_topleft), area=_pg_rect(src_box))

    def propagate_dirty(self, local_clip: Box):
        """Bubble a dirty region (in our local coords) up to our parent container.

        Before bubbling, push our freshly-updated pixels into the parent's cache
        so it doesn't need to rebuild on its next do_draw. Skipped for PanelStack
        parents, whose surface is rebuilt by composition on every propagate_dirty."""
        if not self.visible or self.parent is None:
            return
        parent_clip = local_clip.deoffset(self.offset).offset(self.box)
        parent = self.parent
        if (isinstance(parent, ContainerWidget)
                and not parent._skip_cache_push
                and parent._cache_valid
                and parent.surface is not None):
            viewport_clip = local_clip.deoffset(self.offset)
            self._blit_into(parent.surface, viewport_clip, parent_clip.topleft)
        parent.propagate_dirty(parent_clip)

    def _invalidate_cache(self):
        """Mark our cache stale and bubble the invalidation up the container chain."""
        if not self._cache_valid:
            return
        self._cache_valid = False
        super()._invalidate_cache()

    def scroll(self, offset):
        self.offset = offset
        if not self.virtual:
            self.refresh()
            return
        if self.surface is None:
            return
        viewport = self._viewport()
        content_frame = self._content_bounds()
        ctx = PaintContext(self.surface, content_frame, frame=content_frame)
        for c in self.children:
            if c.visible and viewport.intersects(c.box):
                if not c._painted or c._dirty:
                    c.do_draw(ctx, c.box)
                    c._painted = True
                    c._dirty = False
        self._cache_valid = True
        if self.visible and self.parent is not None:
            self.propagate_dirty(viewport)

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
                self.scroll((ox, 0))
            else:
                self.scroll((ox, oy))
            return True
        return False


def _ipt(p):
    return (int(p[0]), int(p[1]))
