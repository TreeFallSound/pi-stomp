#!/usr/bin/env python3

import json
import modalapi.token as Token
import modalapi.util as util


class Parameter:

    def __init__(self, plugin_info, value, binding):
        self.name = util.DICT_GET(plugin_info, Token.SHORTNAME)  # possibly use name if shortName is None
        self.symbol = util.DICT_GET(plugin_info, Token.SYMBOL)
        self.minimum = util.DICT_GET(util.DICT_GET(plugin_info, Token.RANGES), Token.MINIMUM)
        self.maximum = util.DICT_GET(util.DICT_GET(plugin_info, Token.RANGES), Token.MAXIMUM)
        self.value = value
        self.binding = binding

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


