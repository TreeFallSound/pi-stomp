import adafruit_rgb_display.ili9341 as ili9341

from uilib.panel import *

class LcdIli9341(LcdBase):
    # XXX
    # TODO: Turn "flip" into all 90deg angle combinations
    def __init__(self, spi, cs_pin, dc_pin, reset_pin, baudrate, flip = True):
        self.disp = ili9341.ILI9341(
            spi,
            cs=cs_pin,
            dc=dc_pin,
            rst=reset_pin,
            baudrate=baudrate
        )
        # Clear the display
        self.clear()

        # Test full screen image
        self.width = self.disp.height
        self.height = self.disp.width
        self.flip = flip

    def dimensions(self):
        return (self.width, self.height)

    def default_format(self):
        return 'RGB'

    def clear(self):
        self.disp.fill(0)

    def update(self, image, box = None):
        # LCD coordinates
        #
        # portrait mode, connector = bottom
        #
        # on pi-stomp, X=0 is "bottom" (away from jacks)
        #              Y=0 is "left" (out jack side)
        #
        img_width, img_height = image.size
        if box is None:
            box = Box(0,0,img_width,img_height)

        # Check if we need to crop the image to the LCD size
        x1, y1, x2, y2 = box.rect
        if x2 > self.width:
            x2 = width
        if y2 > self.height:
            y2 = self.height
        if x1 != 0 or y1 != 0 or x2 != img_width or y2 != img_width:
            image = image.crop((x1,y1,x2,y2))
            if self.flip:
                x = self.height - y2
                y = x1
            else:
                x = y1
                y = self.width - x2
        self.disp.image(image, 270 if self.flip else 90, x, y)

