#!/usr/bin/env python

from abc import ABC, abstractmethod

class Lcd(ABC):

    def __init__(self):
        pass

    @abstractmethod
    def splash_show(self):
        pass

    @abstractmethod
    def cleanup(self):
        pass

    @abstractmethod
    def clear(self):
        pass

    # Menu Screens (uses deep_edit image and draw objects)
    @abstractmethod
    def menu_show(self, page_title, menu_items):
        pass

    @abstractmethod
    def menu_highlight(self, index):
        pass

    # Parameter Value Edit
    @abstractmethod
    def draw_value_edit(self, plugin_name, parameter, value):
        pass

    @abstractmethod
    def draw_value_edit_graph(self, parameter, value):
        pass

    @abstractmethod
    def draw_title(self, pedalboard, preset, invert_pb, invert_pre):
        pass

    # Analog Assignments (Tweak, Expression Pedal, etc.)
    @abstractmethod
    def draw_analog_assignments(self, controllers):
        pass

    @abstractmethod
    def draw_info_message(self, text):
        pass

    # Plugins
    @abstractmethod
    def draw_plugin_select(self, plugin=None):
        pass

    @abstractmethod
    def draw_bound_plugins(self, plugins, footswitches):
        pass

    @abstractmethod
    def draw_plugins(self, plugins):
        pass
