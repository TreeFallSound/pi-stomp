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

import random

lcd = LcdIli9341(board.SPI(),
                 digitalio.DigitalInOut(board.CE0),
                 digitalio.DigitalInOut(board.D6),
                 digitalio.DigitalInOut(board.D5),
                 24000000)
pstack = PanelStack(lcd, image_format = 'RGB')

default_menu_item = None

def do_menu(event, data):
    def menu_action(event, params):
        print("menu action, params=", params)
        global default_menu_item
        default_menu_item = params[0]
    items = []
    for i in range(0, 15):
        items.append(('menu item '+str(i), None))
    items.append(('\u2b05', None))
    print("Menu ! DEF=", default_menu_item)
    m = Menu(title = 'Test menu', items = items, auto_destroy = True, default_item = default_menu_item, max_height = 180, action = menu_action)
    pstack.push_panel(m)

def do_plugin_param_menu(event, data):
    def menu_action(event, params):
        print("menu action, params=", params)
        do_param_dialog(event, params)
    items = [('Gain', None), ('Tone', None), ('Level', None), ('Transmogrify', None)]  # TODO this should come from data
    items.append(('\u2b05', None))
    m = Menu(title='Settings', items=items, auto_destroy=True, default_item=default_menu_item, max_width=100, max_height=180,
         action=menu_action)
    pstack.push_panel(m)

def do_dialog(event, data):
    d = Dialog(width = 240, height = 140, auto_destroy = True, title = 'Hello World')
    b = TextWidget(box = Box.xywh(0,140,0,0), text = 'Cancel', parent = d, outline = 1, sel_width = 3, outline_radius = 5, action = lambda x,y: pstack.pop_panel(d), align=WidgetAlign.CENTRE_H, name = 'cancel_btn')    
    d.add_sel_widget(b)
    pstack.push_panel(d)

def do_wifi_dialog(event, data):
    d = Dialog(width=240, height=120, auto_destroy=True, title='Configure WiFi')

    b = TextWidget(box = Box.xywh(0,0,0,0), text='mySSID', prompt='SSID :', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=lambda x,y: pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn',
                   edit_message='WiFi SSID')
    d.add_sel_widget(b)
    b = TextWidget(box = Box.xywh(0,30,0,0), text='password123', prompt='Password :', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=lambda x,y: pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn',
                   edit_message='Password')
    d.add_sel_widget(b)

    b = TextWidget(box = Box.xywh(0, 90, 0, 0), text='Cancel', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=lambda x,y: pstack.pop_panel(d), align=WidgetAlign.NONE, name='cancel_btn')
    d.add_sel_widget(b)
    b = TextWidget(box=Box.xywh(80, 90, 0, 0), text='Ok', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=lambda x, y: pstack.pop_panel(d), align=WidgetAlign.NONE, name='ok_btn')
    d.add_sel_widget(b)

    pstack.push_panel(d)
    d.refresh()

def do_param_dialog(event, data):
    d = Dialog(width=240, height=140, auto_destroy=True, title=data[0])
    b = TextWidget(box = Box.xywh(0,140,0,0), text='Ok', parent=d, outline=1, sel_width=3, outline_radius=5,
                   action=lambda x,y: pstack.pop_panel(d), align=WidgetAlign.CENTRE_H, name='ok_btn')
    d.add_sel_widget(b)
    pstack.push_panel(d)

def do_main_screen():

    title_font = ImageFont.truetype("DejaVuSans-Bold.ttf", 26)
    display_width = 320
    display_height = 240
    plugin_width = 79
    plugin_height = 31
    footswitch_height = 60

    p = Panel(box = Box.xywh(0,0,display_width,180))

    # toolbar
    wifi = ImageWidget(box=Box.xywh(240,0,20,20), image_path='./images/wifi_orange.png', parent=p, action=do_wifi_dialog)
    p.add_sel_widget(wifi)
    power = ImageWidget(box=Box.xywh(270,0,20,20), image_path='./images/power_green.png', parent=p)
    p.add_sel_widget(power)
    wrench = ImageWidget(box=Box.xywh(296,0,20,20), image_path='./images/wrench_silver.png', parent=p,
                         action=do_menu)
    p.add_sel_widget(wrench)

    # Pedalboard / Snapshot
    pb = TextWidget(box = Box.xywh(0,20,159,36), text='Grungy', font=title_font, parent = p, action = do_menu)
    pb.set_foreground((0,255,255))
    p.add_sel_widget(pb)
    snap = TextWidget(box = Box.xywh(161,20,159,36), text='Alice', font=title_font, parent = p, action = do_menu)
    snap.set_foreground((0,255,255))
    p.add_sel_widget(snap)

    # Controlers


    # Plugins
    colors = ["MediumVioletRed", "Lime", "OrangeRed", "Indigo", "Gray", "SaddleBrown"]
    x = 0
    y = 81
    per_row = 4
    for i in range(1, 18):
        plugin = Widget(box = Box.xywh(x,y,plugin_width,plugin_height), outline_radius=5, parent=p, action=do_plugin_param_menu)
        color = colors[random.randint(0, len(colors)-1)]
        plugin.set_outline(2, "black")
        plugin.set_background(color)
        plugin.set_foreground((0,255,0))
        p.add_sel_widget(plugin)

        pos = (i % per_row)
        x = (plugin_width + 1) * pos
        if pos == 0:
            y = y + plugin_height + 1

    # Footswitches
    p2 = Panel(box = Box.xywh(0,180,display_width,footswitch_height))
    colors = ["white", "lime", "blue"]
    x = 0
    y = footswitch_height - plugin_height
    for i in range(0, 3):
        footswitch = Widget(box=Box.xywh(x, y, plugin_width, plugin_height), outline_radius=5, parent=p2)
        footswitch.set_outline(2, "black")
        footswitch.set_background(colors[i-1])
        footswitch.set_foreground((0, 255, 0))
        pos = (i % per_row) + 1
        x = (plugin_width + 37) * pos

    # Render
    pstack.push_panel(p2)
    p2.refresh()
    pstack.push_panel(p)
    p.refresh()

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
