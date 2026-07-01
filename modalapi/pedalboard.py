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
import lilv  # pyright: ignore[reportMissingImports] -- lilv is system-installed
import logging
import os
import requests as req
import sys
import urllib.parse
from typing import Optional

import common.token as Token

import common.util as util
import common.parameter as Parameter
import modalapi.plugin as Plugin
from modalapi.connections import Connection, build_connection
from modalapi.plugin_customization import Customizer, default_customizer


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

        self.world = lilv.World()

        # this is needed when loading specific bundles instead of load_all
        # (these functions are not exposed via World yet)
        self.world.load_specifications()
        self.world.load_plugin_classes()

        self.uri_arc = self.world.new_uri("http://drobilla.net/ns/ingen#arc")
        self.uri_block = self.world.new_uri("http://drobilla.net/ns/ingen#block")
        self.uri_canvas_x = self.world.new_uri("http://drobilla.net/ns/ingen#canvasX")
        self.uri_canvas_y = self.world.new_uri("http://drobilla.net/ns/ingen#canvasY")
        self.uri_head = self.world.new_uri("http://drobilla.net/ns/ingen#head")
        self.uri_port = self.world.new_uri("http://lv2plug.in/ns/lv2core#port")
        self.uri_tail = self.world.new_uri("http://drobilla.net/ns/ingen#tail")
        self.uri_value = self.world.new_uri("http://drobilla.net/ns/ingen#value")
        self.uri_instance_number = self.world.new_uri("http://moddevices.com/ns/modpedal#instanceNumber")

    def get_pedalboard_plugin(self, world, bundlepath):
        # lilv wants the last character as the separator
        bundle = os.path.abspath(bundlepath)
        if not bundle.endswith(os.sep):
            bundle += os.sep
        # convert bundle string into a lilv node
        bundlenode = self.world.new_file_uri(None, bundle)

        # load the bundle
        self.world.load_bundle(bundlenode)

        # free bundlenode, no longer needed
        # self.world.node_free(bundlenode)  # TODO find out why this is no longer necessary (why did API method go away)

        # get all plugins in the bundle
        ps = self.world.get_all_plugins()

        # make sure the bundle includes 1 and only 1 plugin (the pedalboard)
        if len(ps) != 1:
            raise Exception("get_pedalboard_info({}) - bundle has 0 or > 1 plugin".format(bundle))

        # no indexing in python-lilv yet, just get the first item
        plugin = None
        for p in ps:
            plugin = p
            break

        if plugin is None:
            raise Exception("get_pedalboard_plugin({}) - no plugin found".format(bundle))

        return plugin

    def get_plugin_data(self, uri):
        url = self.root_uri + "effect/get?uri=" + urllib.parse.quote(uri)
        try:
            resp = req.get(url, headers={"Cache-Control": "no-cache", "Pragma": "no-cache"})
        except:  # TODO
            logging.error("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            logging.error("mod-host not able to get plugin data: %s\nStatus: %s" % (url, resp.status_code))
            return {}
            # sys.exit()

        return json.loads(resp.text)

    def _coord(self, block, uri) -> float:
        """Read an ingen canvas coordinate (float literal) off a block."""
        node = self.world.get(block, uri, None)
        if node is None:
            return 0.0
        try:
            return float(str(node))
        except ValueError:
            return 0.0

    # Get info from an lv2 bundle
    # @a bundle is a string, consisting of a directory in the filesystem (absolute pathname).
    def load_bundle(self, bundlepath, plugin_dict):
        # Load the bundle, return the single plugin for the pedalboard
        plugin = self.get_pedalboard_plugin(self.world, bundlepath)

        # check if the plugin is a pedalboard
        def fill_in_type(node):
            if node is not None and node.is_uri():
                return node
            return None

        u = self.world.new_uri("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")
        plugin_types = [i for i in util.LILV_FOREACH(plugin.get_value(u), fill_in_type)]
        if "http://moddevices.com/ns/modpedal#Pedalboard" not in plugin_types:
            raise Exception(f"get_pedalboard_info({bundlepath}) - plugin has no mod:Pedalboard type")

        # Iterate blocks (plugins). Order is imposed afterward from canvas
        # coordinates (see below), so block iteration order doesn't matter.
        all_plugins: list[Plugin.Plugin] = []
        instance_to_info: dict[str, Optional[dict]] = {}
        blocks = plugin.get_value(self.uri_block)
        for block in blocks:
            if block is None or block.is_blank():
                continue

            # Add plugin data (from plugin registry) to global plugin dictionary
            plugin_info = {}
            category = None
            plugin_uri = None
            prototype = self.world.find_nodes(block, self.world.ns.lv2.prototype, None)
            if len(prototype) > 0:
                # logging.debug("prototype %s" % prototype[0])
                plugin_uri = str(prototype[0])  # plugin.get_uri()
                if plugin_uri not in plugin_dict:
                    plugin_info = self.get_plugin_data(plugin_uri)
                    if plugin_info:
                        logging.debug("added %s" % plugin_uri)
                        plugin_dict[plugin_uri] = plugin_info
                else:
                    plugin_info = plugin_dict[plugin_uri]
                if plugin_info is not None:
                    cat = util.DICT_GET(plugin_info, Token.CATEGORY)
                    if cat is not None and len(cat) > 0:
                        category = cat[0]

            # Extract Parameter data
            instance_id = str(block.get_path()).replace(bundlepath, "", 1).lstrip("/")
            nodes = self.world.find_nodes(block, self.world.ns.lv2.port, None)
            parameters = {}
            if len(nodes) > 0:
                # These are the port nodes used to define parameter controls
                for port in nodes:
                    param_value = self.world.get(port, self.uri_value, None)
                    # logging.debug("port: %s  value: %s" % (port, param_value))
                    binding = self.world.get(port, self.world.ns.midi.binding, None)
                    if binding is not None:
                        controller_num = self.world.get(binding, self.world.ns.midi.controllerNumber, None)
                        channel = self.world.get(binding, self.world.ns.midi.channel, None)
                        if (controller_num is not None) and (channel is not None):
                            binding = "%d:%d" % (
                                self.world.new_int(int(channel)),
                                self.world.new_int(int(controller_num)),
                            )
                            logging.debug("  MIDI CC binding %s" % binding)
                    path = str(port)
                    symbol = os.path.basename(path)
                    value = None
                    if param_value is not None:
                        if param_value.is_float():
                            value = float(self.world.new_float(param_value))
                        elif param_value.is_int():
                            value = int(self.world.new_int(int(param_value)))
                        else:
                            value = str(value)
                    # Bypass "parameter" is a special case without an entry in the plugin definition
                    if symbol == Token.COLON_BYPASS:
                        info = {
                            "shortName": "bypass",
                            "symbol": symbol,
                            "ranges": {"minimum": 0, "maximum": 1},
                        }  # TODO tokenize
                        v = 0.0 if value == 0 else 1.0
                        param = Parameter.Parameter(info, v, binding, instance_id)
                        parameters[symbol] = param
                        continue  # don't try to find matching symbol in plugin_dict
                    # Try to find a matching symbol in plugin_dict to obtain the remaining param details
                    try:
                        plugin_params = (plugin_info or {})[Token.PORTS][Token.CONTROL][Token.INPUT]
                    except KeyError:
                        logging.warning("plugin port info not found, could be missing LV2 for: %s", instance_id)
                        continue
                    for pp in plugin_params:
                        sym = util.DICT_GET(pp, Token.SYMBOL)
                        if sym == symbol:
                            # logging.debug("PARAM: %s %s %s" % (util.DICT_GET(pp, 'name'), info[uri], category))
                            param = Parameter.Parameter(pp, value, binding, instance_id)
                            # logging.debug("Param: %s %s %4.2f %4.2f %s" % (param.name, param.symbol, param.minimum, value, binding))
                            parameters[symbol] = param

                    # logging.debug("  Label: %s" % label)
            n_int: int | None = None
            n_node = self.world.get(block, self.uri_instance_number, None)
            if n_node is not None:
                try:
                    n_int = int(str(n_node))
                except ValueError:
                    logging.debug("Non-integer pedal:instanceNumber on %s: %r", instance_id, n_node)
            c = self._customizer(plugin_uri, bundlepath, n_int)
            inst = Plugin.Plugin(
                instance_id,
                parameters,
                plugin_info,
                category,
                uri=plugin_uri,
                customization=c,
                instance_number=n_int,
            )
            inst.canvas_x = self._coord(block, self.uri_canvas_x)
            inst.canvas_y = self._coord(block, self.uri_canvas_y)
            instance_to_info[instance_id.lstrip("/")] = plugin_info
            all_plugins.append(inst)
            # logging.debug("dump: %s" % inst.to_json())

        # Order by MOD-UI canvas position: left-to-right (audio flow), then
        # top-to-bottom. Deterministic regardless of lilv's block iteration
        # order; instance_id breaks any exact-coordinate tie.
        self.plugins = sorted(all_plugins, key=lambda p: (p.canvas_x, p.canvas_y, p.instance_id))

        self.connections = self._extract_connections(plugin, bundlepath, instance_to_info)

        # Capture parse-time snapshot of all parameter values for Reset
        for plugin in self.plugins:
            plugin.pedalboard_snapshot = {
                sym: float(p.value) if p.value is not None else 0.0 for sym, p in plugin.parameters.items()
            }

        # Done obtaining relevant lilv for the pedalboard
        return

    def _extract_connections(
        self,
        pedalboard_plugin,
        bundlepath: str,
        instance_to_info: dict[str, Optional[dict]],
    ) -> list[Connection]:
        """Enumerate ingen:arc objects on the pedalboard and resolve each to a
        Connection. Mirrors mod-ui's approach (utils_lilv.cpp:4992)."""
        connections: list[Connection] = []
        arcs = pedalboard_plugin.get_value(self.uri_arc)
        if arcs is None:
            return connections
        for arc in arcs:
            if arc is None:
                continue
            tail = self.world.get(arc, self.uri_tail, None)
            head = self.world.get(arc, self.uri_head, None)
            if tail is None or head is None:
                continue
            try:
                connections.append(
                    build_connection(
                        str(tail),
                        str(head),
                        bundlepath,
                        instance_to_info,
                    )
                )
            except Exception as e:
                logging.warning("Failed to parse arc %s -> %s: %s", tail, head, e)
        return connections

    def _build_plugin(self, instance_id: str, uri: str, x: float, y: float, info: dict) -> Optional[Plugin.Plugin]:
        """Build a Plugin from REST metadata (no LILV). Used for dynamic adds.

        Parameters start at REST defaults; bypass is set false. MIDI bindings
        arrive later via midi_map WS messages; values arrive via param_set.
        Returns None if info is empty (unknown plugin URI).
        """
        if not info:
            return None

        category = None
        cat = util.DICT_GET(info, Token.CATEGORY)
        if cat and len(cat) > 0:
            category = cat[0]

        parameters: dict[str, Parameter.Parameter] = {}

        bypass_info: dict = {
            "shortName": "bypass",
            "symbol": Token.COLON_BYPASS,
            "ranges": {"minimum": 0, "maximum": 1},
        }
        parameters[Token.COLON_BYPASS] = Parameter.Parameter(bypass_info, 0.0, None, instance_id)

        try:
            plugin_params = info[Token.PORTS][Token.CONTROL][Token.INPUT]
        except KeyError:
            plugin_params = []

        for pp in plugin_params:
            sym = util.DICT_GET(pp, Token.SYMBOL)
            if not sym:
                continue
            ranges = util.DICT_GET(pp, Token.RANGES) or {}
            default_val = ranges.get("default")
            parameters[sym] = Parameter.Parameter(pp, default_val, None, instance_id)

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
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
