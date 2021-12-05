import json
from PIL import ImageFont

class Config():
    _instance = None
    def __new__(cls,*args, **kwargs):
        if Config._instance is None:
            Config._instance = super().__new__(cls)
        return Config._instance

    def __init__(self, config_json = None):
        if not hasattr(self, 'fonts'):
            print("Adding empty fonts...")
            self.fonts = {}
        if not hasattr(self, 'colors'):
            print("Adding empty colors...")
            self.colors = {}
        if config_json is not None:
            self.load_config(config_json)
        self._set_defaults()

    def _set_defaults(self):
        if 'default' not in self.fonts:
            add_font('default', 'DejaVuSans.ttf', 16)
        if 'default_title' not in self.fonts:
            add_font('default_title', 'DejaVuSans-Bold.ttf', 16)
        if 'default_fgnd' not in self.colors:
            add_color('default_fgnd', (255, 255, 255))
        if 'default_bkgnd' not in self.colors:
            add_color('default_bkgnd', (0, 0, 0))
        if 'default_title_fgnd' not in self.colors:
            add_color('default_title_fgnd', (255, 191, 63))
        if 'default_title_bkgnd' not in self.colors:
            add_color('default_title_bkgnd', (63, 63, 63))

    def add_font(self, label, file_name, size):
        f = ImageFont.truetype(file_name, size)
        # XXX Add some error handling
        self.fonts[label] = f

    def get_font(self, label):
        if label not in self.fonts:
            return None
        return self.fonts[label]

    def has_font(self, label):
        return label in self.fonts

    def add_color(self, label, rgb):
        self.colors[label] = rgb

    def get_color(self, label):
        return self.colors[label]

    def has_color(self, label):
        return label in self.colors
    
    def load_config(self, json_file, reset_old = True):
        if reset_old:
            self.fonts = {}
            self.colors = {}
        with open(json_file, 'r') as f:
            data = json.load(f)
        if 'fonts' in data:
            fonts = data['fonts']
            for font_def in fonts:
                try:
                    l = font_def['label']
                    n = font_def['name']
                    s = font_def['size']
                except KeyError as e:
                    print("Error loading font:", e)
                else:
                    self.add_font(l, n, s)
        if 'colors' in data:
            colors = data['colors']
            for color_def in colors:
                try:
                    l = color_def['label']
                    c = color_def['rgb']
                except KeyError as e:
                    print("Error loading color:", e, colors)
                else:
                    c = tuple(c)
                    self.add_color(l, c)

