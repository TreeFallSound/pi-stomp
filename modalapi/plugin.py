#!/usr/bin/env python3

import json


class Plugin:

    def __init__(self, instance_id, parameters, info):

        self.instance_id = instance_id
        self.parameters = parameters
        #self.info_dict = info   # TODO could store this but not sure we need to

    def to_json(self):
        return json.dumps(self, default=lambda o: o.__dict__, sort_keys=True, indent=4)


