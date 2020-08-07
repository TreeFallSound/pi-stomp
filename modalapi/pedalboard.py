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
import lilv
import logging
import os
import requests as req
import sys
import urllib.parse

import common.token as Token
import common.util as util
import modalapi.parameter as Parameter
import modalapi.plugin as Plugin


class NS(object):
    def __init__(self, world, base):
        self.world = world
        self.base = base
        self._cache = {}

    def __getattr__(self, attr):
        if attr.endswith("_"):
            attr = attr[:-1]
        if attr not in self._cache:
            self._cache[attr] = lilv.Node(self.world.new_uri(self.base+attr))
        return self._cache[attr]


class Pedalboard:

    def __init__(self, title, bundle):
        self.root_uri = "http://localhost:80/"
        self.title = title
        self.bundle = bundle
        self.plugins = []

    def get_pedalboard_plugin(self, world, bundlepath):
        # lilv wants the last character as the separator
        bundle = os.path.abspath(bundlepath)
        if not bundle.endswith(os.sep):
            bundle += os.sep

        # convert bundle string into a lilv node
        bundlenode = lilv.lilv_new_file_uri(world.me, None, bundle)

        # load the bundle
        world.load_bundle(bundlenode)

        # free bundlenode, no longer needed
        lilv.lilv_node_free(bundlenode)

        # get all plugins in the bundle
        plugins = world.get_all_plugins()

        # make sure the bundle includes 1 and only 1 plugin (the pedalboard)
        if plugins.size() != 1:
            raise Exception('get_pedalboard_info(%s) - bundle has 0 or > 1 plugin'.format(bundle))

        # no indexing in python-lilv yet, just get the first item
        plugin = None
        for p in plugins:
            plugin = p
            break

        if plugin is None:
            raise Exception('get_pedalboard_info(%s) - failed to get plugin, you are using an old lilv!'.format(bundle))

        return plugin

    def get_plugin_data(self, uri):
        url = self.root_uri + "effect/get?uri=" + urllib.parse.quote(uri)
        try:
            resp = req.get(url)
        except:  # TODO
            logging.error("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            logging.error("Cannot connect to mod-host for plugin data: %s\nStatus: %s" % (url, resp.status_code))
            sys.exit()

        return json.loads(resp.text)

    # Get info from an lv2 bundle
    # @a bundle is a string, consisting of a directory in the filesystem (absolute pathname).
    def load_bundle(self, bundlepath, plugin_dict):
        # Create our own unique lilv world
        # We'll load a single bundle and get all plugins from it
        world = lilv.World()

        # this is needed when loading specific bundles instead of load_all
        # (these functions are not exposed via World yet)
        lilv.lilv_world_load_specifications(world.me)
        lilv.lilv_world_load_plugin_classes(world.me)

        # Load the bundle, return the single plugin for the pedalboard
        plugin = self.get_pedalboard_plugin(world, bundlepath)

        # define the needed stuff
        ns_rdf = NS(world, lilv.LILV_NS_RDF)
        ns_lv2core = NS(world, lilv.LILV_NS_LV2)
        ns_ingen = NS(world, "http://drobilla.net/ns/ingen#")
        ns_midi = NS(world, "http://lv2plug.in/ns/ext/midi#")

        # check if the plugin is a pedalboard
        def fill_in_type(node):
            return node.as_string()

        plugin_types = [i for i in util.LILV_FOREACH(plugin.get_value(ns_rdf.type_), fill_in_type)]

        if "http://moddevices.com/ns/modpedal#Pedalboard" not in plugin_types:
            raise Exception('get_pedalboard_info(%s) - plugin has no mod:Pedalboard type'.format(bundle))

        # plugins
        blocks = plugin.get_value(ns_ingen.block)
        it = blocks.begin()
        while not blocks.is_end(it):
            block = blocks.get(it)
            it = blocks.next(it)

            if block.me is None:
                continue

            protouri1 = lilv.lilv_world_get(world.me, block.me, ns_lv2core.prototype.me, None)
            protouri2 = lilv.lilv_world_get(world.me, block.me, ns_ingen.prototype.me, None)

            if protouri1 is not None:
                proto = protouri1
            elif protouri2 is not None:
                proto = protouri2
            else:
                continue

            # TODO remove unused vars and queries of unused fields
            # Add plugin data (from plugin registry) to global plugin dictionary
            plugin_uri = lilv.lilv_node_as_uri(protouri1)
            plugin_info = {}
            if plugin_uri not in plugin_dict:
                plugin_info = self.get_plugin_data(plugin_uri)
                if plugin_info:
                    logging.debug("added %s" % plugin_uri)
                    plugin_dict[plugin_uri] = plugin_info
            else:
                plugin_info = plugin_dict[plugin_uri]
            category = util.DICT_GET(plugin_info, Token.CATEGORY)

            # Extract Parameter data
            instance_id = lilv.lilv_uri_to_path(lilv.lilv_node_as_string(block.me)).replace(bundlepath, "", 1)
            uri = lilv.lilv_node_as_uri(proto)
            enabled = lilv.lilv_world_get(world.me, block.me, ns_ingen.enabled.me, None)
            nodes = lilv.lilv_world_find_nodes(world.me, block.me, ns_lv2core.port.me, None)  # nodes > ports
            parameters = {}
            if nodes is not None:
                # These are the port nodes used to define parameter controls
                nodes_it = lilv.lilv_nodes_begin(nodes)
                while not lilv.lilv_nodes_is_end(nodes, nodes_it):
                    port = lilv.lilv_nodes_get(nodes, nodes_it)
                    nodes_it = lilv.lilv_nodes_next(nodes, nodes_it)
                    param_value = lilv.lilv_world_get(world.me, port, ns_ingen.value.me, None)
                    binding = lilv.lilv_world_get(world.me, port, ns_midi.binding.me, None)
                    if binding is not None:
                        controller_num = lilv.lilv_world_get(world.me, binding, ns_midi.controllerNumber.me, None)
                        channel = lilv.lilv_world_get(world.me, binding, ns_midi.channel.me, None)
                        if (controller_num is not None) and (channel is not None):
                            binding = "%d:%d" %(lilv.lilv_node_as_int(channel), lilv.lilv_node_as_int(controller_num))
                    path = lilv.lilv_node_as_string(port)
                    symbol = os.path.basename(path)
                    value = lilv.lilv_node_as_float(param_value)
                    # Bypass "parameter" is a special case without an entry in the plugin definition
                    if symbol == Token.COLON_BYPASS:
                        info = {"shortName": "bypass", "symbol": symbol, "ranges": {"minimum": 0, "maximum": 1}}  # TODO tokenize
                        param = Parameter.Parameter(info, value, binding)
                        parameters[symbol] = param
                        continue  # don't try to find matching symbol in plugin_dict
                    # Try to find a matching symbol in plugin_dict to obtain the remaining param details
                    plugin_params = plugin_info[Token.PORTS][Token.CONTROL][Token.INPUT]
                    for pp in plugin_params:
                        sym = util.DICT_GET(pp, Token.SYMBOL)
                        if sym == symbol:
                            #logging.debug("PARAM: %s %s %s" % (util.DICT_GET(pp, 'name'), info[uri], category))
                            param = Parameter.Parameter(pp, value, binding)
                            logging.debug("Param: %s %s %4.2f %4.2f" % (param.name, param.symbol, param.minimum, value))
                            parameters[symbol] = param

                    #logging.debug("  Label: %s" % label)
            inst = Plugin.Plugin(instance_id, parameters, plugin_info)
            self.plugins.append(inst)
            #logging.debug("dump: %s" % inst.to_json())
        return

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)
