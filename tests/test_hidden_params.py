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

"""Ports a plugin exposes but no UI may paint.

Two sources: the port's own LV2 metadata (`is_hidden_port`, mirroring mod-ui's
"badports"), and the curated `hidden_params` for ports declaring nothing.
Hidden is a display exclusion — the Parameter stays in `plugin.parameters`.
"""

import pytest

from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol, is_hidden_port
from modalapi.plugin import Plugin
from modalapi.plugin_customization import PluginCustomization


def _port(symbol: str, *, properties: list[str] | None = None, designation: str | None = None) -> PortInfo:
    info = PortInfo(symbol=symbol, shortName=symbol, ranges={"minimum": 0.0, "maximum": 1.0, "default": 0.0})
    if properties is not None:
        info["properties"] = properties
    if designation is not None:
        info["designation"] = designation
    return info


def _plugin(ports: list[PortInfo], customization: PluginCustomization | None = None) -> Plugin:
    params = {Symbol(p["symbol"]): Parameter(p, 0.0, None, "inst") for p in ports}
    params[BYPASS_SYMBOL] = Parameter(_port(BYPASS_SYMBOL), 0.0, None, "inst")
    return Plugin("inst", params, {}, None, uri="urn:test", customization=customization)


class TestIsHiddenPort:
    def test_plain_port_is_visible(self):
        assert not is_hidden_port(_port("gain"))

    def test_not_on_gui_is_hidden(self):
        assert is_hidden_port(_port("thresholdRMS", properties=["notOnGUI"]))

    @pytest.mark.parametrize(
        "designation",
        [
            "http://lv2plug.in/ns/lv2core#enabled",
            "http://lv2plug.in/ns/lv2core#freeWheeling",
            "http://ardour.org/lv2/processing#enable",
            "http://lv2plug.in/ns/ext/time#beatsPerMinute",
        ],
    )
    def test_designated_host_ports_are_hidden(self, designation):
        assert is_hidden_port(_port("BYPASS", designation=designation))

    def test_unrecognised_designation_is_visible(self):
        # parameters#attack is a real, editable control — designation alone is not disqualifying.
        assert not is_hidden_port(_port("attack", designation="http://lv2plug.in/ns/ext/parameters#attack"))


class TestVisibleParameters:
    def test_metadata_hidden_port_is_not_visible(self):
        # guitarix names it BYPASS and designates it `enabled`; mod-host writes the
        # inverse of the bypass value into it, so it *is* :bypass.
        plugin = _plugin([
            _port("BYPASS", designation="http://lv2plug.in/ns/lv2core#enabled"),
            _port("drive"),
        ])
        assert set(plugin.visible_parameters) == {BYPASS_SYMBOL, Symbol("drive")}

    def test_curated_symbol_is_not_visible(self):
        plugin = _plugin(
            [_port("bypass"), _port("threshold")],
            PluginCustomization(hidden_params=frozenset({Symbol("bypass")})),
        )
        assert set(plugin.visible_parameters) == {BYPASS_SYMBOL, Symbol("threshold")}

    def test_hidden_param_is_retained_in_parameters(self):
        """Hiding is a display exclusion. The Parameter must survive so MIDI
        bindings, pedalboard_snapshot/Reset and param_set echo still work."""
        plugin = _plugin(
            [_port("lv2_freewheel", designation="http://lv2plug.in/ns/lv2core#freeWheeling")],
            PluginCustomization(hidden_params=frozenset({Symbol("bypass")})),
        )
        assert Symbol("lv2_freewheel") in plugin.parameters
        assert plugin.parameters[Symbol("lv2_freewheel")].hidden
