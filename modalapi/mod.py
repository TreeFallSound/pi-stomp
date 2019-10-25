#!/usr/bin/env python

import json
import lilv
import os
import requests as req
import sys
import urllib.parse

sys.path.append('/usr/lib/python3.5/site-packages')  # TODO possibly /usr/local/modep/mod-ui
from mod.development import FakeHost as Host


def LILV_FOREACH(collection, func):
    itr = collection.begin()
    while itr:
        yield func(collection.get(itr))
        itr = collection.next(itr)


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

class Mod:
    __single = None

    def __init__(self, lcd):
        print("Init mod")
        if Mod.__single:
            raise Mod.__single
        Mod.__single = self

        self.lcd = lcd
        self.root_uri = "http://localhost:80/"
        # TODO construct pblist, current at each call in case changes made via UI
        # unless performance sucks that way
        self.param_list = []
        self.pedalboards = []
        self.current_pedalboard_index = 0
        self.current_preset_index = 0
        self.current_num_presets = 0

        self.plugin_dict = {}

        # TODO should this be here?
        #self.load_pedalboards()

        # Create dummy host for obtaining pedalboard info
        self.host = Host(None, None, self.msg_callback)


    def load_pedalboards(self):
        url = self.root_uri + "pedalboard/list"

        try:
            resp = req.get(url)
        except:  # TODO
            print("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            print("Cannot connect to mod-host.  Status: %s" % resp.status_code)
            sys.exit()

        self.pedalboards = json.loads(resp.text)
        #print(self.pedalboard_list)
        #self.load_pedalboard_plugins()
        for pb in self.pedalboards:
            print("Loading pedalboard info: %s" % pb['title'])
            bundle = pb['bundle']
            self.get_pedalboard_info(bundle)
        return self.pedalboards

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

    # Get info from an lv2 bundle
    # @a bundle is a string, consisting of a directory in the filesystem (absolute pathname).
    def get_pedalboard_info(self, bundlepath):
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

        plugin_types = [i for i in LILV_FOREACH(plugin.get_value(ns_rdf.type_), fill_in_type)]

        if "http://moddevices.com/ns/modpedal#Pedalboard" not in plugin_types:
            raise Exception('get_pedalboard_info(%s) - plugin has no mod:Pedalboard type'.format(bundle))

        # let's get all the info now
        # Mod ala pi controllers.  Add one entry for each control, keyed by the associated CC
        # Example using 4 knobs and 3 switches  90:{},
        # TODO Should likely include midi channel in the key
        info = {1: {}, 7: {}, 16: {}, 109: {}}

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

            plugin_uri = lilv.lilv_node_as_uri(protouri1)
            #print("  Plugin: %s" % plugin_uri)
            if plugin_uri not in self.plugin_dict:
                data = self.get_plugin_data(plugin_uri)
                if data:
                    # print(data)
                    print("  added %s" % plugin_uri)
                    self.plugin_dict[plugin_uri] = data

            # XXX TODO Use this eventually for detailed pedalboard port info (return a dict instead of a simple list)
            instance = lilv.lilv_uri_to_path(lilv.lilv_node_as_string(block.me)).replace(bundlepath, "", 1)
            uri = lilv.lilv_node_as_uri(proto)
            enabled = lilv.lilv_world_get(world.me, block.me, ns_ingen.enabled.me, None)
            nodes = lilv.lilv_world_find_nodes(world.me, block.me, ns_lv2core.port.me, None)  # nodes > ports
            if nodes is not None:
                # These are the port nodes used to define parameter controls
                nodes_it = lilv.lilv_nodes_begin(nodes)
                while not lilv.lilv_nodes_is_end(nodes, nodes_it):
                    port = lilv.lilv_nodes_get(nodes, nodes_it)
                    nodes_it = lilv.lilv_nodes_next(nodes, nodes_it)
                    param_value = lilv.lilv_world_get(world.me, port, ns_ingen.value.me, None)
                    binding = lilv.lilv_world_get(world.me, port, ns_midi.binding.me, None)
                    # if binding is not None:
                    # Only interested in ports which have controller bindings
                    controller_num = lilv.lilv_world_get(world.me, binding, ns_midi.controllerNumber.me, None)
                    if controller_num is not None:
                        cnum = lilv.lilv_node_as_int(controller_num)
                        # if cnum in info:
                        # This binding is to one of our controls, store its details in controller dict
                        path = lilv.lilv_node_as_string(port)
                        info[uri] = {
                            "instance": instance,
                            'uri': uri,
                            "parameter": os.path.basename(path),
                            "value": lilv.lilv_node_as_float(param_value)
                        }
        # print("info: %s" % info)
        return info


    def get_plugin_data(self, uri):
        url = self.root_uri + "effect/get?uri=" + urllib.parse.quote(uri)
        print(url)
        try:
            resp = req.get(url)
        except:  # TODO
            print("Cannot connect to mod-host.")
            sys.exit()

        if resp.status_code != 200:
            print("Cannot connect to mod-host.  Status: %s" % resp.status_code)
            sys.exit()

        return resp.text


    # TODO change these functions ripped from modep
    def get_current_pedalboard(self):
        url = self.root_uri + "pedalboard/current"
        try:
            resp = req.get(url)
            # TODO pass code define
            if resp.status_code == 200:
                return resp.text
        except:
            return None

    def get_current_pedalboard_name(self):
        pb = self.get_current_pedalboard()
        return os.path.splitext(os.path.basename(pb))[0]

    def get_current_pedalboard_index(self, pedalboards, current):
        try:
            return pedalboards.index(current)
        except:
            return None

    def get_bundlepath(self, index):
        pedalboard = self.pedalboards[index]
        if pedalboard == None:
            print("Pedalboard with index %d not found" % index)
            # TODO error handling
            return None
        return self.pedalboards[index]['bundle']

    def msg_callback(self, msg):
        print(msg)

    def pedalboard_init(self):
        # Get current pedalboard - TODO refresh when PB changes
        url = self.root_uri + "pedalboard/current"
        resp = req.get(url)
        pedalboard_name = os.path.splitext(os.path.basename(resp.text))[0]
        print("Getting Pedalboard: %s" % pedalboard_name)
        bundle = "/usr/local/modep/.pedalboards/%s.pedalboard" % pedalboard_name
        pedalboard = (next(item for item in self.pedalboards if item['bundle'] == bundle))
        self.current_pedalboard_index = self.pedalboards.index(pedalboard)
        print("  Index: %d" % self.current_pedalboard_index)


        # Preset info
        # TODO should this be here?
        plugins = []  # TODO
        bundlepath = self.get_bundlepath(self.current_pedalboard_index)
        print("bundle: %s" % bundlepath)

        self.host.load(bundlepath, False)
        #var = self.host.load_pb_presets(plugins, bundlepath)
        self.current_num_presets = len(self.host.pedalboard_presets)
        print("len: %d" % len(self.host.pedalboard_presets))
        print(self.host.plugins)

        # Plugin info



        # Pedalboard info
        # info = pb.get_pedalboard_info(resp.text)
        # param_list = list()
        # for key, param in info.items():
        #     if param != {}:
        #          p = param['instance'].capitalize() + ":" + param['parameter'].upper()
        #          print(p)
        #          param_list.append(p)
        # print(len(param_list))

        # lcd_draw_text_rows(pedalboard_name, param_list)

    def get_current_preset_name(self):
        return self.host.pedalpreset_name(self.current_preset_index)

    def preset_change(self, encoder, clk_pin):
        enc = encoder.get_data()
        index = ((self.current_preset_index - 1) if (enc == 1)
                 else (self.current_preset_index + 1)) % self.current_num_presets
        print("preset change: %d" % index)
        url = "http://localhost/pedalpreset/load?id=%d" % index
        print(url)
        # req.get("http://localhost/reset")
        resp = req.get(url)
        if resp.status_code != 200:
            print("Bad Rest request: %s status: %d" % (url, resp.status_code))
        self.current_preset_index = index

        # TODO move formatting to common place
        # TODO name varaibles so they don't have to be calculated
        text = "%s-%s" % (self.get_current_pedalboard_name(), self.get_current_preset_name())
        self.lcd.draw_text_rows(text)
