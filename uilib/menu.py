from uilib.dialog import *
from uilib.config import *

class Menu(Dialog):
    """A pop-up menu panel with lines of text to select
           items   : iterable of tuples whose first element is the text to display
           Returns a tuple (image, draw, box) where:
    """
    def __init__(self, items, font = None, max_width = None, max_height = None,
                 text_halign = TextHAlign.CENTRE, auto_dismiss = True, dismiss_option = False,
                 default_item = None, **kwargs):
        self.max_height = max_height
        self.max_width = max_width
        self.items = items
        self.auto_dismiss = auto_dismiss
        if auto_dismiss is False or dismiss_option is True:
            # without auto_dismiss provide a back arrow to close menu
            self.items.append(('\u2b05', self._dismiss, None))
        if font is None:
            font = Config().get_font('default')
        self.font = font
        self.font_metrics = font.getmetrics()
        self.item_h = 0
        self.text_halign = text_halign
        self.default_item = default_item
        super(Menu,self).__init__(width = 0, height = 0, **kwargs)

        # Create item widgets
        h = 0
        for i in items:
            # item structure: 0:name, 1:action, 2:object, 3:selected item
            t = i[0]
            if len(i) == 4 and i[3]:
                t = '\u2714 ' + t   # Add checkmark to selected item
            b = Box.xywh(0,h,self.box.width,self.item_h)
            w = TextWidget(box = b, text_halign = self.text_halign, font = self.font,
                           text = t, parent = self, action = self._item_action)
            w.data = i
            self.add_sel_widget(w)
            if t == self.default_item:
                self.sel_widget(w)
            h = h + self.item_h

        self.refresh()

    def _dismiss(self, arg=None):
        stack = self._get_stack()
        if stack:
            stack.pop_panel(self)

    def _item_action(self, event, source):
        trace(self, "item action !", event, source)
        if event == InputEvent.CLICK or event == InputEvent.LONG_CLICK:
            data = source.data
            action = self.action
            if self.auto_dismiss:
                self._dismiss()
            if action is not None:
                action(event, data)

    def _adjust_box(self):
        trace(self, "menu box adjust, parent=", self.parent)

        # Calculate height and width
        #
        # TODO: Make margins configurable
        #
        # Note: we assume the height of a line is constant. This might be a tad
        # optimistic but it helps getting smooth scrolling.
        #
        # TODO: Re-adjust item widgets here instead of in constructor. Right
        # now we rely on the pass done in the constructor (without a parent)
        # because it calculates item_h which is then use to layout the menu
        # items. But we could just pile them on top of each other and move
        # them once attached.
        #
        w = 240
        h = 0
        h_margin = 10
        v_margin = 0
        for i in self.items:
            t = i[0]
            tw, th = get_text_size(t, self.font, self.font_metrics)
            trace(self, "item <",t,"> tw=", tw, "th=", th)
            tw = tw + h_margin * 2
            th = th + v_margin * 2
            #if tw > w:
            #    w = tw
            if h == 0:
                self.item_h = th
                h = th * len(self.items)
        mw = self.max_width
        mh = self.max_height
        if mw is not None and w > mw:
            w = 240
        if mh is not None and h > mh:
            h = mh
        print("-> adjusted w,h:", w, h)
        self.box = Box.xywh(0,0,w,h)
        super(Menu,self)._adjust_box()
