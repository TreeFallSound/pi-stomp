import json
from PIL import ImageFont

from uilib.panel import *
from uilib.dialog import *
from uilib.text import *
from uilib.image import *
from uilib.config import *

class UiBuilder:
    def _translate_attr(kv):
        key, value = kv
        if key == 'box':
            return Box(value)
        if key == 'align':
            return WidgetAlign[value]
        if key == 'text_halign':
            return TestHAlign[value]
        if key == 'font' or key == 'title_font':
            if isinstance(value, list):
                fname, size = tuple(value)
                return ImageFont.TrueType(fname, size)
            return Config().get_font(kv)
        if (key == 'fgnd' or key == 'bkgnd' or key == 'sel_color' or
            key == 'outline_color' or key == 'title_color'):
            if isinstance(value, list):
                return tuple(value)
            return Config().get_color(value)
        return value

    def _set_default(attrs, family, name, defaults):
        if name is None or name == '':
            attr_name = family
            def_name = 'default'
        else:
            attr_name = name + '_' + family
            def_name = 'default_' + name
        if attr_name not in attrs:
            if def_name in defaults:
                attrs[attr_name] = defaults[def_name]


    def _fixup_widget(attrs):
        UiBuilder._set_default(attrs, 'color', 'fgnd', Config().colors)
        UiBuilder._set_default(attrs, 'color', 'bkgnd', Config().colors)
        UiBuilder._set_default(attrs, 'color', 'sel', Config().colors)
        UiBuilder._set_default(attrs, 'color', 'outline', Config().colors)
        return attrs

    def _fixup_panel(attrs):
        return UiBuilder._fixup_widget(attrs)

    def _fixup_dialog(attrs):
        UiBuilder._set_default(attrs, 'font', 'title', Config().fonts)
        return UiBuilder._fixup_panel(attrs)

    def _fixup_text_widget(attrs):
        UiBuilder._set_default(attrs, 'font', None, Config().fonts)
        return UiBuilder._fixup_widget(attrs)

    def _fixup_image_widget(attrs):
        return UiBuilder._fixup_widget(attrs)
    
    def create_widget(desc, label = None, parent = None):
        print("Creating widget from json...")

        # Handle files containing lists of widgets
        if isinstance(desc, list):
            print("Found list, scanning..")
            for e in desc:
                w = UiBuilder.create_widget(e, label, parent)
                if w is not None:
                    return w
            return None

        # Decode one widget
        l = None
        cls = None
        children = None
        attrs = {}
        selectable = False
        for key, value in desc.items():
            if key == 'label':
                l = value
                if label is not None and l != label:
                    print("Label mismatch, skipping")
                    return None
            elif key == 'class':
                cls = value
            elif key == 'children':
                children = value
            elif key == 'selectable':
                selectable = bool(Value)
            else:
                attrs[key] = UiBuilder._translate_attr((key, value))
        if parent is not None:
            attrs['parent'] = parent
        attrs['label'] = l
        if cls is None:
            print("Missing class for widget in json !")
            return
        wtypes = {
            'Panel' : (Panel, UiBuilder._fixup_panel),
            'Dialog' : (Dialog, UiBuilder._fixup_dialog),
            'Widget' : (Widget, UiBuilder._fixup_widget),
            'TextWidget' : (TextWidget, UiBuilder._fixup_text_widget),
            'ImageWidget' : (ImageWidget, UiBuilder._fixup_image_widget),
            'Button' : (Button, UiBuilder._fixup_text_widget)
        }
        _cls, _fix = wtypes[cls]
        attrs = _fix(attrs)
        trace(None, "Creating widget class", cls, "attrs:", attrs)
        w = _cls(**attrs)
        if children is not None:
            for c in children:
                UiBuilder.create_widget(c, parent = w)
        if selectable:
            p = w._get_panel()
            if p is None:
                print("Selectable widget, but panel not found")
            else:
                p.add_sel_widget(w)

    def load_widget(json_file, label = None, parent = None):
        with open(json_file, 'r') as f:
            data = json.load(f)
        return UiBuilder.create_widget(data, label, parent)
