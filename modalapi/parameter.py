#!/usr/bin/env python3

import json
import modalapi.util as util


class Parameter:

    def __init__(self, plugin_info, value, binding):
        self.name = util.DICT_GET(plugin_info, 'shortName')  # possibly use name if shortName is None
        self.symbol = util.DICT_GET(plugin_info, 'symbol')
        self.minimum = util.DICT_GET(util.DICT_GET(plugin_info, 'ranges'), 'minimum')
        self.maximum = util.DICT_GET(util.DICT_GET(plugin_info, 'ranges'), 'maximum')
        self.value = value
        self.binding = binding

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


