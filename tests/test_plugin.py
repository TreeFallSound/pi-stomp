"""Unit tests for modalapi.plugin.Plugin and common.parameter.Parameter."""

from modalapi.plugin import Plugin
from common.parameter import Parameter


def test_plugin_instance_id_normalized_no_slash():
    plugin = Plugin("fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_plugin_instance_id_normalized_strips_leading_slash():
    plugin = Plugin("/fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_plugin_instance_id_strips_multiple_leading_slashes():
    plugin = Plugin("///fuzz", parameters={}, info=None)
    assert plugin.instance_id == "fuzz"


def test_parameter_instance_id_normalized_no_slash():
    param = Parameter({"shortName": "Gain", "symbol": "gain", "ranges": {}}, 0.5, None, "fuzz")
    assert param.instance_id == "fuzz"


def test_parameter_instance_id_strips_leading_slash():
    param = Parameter({"shortName": "Gain", "symbol": "gain", "ranges": {}}, 0.5, None, "/fuzz")
    assert param.instance_id == "fuzz"


def test_parameter_instance_id_none_preserved():
    param = Parameter({"shortName": "Gain", "symbol": "gain", "ranges": {}}, 0.5, None, None)
    assert param.instance_id is None
