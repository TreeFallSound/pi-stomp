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

    def __init__(self, cwd, handler=None):
        # expects cwd (current working directory)
        pass

    @abstractmethod
    def splash_show(self, boot=True):
        pass

    @abstractmethod
    def clear(self):
        pass

    @abstractmethod
    def erase_all(self):
        pass

    @abstractmethod
    def clear_select(self):
        pass

    # Toolbar
    @abstractmethod
    def draw_tools(self, wifi_type, bypass_type, system_type):
        pass

    @abstractmethod
    def update_wifi(self, wifi_status):
        pass

    @abstractmethod
    def update_bypass(self, bypass):
        pass

    @abstractmethod
    def draw_tool_select(self, tool_type):
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
    def draw_title(self, pedalboard, preset, invert_pb, invert_pre, highlight_only):
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

    @abstractmethod
    def refresh_plugins(self):
        pass

    @abstractmethod
    def refresh_zone(self, zone_idx):
        pass

    @abstractmethod
    def shorten_name(self):
        pass
