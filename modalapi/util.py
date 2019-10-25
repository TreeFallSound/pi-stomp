#!/usr/bin/env python

def LILV_FOREACH(collection, func):
    itr = collection.begin()
    while itr:
        yield func(collection.get(itr))
        itr = collection.next(itr)

def DICT_GET(dict, key):
    if key in dict:
        return dict[key]
    else:
        return None