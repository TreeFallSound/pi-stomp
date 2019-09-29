#!/usr/bin/env python

import json
#import modalapi_lilv as pb
import os
import requests as req
import sys


class Mod:
    __single = None

    def __init__(self):
        print("Init mod")
        if Mod.__single:
            raise Mod.__single
        Mod.__single = self

        self.root_uri = "http://localhost:80/"
        # TODO construct pblist, current at each call in case changes made via UI
        # unless performance sucks that way
        self.pedalboard_list = {}
        self.param_list = []
        self.pedalboard_list = []
        self.current_pedalboard_index = 0
        self.current_preset_index = 0

        # TODO should this be here?
        self.load_pedalboards()

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

        self.pedalboard_list = json.loads(resp.text)
        print(self.pedalboard_list)

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
        pedalboard = pedalboard_list[index]
        if pedalboard == None:
            print("Pedalboard with index %d not found" % index)
            # TODO error handling
            return None
        return pedalboard_list[index]['bundle']

    def pedalboard_init(self):
        # Get current pedalboard - TODO refresh when PB changes
        url = self.root_uri + "pedalboard/current"
        resp = req.get(url)
        pedalboard_name = os.path.splitext(os.path.basename(resp.text))[0]
        print("Getting Pedalboard: %s" % pedalboard_name)
        bundle = "/usr/local/modep/.pedalboards/%s.pedalboard" % pedalboard_name
        pedalboard = (next(item for item in self.pedalboard_list if item['bundle'] == bundle))
        self.current_pedalboard_index = self.pedalboard_list.index(pedalboard)
        print("  Index: %d" % self.current_pedalboard_index)

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