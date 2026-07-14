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

import json
import logging
import pistomp.httpclient as req
import sys
import urllib.parse
from typing import Optional


from common.parameter import BYPASS_SYMBOL, Parameter, PortInfo, Symbol, json_default
import modalapi.plugin as Plugin
from modalapi.connections import Connection, build_connection
from modalapi.plugin_customization import Customizer, default_customizer


def _bypass_info() -> PortInfo:
    # mod-ui reports bypass as a bool alongside the ports, not as a port row.
    return PortInfo(shortName="bypass", symbol=BYPASS_SYMBOL, ranges={"minimum": 0.0, "maximum": 1.0})


def _control_inputs(plugin_info: dict | None) -> list[PortInfo] | None:
    """None means the LV2 metadata is absent, distinct from a plugin that
    genuinely exposes no control inputs."""
    try:
        return (plugin_info or {})["ports"]["control"]["input"]
    except (KeyError, TypeError):
        return None


class Pedalboard:
    def __init__(self, title, bundle, root_uri="http://localhost:80/", customizer: Customizer | None = None):
        self.root_uri = root_uri
        self.title = title
        self.bundle = bundle  # TODO used?
        # Resolver injected by the composition root (handler); defaults to a
        # no-op so headless/v1 construction degrades to standard behaviour
        # instead of silently depending on plugin-package import order.
        self._customizer: Customizer = customizer or default_customizer
        self.plugins = []
        self.connections: list[Connection] = []
        self.hydrated = False

    def get_plugin_data(self, uri):
        url = self.root_uri + "effect/get?uri=" + urllib.parse.quote(uri)
        try:
            resp = req.get(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
        except Exception:  # TODO
            logging.error("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            logging.error("mod-host not able to get plugin data: %s\nStatus: %s" % (url, resp.status_code))
            return {}
            # sys.exit()

        return json.loads(resp.text)

    def get_pedalboard_info(self) -> dict:
        """mod-ui's own parse of the bundle. It walks the TTL in C++; doing it here
        through the lilv python bindings cost ~0.8s per board at startup."""
        url = self.root_uri + "pedalboard/info/?bundlepath=" + urllib.parse.quote(self.bundle)
        try:
            resp = req.get(url)
        except Exception:
            logging.error("Cannot connect to mod-ui.")
            sys.exit()

        if resp.status_code != 200:
            logging.error("mod-ui not able to get pedalboard info: %s  Status: %s" % (url, resp.status_code))
            return {}

        return json.loads(resp.text)

    @staticmethod
    def _binding(cc: dict | None) -> Optional[str]:
        # channel -1 is mod-ui's "unmapped" sentinel (utils_lilv.cpp).
        if not cc or cc.get("channel", -1) < 0:
            return None
        return "%d:%d" % (cc["channel"], cc["control"])

    def hydrate(self, plugin_dict) -> None:
        """Populate plugins and connections from mod-ui. Idempotent."""
        if self.hydrated:
            return

        info = self.get_pedalboard_info()
        if not info:
            return

        all_plugins: list[Plugin.Plugin] = []
        instance_to_info: dict[str, Optional[dict]] = {}

        for pb_plugin in info.get("plugins", []):
            instance_id = pb_plugin["instance"].lstrip("/")
            plugin_uri = pb_plugin["uri"]

            plugin_info = plugin_dict.get(plugin_uri)
            if plugin_info is None:
                plugin_info = self.get_plugin_data(plugin_uri)
                if plugin_info:
                    plugin_dict[plugin_uri] = plugin_info

            category = None
            cat = (plugin_info or {}).get("category")
            if cat is not None and len(cat) > 0:
                category = cat[0]

            parameters: dict[Symbol, Parameter] = {}
            parameters[BYPASS_SYMBOL] = Parameter(
                _bypass_info(),
                1.0 if pb_plugin.get("bypassed") else 0.0,
                self._binding(pb_plugin.get("bypassCC")),
                instance_id,
            )

            plugin_params = _control_inputs(plugin_info)
            if plugin_params is None:
                logging.warning("plugin port info not found, could be missing LV2 for: %s", instance_id)
                plugin_params = []

            by_symbol = {pp["symbol"]: pp for pp in plugin_params}
            for port in pb_plugin.get("ports", []):
                symbol = Symbol(port["symbol"])
                pp = by_symbol.get(symbol)
                if pp is None:
                    continue
                parameters[symbol] = Parameter(
                    pp,
                    float(port["value"]),
                    self._binding(port.get("midiCC")),
                    instance_id,
                )

            n_int = pb_plugin.get("instanceNumber")
            if n_int is not None and n_int < 0:
                n_int = None

            inst = Plugin.Plugin(
                instance_id,
                parameters,
                plugin_info,
                category,
                uri=plugin_uri,
                customization=self._customizer(plugin_uri, self.bundle, n_int),
                instance_number=n_int,
            )
            inst.canvas_x = float(pb_plugin.get("x", 0.0))
            inst.canvas_y = float(pb_plugin.get("y", 0.0))
            instance_to_info[instance_id] = plugin_info
            all_plugins.append(inst)

        # Order by MOD-UI canvas position: left-to-right (audio flow), then
        # top-to-bottom. instance_id breaks any exact-coordinate tie.
        self.plugins = sorted(all_plugins, key=lambda p: (p.canvas_x, p.canvas_y, p.instance_id))

        self.connections = []
        for arc in info.get("connections", []):
            try:
                # mod-ui already strips the bundle path off both endpoints.
                self.connections.append(build_connection(arc["source"], arc["target"], "", instance_to_info))
            except Exception as e:
                logging.warning("Failed to parse arc %s -> %s: %s", arc.get("source"), arc.get("target"), e)

        # Capture snapshot of all parameter values for Reset
        for plugin in self.plugins:
            plugin.pedalboard_snapshot = {
                sym: float(p.value) for sym, p in plugin.parameters.items()
            }

        self.hydrated = True

    def _build_plugin(self, instance_id: str, uri: str, x: float, y: float, info: dict) -> Optional[Plugin.Plugin]:
        """Build a Plugin from REST metadata (no LILV). Used for dynamic adds.

        Parameters start at REST defaults; bypass is set false. MIDI bindings
        arrive later via midi_map WS messages; values arrive via param_set.
        Returns None if info is empty (unknown plugin URI).
        """
        if not info:
            return None

        category = None
        cat = info.get("category")
        if cat and len(cat) > 0:
            category = cat[0]

        parameters: dict[Symbol, Parameter] = {}
        parameters[BYPASS_SYMBOL] = Parameter(_bypass_info(), 0.0, None, instance_id)

        for pp in _control_inputs(info) or []:
            sym = pp.get("symbol")
            if not sym:
                continue
            default_val = (pp.get("ranges") or {}).get("default")
            parameters[Symbol(sym)] = Parameter(
                pp, float(default_val) if default_val is not None else 0.0, None, instance_id
            )

        # TODO: extra_data can't be populated here — mod-ui's `add` WS message
        # doesn't include the numeric `pedal:instanceNumber`, so we can't address
        # effect-N/effect.ttl. A protocol change (include the instance number
        # on the wire) would let us pass the bundle + number to the customizer.
        inst = Plugin.Plugin(instance_id, parameters, info, category, uri=uri, customization=self._customizer(uri))
        inst.canvas_x = x
        inst.canvas_y = y
        return inst

    def add_connection(self, port_from: str, port_to: str) -> None:
        """Add a connection from live WS port paths (e.g. /graph/A/out → /graph/B/in)."""
        instance_to_info = {p.instance_id: p.info for p in self.plugins}
        tail = port_from.removeprefix("/graph/")
        head = port_to.removeprefix("/graph/")
        try:
            conn = build_connection(tail, head, "", instance_to_info)
            if conn not in self.connections:
                self.connections.append(conn)
        except Exception as e:
            logging.warning("Failed to add connection %s -> %s: %s", port_from, port_to, e)

    def remove_connection(self, port_from: str, port_to: str) -> None:
        """Remove a connection matching live WS port paths."""
        tail = port_from.removeprefix("/graph/")
        head = port_to.removeprefix("/graph/")
        src_id, src_sym = tail.split("/", 1) if "/" in tail else (tail, "")
        dst_id, dst_sym = head.split("/", 1) if "/" in head else (head, "")
        self.connections = [
            c
            for c in self.connections
            if not (
                c.src.id == src_id
                and c.src.port_symbol == src_sym
                and c.dst.id == dst_id
                and c.dst.port_symbol == dst_sym
            )
        ]

    def to_json(self):
        return json.dumps(self, default=json_default, sort_keys=True, indent=4)
