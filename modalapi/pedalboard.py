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


class Pedalboard:

    def __init__(self, title, bundle):
        self.root_uri = "http://localhost:80/"
        self.title = title
        self.bundle = bundle  # TODO used?
        self.plugins = []

        self.world = lilv.World()

        # this is needed when loading specific bundles instead of load_all
        # (these functions are not exposed via World yet)
        self.world.load_specifications()
        self.world.load_plugin_classes()

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
        #self.world.node_free(bundlenode)  # TODO find out why this is no longer necessary (why did API method go away)

        # get all plugins in the bundle
        ps = self.world.get_all_plugins()

        # make sure the bundle includes 1 and only 1 plugin (the pedalboard)
        if len(ps) != 1:
            raise Exception('get_pedalboard_info(%s) - bundle has 0 or > 1 plugin'.format(bundle))

        # no indexing in python-lilv yet, just get the first item
        plugin = None
        for p in ps:
            plugin = p
            break

        if plugin is None:
            raise Exception('get_pedalboard_plugin(%s)'.format(bundle))

        return plugin

    def get_plugin_data(self, uri):
        url = self.root_uri + "effect/get?uri=" + urllib.parse.quote(uri)
        try:
            resp = req.get(url, headers={'Cache-Control': 'no-cache', 'Pragma': 'no-cache'})
        except:  # TODO
            logging.error("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            logging.error("mod-host not able to get plugin data: %s\nStatus: %s" % (url, resp.status_code))
            return {}
            #sys.exit()

        return json.loads(resp.text)

    # Get info from an lv2 bundle
    # @a bundle is a string, consisting of a directory in the filesystem (absolute pathname).
    def load_bundle(self, bundlepath, plugin_dict):
        # Load the bundle, return the single plugin for the pedalboard
        plugin = self.get_pedalboard_plugin(self.world, bundlepath)

        # check if the plugin is a pedalboard
        #def fill_in_type(node):
        #   print("%s" % node)
        #    return ("%s" % node)

        # TODO XXX deterimine if OK to avoid this check
        #plugin_types = [i for i in util.LILV_FOREACH(plugin.get_value(ns_rdf.type_), fill_in_type)]

        #if "http://moddevices.com/ns/modpedal#Pedalboard" not in plugin_types:
        #    raise Exception('get_pedalboard_info(%s) - plugin has no mod:Pedalboard type'.format(bundle))

        # plugins
        u = self.world.new_uri("http://drobilla.net/ns/ingen#block")
        blocks = plugin.get_value(u)
        for block in blocks:
            if block is None or block.is_blank():
                continue

            # TODO XXX add this back
            # protouri1 = world.find_nodes(block, ns_prototype, None)
            # protouri2 = world.find_nodes(block, ns_ingen, None)
            # #print("%s %s" % (protouri1, protouri2))
            # if len(protouri1) > 0:
            #     proto = protouri1[0]
            # elif len(protouri2) > 0:
            #     proto = protouri2[0]
            # else:
            #     continue
            #
            # continue
            #
            # print("&&&&&&&&&&&&&&&&&& %s" % proto)
            # # TODO remove unused vars and queries of unused fields

            # Add plugin data (from plugin registry) to global plugin dictionary
            plugin_info = {}
            prototype = self.world.find_nodes(block, self.world.ns.lv2.prototype, None)
            if len(prototype) > 0:
                logging.debug("prototype %s" % prototype[0])
                plugin_uri = str(prototype[0])  # plugin.get_uri()
                if plugin_uri not in plugin_dict:
                    plugin_info = self.get_plugin_data(plugin_uri)
                    if plugin_info:
                        logging.debug("added %s" % plugin_uri)
                        plugin_dict[plugin_uri] = plugin_info
                else:
                    plugin_info = plugin_dict[plugin_uri]
                #category = util.DICT_GET(plugin_info, Token.CATEGORY)

            # Extract Parameter data
            instance_id = str(block.get_path()).replace(bundlepath, "", 1)
            nodes = self.world.find_nodes(block, self.world.ns.lv2.port, None)
            parameters = {}
            if len(nodes) > 0:
                # These are the port nodes used to define parameter controls
                for port in nodes:
                    u = self.world.new_uri("http://drobilla.net/ns/ingen#value")
                    param_value = self.world.get(port, u, None)
                    #logging.debug("port: %s  value: %s" % (port, param_value))
                    binding = self.world.get(port, self.world.ns.midi.binding, None)
                    if binding is not None:
                        controller_num = self.world.get(binding, self.world.ns.midi.controllerNumber, None)
                        channel = self.world.get(binding, self.world.ns.midi.channel, None)
                        if (controller_num is not None) and (channel is not None):
                            binding = "%d:%d" % (self.world.new_int(channel), self.world.new_int(controller_num))
                            logging.debug("  binding %s" % binding)
                    path = str(port)
                    symbol = os.path.basename(path)
                    value = None
                    if param_value is not None:
                        if param_value.is_float():
                            value = float(self.world.new_float(param_value))
                        elif param_value.is_int():
                            value = int(self.world.new_int(param_value))
                        else:
                            value = str(value)
                    # Bypass "parameter" is a special case without an entry in the plugin definition
                    if symbol == Token.COLON_BYPASS:
                        info = {"shortName": "bypass", "symbol": symbol, "ranges": {"minimum": 0, "maximum": 1}}  # TODO tokenize
                        v = False if value is 0 else True
                        param = Parameter.Parameter(info, v, binding)
                        parameters[symbol] = param
                        continue  # don't try to find matching symbol in plugin_dict
                    # Try to find a matching symbol in plugin_dict to obtain the remaining param details
                    try:
                        plugin_params = plugin_info[Token.PORTS][Token.CONTROL][Token.INPUT]
                    except KeyError:
                        logging.warning("plugin port info not found, could me missing LV2 for: %s", instance_id)
                        continue
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
