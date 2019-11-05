#!/usr/bin/env python3

import json


class Plugin:

    def __init__(self, instance_id, parameters, info):

        self.instance_id = instance_id
        self.parameters = parameters
        self.bypass_indicator_xy = ((0,0), (0,0))
        self.lcd_xyz = None
        self.controllers = []
        self.has_footswitch = False
        #self.info_dict = info   # TODO could store this but not sure we need to

    def is_bypassed(self):
        param = self.parameters.get(":bypass")
        if param is not None:
            return param.value
        return True

    def toggle_bypass(self):
        param = self.parameters.get(":bypass")
        if param is not None:
            param.value = not param.value
        return param.value  # return the new value

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


