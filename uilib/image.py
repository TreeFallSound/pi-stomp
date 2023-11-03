from uilib.widget import *
from PIL import Image

class ImageWidget(Widget):
    """A simple widget with an image"""
    def __init__(self, image_path, **kwargs):
        self._init_attrs(Widget.INH_ATTRS, kwargs)
        super(ImageWidget,self).__init__(**kwargs)
        self.image = Image.open(image_path)

    def _draw(self, image, draw, real_box):
        # XXX TODO Centre and crop it ? For now just centre. XXX Assume box > image size,
        # this needs to be cleaned up and made shinnier, possibly with a Box() helper
        width,height = self.image.size
        offx = int((real_box.width - width) / 2)
        offy = int((real_box.height - height) / 2)
        loc = real_box.offset((offx,offy)).topleft
        
        # Draw image
        image.paste(self.image, loc)

    def replace_img(self, image_path):
        # XXX Note that the new image must be the same size as the original
        self.image = Image.open(image_path)
        self.refresh()

