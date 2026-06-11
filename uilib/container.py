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

from uilib.box import Box
from uilib.misc import trace
from uilib.widget import Widget
from uilib.paint import PaintContext, _pg_rect


class ContainerWidget(Widget):
    """A Widget container with a pygame.Surface backing store. Children are
    drawn inside the container. A container also supports scrolling its content.
    """

    # Inherited attributes with defaults
    INH_ATTRS = {"image_format": "RGB"}

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
        # Surface-local rect of stale pixels — None ⇒ cache is fully valid.
        # do_draw rebuilds only the dirty region on a cache miss, so frequent
        # small-clip refreshes stay cheap.
        self._dirty_region: Optional[Box] = None

        super(ContainerWidget, self).__init__(box=box, **kwargs)

        # A container doesn't need a parent to be setup so ensure that happens
        self._setup_act_attrs()
        self._setup()

    def _setup(self):
        # May adjust boundary box
        super(ContainerWidget, self)._setup()

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
        self._dirty_region = Box(0, 0, int(w), int(h))

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
            self._finalize_cache()
            self._dirty_region = None
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
            self._finalize_cache()
            self._dirty_region = None
            if self.visible and self.parent is not None:
                self.propagate_dirty(local_clip)

    def _finalize_cache(self) -> None:
        """Hook called after the backing surface is rebuilt. Subclasses can
        apply composite effects (e.g. corner masking) so steady-state blits
        out of this container are plain. Default: no-op."""
        pass

    def do_draw(self, ctx: PaintContext, frame: Box):
        """Draw this container's pixels into a parent's PaintContext.

        On a cache miss we rebuild only the dirty region (SDL clip clamps
        every primitive to that rect), then blit into the parent. Virtual
        containers maintain their cache via refresh()/scroll() and never
        rebuild here."""
        assert self.surface is not None
        with ctx.painting(frame) as pctx:
            pframe = pctx.frame
            assert pframe is not None
            local_clip = pctx.clip.deoffset(pframe.topleft)
            local_frame = self.box.norm()

            if not self.virtual and self._dirty_region is not None:
                dirty = self._dirty_region
                base_ctx = PaintContext(self.surface, dirty)
                with base_ctx.painting(local_frame) as full_ctx:
                    self._draw_erase(full_ctx)
                    self._draw(full_ctx)
                    for c in self.children:
                        if c.visible:
                            cf = c.box.offset(local_frame)
                            if cf.intersects(dirty):
                                c.do_draw(full_ctx, cf)
                    self._draw_outline(full_ctx)
                    self._draw_selection(full_ctx)
                self._finalize_cache()
                self._dirty_region = None

            dst_topleft = (pframe.x0 + local_clip.x0, pframe.y0 + local_clip.y0)
            self._blit_into(pctx.surface, local_clip, dst_topleft)

    def _viewport_view(self) -> pygame.Surface:
        """Viewport-local view of the backing surface.

        Non-virtual: viewport == bounds, so this is the whole surface.
        Virtual: returns a subsurface slice of the tall surface at the current
        scroll offset, clamped to surface bounds (the viewport can extend past
        the content when scrolled near the end). Either way, callers treat
        `local_clip` as viewport-local coords with no offset math."""
        assert self.surface is not None
        vp = self._viewport().intersection(self._content_bounds())
        return self.surface.subsurface(_pg_rect(vp))

    def _blit_into(self, target_surface: pygame.Surface, local_clip: Box, dst_topleft: Tuple[int, int]) -> None:
        """Copy the viewport-local clip from our cache into target_surface."""
        target_surface.blit(self._viewport_view(), _ipt(dst_topleft), area=_pg_rect(local_clip))

    def propagate_dirty(self, local_clip: Box):
        """Bubble a dirty region (in our local coords) up to our parent.

        Cached composites above us hold stale pixels of our region, so we
        invalidate the parent's cache with the precise rect — the next
        do_draw rebuilds only that slice."""
        if not self.visible or self.parent is None:
            return
        parent_clip = local_clip.deoffset(self.offset).offset(self.box)
        parent = self.parent
        if isinstance(parent, ContainerWidget):
            parent._invalidate_cache(parent_clip)
        parent.propagate_dirty(parent_clip)

    def _invalidate_cache(self, box: Optional[Box] = None) -> None:
        """Mark a region of our cache stale and bubble up.

        box=None means "fully invalidate" (used by child attach/detach where
        we don't have a precise rect). Otherwise unions box into our dirty
        region and bubbles a parent-coord rect to the parent."""
        if self.surface is None:
            return
        full = self._content_bounds()
        region = full if box is None else box.intersection(full)
        if region.is_empty():
            return
        self._dirty_region = region if self._dirty_region is None else self._dirty_region.union(region)
        if self.visible and self.parent is not None:
            self.parent._invalidate_cache(region.deoffset(self.offset).offset(self.box))

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
        self._dirty_region = None
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
