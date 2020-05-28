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


def renormalize(n, left_min, left_max, right_min, right_max):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    delta1 = left_max - left_min
    delta2 = right_max - right_min
    return round((delta2 * (n - left_min) / delta1) + right_min)


def renormalize_float(value, left_min, left_max, right_min, right_max):
    # this remaps a value from original (left) range to new (right) range
    # Figure out how 'wide' each range is
    left_span = abs(left_max - left_min)
    num_divisions = left_span / value

    right_span = abs(right_max - right_min)

    return round(right_span / num_divisions, 2)


def format_float(value):
    if value < 10:
        if value < 1:
            return "%.2f" % value
        else:
            return "%.1f" % value
    else:
        return "%d" % value
