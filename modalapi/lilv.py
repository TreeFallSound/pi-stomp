# ------------------------------------------------------------------------------------------------------------
# Extracts important fields from a pedalboard ttl file
#
# Needed by LCD
#  - Pedalboard name 
#  - LIST of presets
#  - LIST of Effect params which are bound
#    - Effect name (instance)
#    - Param name
#    - Param value
#    - Midi channel
#    - Midi CC
#    - Max/Min for scaling
#
# TODO
#  read namespaces from top of ttl?

import lilv
import os

os.environ['LV2_PATH'] = '/usr/local/modep/.lv2'

#TODO use something like this for iterating
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

def get_pedalboard_plugin(world, bundlepath):
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

# ------------------------------------------------------------------------------------------------------------
# get_pedalboard_info

# Get info from an lv2 bundle
# @a bundle is a string, consisting of a directory in the filesystem (absolute pathname).
def get_pedalboard_info(bundlepath):
    # Create our own unique lilv world
    # We'll load a single bundle and get all plugins from it
    world = lilv.World()

    # lilv.lilv_world_load_all(world.me)
    # plugins = lilv.lilv_world_get_all_plugins(world.me)
    # if plugins is not None:
    #     # These are the port nodes used to define parameter controls
    #     plugins_it = lilv.lilv_plugins_begin(plugins)
    #     while not lilv.lilv_nodes_is_end(plugins, plugins_it):
    #         p = lilv.lilv_plugins_get(plugins, plugins_it)
    #         plugins_it = lilv.lilv_nodes_next(plugins, plugins_it)
    #         uri = lilv.lilv_plugin_get_uri(p)
    #         #logging.debug(lilv.lilv_node_as_uri(uri))

    # this is needed when loading specific bundles instead of load_all
    # (these functions are not exposed via World yet)
    lilv.lilv_world_load_specifications(world.me)
    lilv.lilv_world_load_plugin_classes(world.me)

    # Load the bundle, return the single plugin for the pedalboard
    plugin = get_pedalboard_plugin(world, bundlepath)

    # define the needed stuff
    ns_rdf      = NS(world, lilv.LILV_NS_RDF)
    ns_lv2core  = NS(world, lilv.LILV_NS_LV2)
    ns_ingen    = NS(world, "http://drobilla.net/ns/ingen#")
    ns_midi     = NS(world, "http://lv2plug.in/ns/ext/midi#")

    # check if the plugin is a pedalboard
    def fill_in_type(node):
        return node.as_string()
    plugin_types = [i for i in LILV_FOREACH(plugin.get_value(ns_rdf.type_), fill_in_type)]

    if "http://moddevices.com/ns/modpedal#Pedalboard" not in plugin_types:
        raise Exception('get_pedalboard_info(%s) - plugin has no mod:Pedalboard type'.format(bundle))

    # plugins
    plugin_list = []
    blocks = plugin.get_value(ns_ingen.block)
    it = blocks.begin()
    while not blocks.is_end(it):
        block = blocks.get(it)
        it    = blocks.next(it)

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

        #logging.debug(" Instance: %s" % lilv.lilv_node_as_uri(protouri1))
        plugin_list.append(lilv.lilv_node_as_uri(protouri1))

        # XXX TODO Use this eventually for detailed pedalboard port info (return a dict instead of a simple list)
        # TODO get rid of fields not used
        instance = lilv.lilv_uri_to_path(lilv.lilv_node_as_string(block.me)).replace(bundlepath,"",1)
        uri      = lilv.lilv_node_as_uri(proto)
        enabled  = lilv.lilv_world_get(world.me, block.me, ns_ingen.enabled.me, None)
        nodes    = lilv.lilv_world_find_nodes(world.me, block.me, ns_lv2core.port.me, None)   # nodes > ports
        if nodes is not None:
            # These are the port nodes used to define parameter controls
            nodes_it = lilv.lilv_nodes_begin(nodes)
            while not lilv.lilv_nodes_is_end(nodes, nodes_it):
                port        = lilv.lilv_nodes_get(nodes, nodes_it)
                nodes_it    = lilv.lilv_nodes_next(nodes, nodes_it)
                param_value = lilv.lilv_world_get(world.me, port, ns_ingen.value.me, None)
                binding     = lilv.lilv_world_get(world.me, port, ns_midi.binding.me, None)
                #if binding is not None:
                # Only interested in ports which have controller bindings
                controller_num = lilv.lilv_world_get(world.me, binding, ns_midi.controllerNumber.me, None)
                if controller_num is not None:
                    cnum = lilv.lilv_node_as_int(controller_num)
                    path = lilv.lilv_node_as_string(port)
    return plugin_list
