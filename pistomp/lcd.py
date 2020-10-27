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

from abc import ABC, abstractmethod


class Lcd(ABC):

    def __init__(self, cwd):
        # expects cwd (current working directory)
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

    @abstractmethod
    def erase_all(self):
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
