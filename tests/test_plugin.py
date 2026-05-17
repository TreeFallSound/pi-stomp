"""Unit tests for modalapi.plugin.Plugin."""

from modalapi.plugin import Plugin


def test_plugin_instance_id_normalized_no_slash():
    plugin = Plugin("fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_plugin_instance_id_normalized_strips_leading_slash():
    plugin = Plugin("/fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_plugin_instance_id_strips_multiple_leading_slashes():
    plugin = Plugin("///fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"
