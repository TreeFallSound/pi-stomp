#!/usr/bin/env python3

import board
import digitalio
import time
import functools
import uilib
from uilib import *
from uilib.lcd_ili9341 import *
from pistomp import encoder
from pistomp import encoderswitch

lcd = LcdIli9341(board.SPI(),
                 digitalio.DigitalInOut(board.CE0),
                 digitalio.DigitalInOut(board.D6),
                 digitalio.DigitalInOut(board.D5),
                 24000000)
pstack = PanelStack(lcd, image_format = 'RGB')

default_menu_item = None

def do_menu(event, data):
#    p2 = RoundedPanel(box = Box.xywh(40,40,260,160), image_format='RGB', auto_destroy = True)
#    p2 = RoundedPanel(box = Box.xywh(40,40,260,160), image_format='RGB', auto_destroy = True, align=WidgetAlign.CENTRE)
#    p2.set_outline(2, (0,255,0))
#    p2.set_background((0,0,0,128))
#    for i in range(0,10):
#        w = TextWidget(box = Box.xywh(5,5+20*i,250,20), text = 'Line %d' % (i+1), font = tiny_font, parent = p2)
#        p2.add_sel_widget(w)
#    i = 10
#    # XX TODO: Have a pre-cooked nice image for that, maybe even a menu helper that does
    # the job from a list of item
#    w = TextWidget(box = Box.xywh(5,5+20*i,250,20), text = '<--', font = tiny_font, parent = p2, action = lambda x,y: pstack.pop_panel(p2))
#    p2.add_sel_widget(w)
#    p2.refresh()
#    pstack.push_panel(p2)
    def menu_action(event, params):
        print("menu action, params=", params)
        global default_menu_item
        default_menu_item = params[0]
    items  = []
    for i in range(0, 15):
        items.append(('menu item '+str(i), None))
    items.append(('\u2b05', None))
    print("Menu ! DEF=", default_menu_item)
    m = Menu(title = 'Test menu', items = items, auto_destroy = True, default_item = default_menu_item, max_height = 180, action = menu_action)
    pstack.push_panel(m)

def do_dialog(event, data):
    d = Dialog(width = 240, height = 140, auto_destroy = True, title = 'Hello World')
    b = TextWidget(box = Box.xywh(0,140,0,0), text = 'Cancel', parent = d, outline = 1, sel_width = 3, outline_radius = 5, action = lambda x,y: pstack.pop_panel(d), align=WidgetAlign.CENTRE_H, name = 'cancel_btn')    
    d.add_sel_widget(b)
    pstack.push_panel(d)

def do_main_screen():
    p = Panel(box = Box.xywh(0,0,320,240))
    w = Widget(box = Box.xywh(20,20,100,40), parent = p)
    w.set_outline(2, (0,0,255))
    w.set_background((255,0,0))
    w.set_foreground((0,255,0))
    w1 = TextWidget(box = Box.xywh(100,80,60,24), text = 'Dialog', parent = p, outline = 1, sel_width = 3, outline_radius = 5, action = do_dialog)
    w2 = TextWidget(box = Box.xywh(10,120,300,20), text = 'Hello World', edit_message = 'Edit this thing:', parent = p)
    w3 = TextWidget(box = Box.xywh(50,150,250,40), text = 'Test Menu', font=Config().get_font('big_bold'), parent = p, action = do_menu)
    w2.set_foreground((0,255,255))
    w3.set_foreground((0,255,255))
    w4 = ImageWidget(box = Box.xywh(280,0,20,20), image_path = './images/wifi_orange.png', parent = p)
    p.refresh()
    p.add_sel_widget(w)
    p.add_sel_widget(w1)
    p.add_sel_widget(w2)
    p.add_sel_widget(w3)
    p.add_sel_widget(w4)
    pstack.push_panel(p)
    # Mess around with selection
    p.sel_prev()
    p.sel_next()
    p.sel_next()
    p.sel_next()
    p.sel_next()
    p.sel_next()
    p.sel_next()

def enc_step(d):
    if d > 0:
        pstack.input_event(InputEvent.RIGHT)
    elif d < 0:
        pstack.input_event(InputEvent.LEFT)

def enc_sw(v):
    if v == encoderswitch.Value.RELEASED:
        pstack.input_event(InputEvent.CLICK)
    elif v == encoderswitch.Value.LONGPRESSED:
        pstack.input_event(InputEvent.LONG_CLICK) 
    
TOP_ENC_PIN_D = 17
TOP_ENC_PIN_CLK = 4
enc = encoder.Encoder(TOP_ENC_PIN_D, TOP_ENC_PIN_CLK, callback=enc_step)
sw = encoderswitch.EncoderSwitch(1, callback=enc_sw)

Config('ui/config.json')
do_main_screen()
while True:
    enc.read_rotary()
    sw.poll()
    time.sleep(0.01)  # lower to increase responsiveness, but can cause conflict with LCD if too low
