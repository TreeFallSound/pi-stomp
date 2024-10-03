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

# All "box" arguments here are to be instances of this class
#
class Box:
    """Class representing a rectangle with various helpers for things
       like offsetting, measuring etc...
    """
    def __init__(self, *args):
        """Initialize using either:
          - Indivudal coords: x0,y0,x1,y1
          - Indivudal points: (x0,y0),(x1,y1)
          - tuple (x0,y0,x1,y1)
          - list [x0,y0,x1,y1]
          - tuples ((x0,y0),(x1,y1))
          - list of tuples  [(x0,y0),(x1,y1)]
        """
        # If single args, just unpack it
        if len(args) == 1:
            args = args[0]
        if len(args) == 4:
            self.box = tuple(args)
        elif len(args) == 2:
            p0 = args[0]
            p1 = args[1]
            self.box = (p0[0], p0[1], p1[0], p1[1])
        else:
            raise ValueError

    def __str__(self):
        return str(self.box)

    def copy(self):
        return Box(self.x0, self.y0, self.x1, self.y1)

    @property
    def width(self):
        x0,y0,x1,y1 = self.box
        return x1 - x0
    @width.setter
    def width(self, value):
       self.x1 = self.x0 + int(value)

    @property
    def height(self):
        x0,y0,x1,y1 = self.box
        return y1 - y0
    @height.setter
    def height(self, value):
       self.y1 = self.y0 + int(value)

    @property
    def topleft(self):
        x0,y0,x1,y1 = self.box
        return (x0,y0)

    @property
    def botright(self):
        x0,y0,x1,y1 = self.box
        return (x1,y1)

    @property
    def x0(self):
        return self.box[0]
    @x0.setter
    def x0(self, value):
        self.box = (int(value), self.box[1], self.box[2], self.box[3])
    @property
    def y0(self):
        return self.box[1]
    @y0.setter
    def y0(self, value):
        self.box = (self.box[0], int(value), self.box[2], self.box[3])
    @property
    def x1(self):
        return self.box[2]
    @x1.setter
    def x1(self, value):
        self.box = (self.box[0], self.box[1], int(value), self.box[3])
    @property
    def y1(self):
        return self.box[3]
    @y1.setter
    def y1(self, value):
        self.box = (self.box[0], self.box[1], self.box[2], int(value))

    @property
    def rect(self):
        """Return rectangle as a tuple"""
        return self.box

    @property
    def PIL_rect(self):
        """Return rectangle as a tuple with botright coords minus 1
           to account for PIL/Pillow bug in "rectangle" primitives
        """
        return (self.box[0], self.box[1], self.box[2] - 1, self.box[3] - 1)

    @staticmethod
    def xywh(x,y,w,h):
        """Create a Box from coordinates, width and height"""
        return Box(x,y,x+w,y+h)

    def __eq__(self, other):
        if isinstance(other, Box):
            return self.box == other.box
        return NotImplemented

    def offset(self, ref):
        """Return an offsetted Box. ref can be a point (x,y) tuple, or
           another Box in which case it's topleft corner is used as an
           offset
        """        
        # Ref can be a point (x,y) or a Box
        if isinstance(ref, Box):
            ref = ref.topleft
        # We shift, we don't clip
        b = self.box
        return Box(b[0] + ref[0],
                   b[1] + ref[1],
                   b[2] + ref[0],
                   b[3] + ref[1])

    def deoffset(self, ref):
        """Return an "de-offsetted Box". This is the same as "offset" but
           the offset is applied negativelty. ref can be a point (x,y) tuple, or
           another Box in which case it's topleft corner is used as an
           offset
        """        
        # Ref can be a point (x,y) or a Box
        if isinstance(ref, Box):
            ref = ref.topleft
        # We shift, we don't clip
        b = self.box
        return Box(b[0] - ref[0],
                   b[1] - ref[1],
                   b[2] - ref[0],
                   b[3] - ref[1])

    def get_offset(self, box):
        """Returns the (x,y) offset between two boxes"""
        return (box.box[0] - self.box[0], box.box[1] - self.box[1])

    def intersects(self, box):
        """Returns whether there is an intersection between the two rectangles"""
        if self.box[0] >= box.box[2] or box.box[0] >= self.box[2] or self.box[1] >= box.box[3] or box.box[1] >= self.box[3]:
            return False
        else:
            return True

    def intersection(self, box):
        """Returns a rectangle that is the intersection of the two rectangles"""
        x0 = max(self.box[0], box.box[0])
        y0 = max(self.box[1], box.box[1])
        x1 = min(self.box[2], box.box[2])
        y1 = min(self.box[3], box.box[3])
        return Box(x0,y0,x1,y1)

    def is_empty(self):
        return self.box[0] >= self.box[2] or self.box[1] >= self.box[3]

    def norm(self):
        """Return a zero based Box of the same width and height"""
        return Box(0,0, self.width, self.height)

    def centre(self, parent):
        """Return a copy of this box centered into the parent"""
        w = self.width
        h = self.height
        pw = parent.width
        ph = parent.height
        hoff = (pw - w) // 2
        voff = (ph - h) // 2
        return Box.xywh(hoff, voff, w, h)

