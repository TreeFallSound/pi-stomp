"""Unit tests for the pure connection-parsing logic in modalapi.pedalboard.

The lilv-dependent arc walk is not tested here (lilv is mocked in the test
env); we test the URI/port resolution that the walk feeds into.
"""

from modalapi.connections import (
    Connection,
    Endpoint,
    EndpointKind,
    build_connection,
    classify_endpoint,
    resolve_port_idx,
    split_port_uri,
)


BUNDLE = "/data/pedalboards/Guitar.pedalboard"
CHORUS_INFO = {
    "ports": {
        "audio": {
            "input": [{"symbol": "in"}],
            "output": [{"symbol": "out"}],
        }
    }
}
STEREO_INFO = {
    "ports": {
        "audio": {
            "input": [{"symbol": "inL"}, {"symbol": "inR"}],
            "output": [{"symbol": "outL"}, {"symbol": "outR"}],
        }
    }
}


def test_split_strips_bundle_and_separates_symbol() -> None:
    assert split_port_uri(f"file://{BUNDLE}/ChorusI/out", BUNDLE) == ("ChorusI", "out")


def test_split_hw_port_has_no_symbol() -> None:
    assert split_port_uri(f"file://{BUNDLE}/capture_1", BUNDLE) == ("capture_1", "")


def test_split_handles_missing_scheme() -> None:
    assert split_port_uri(f"{BUNDLE}/stereo/inL", BUNDLE) == ("stereo", "inL")


def test_split_handles_url_encoded_bundle_path() -> None:
    # lilv URL-encodes spaces in file:// URIs. The raw bundlepath stored on
    # the Pedalboard object isn't encoded — split_port_uri must reconcile.
    # Regression: previously this returned ("", "...") for every port,
    # collapsing every connection onto a single node and creating a fake cycle.
    bundle_with_space = "/Users/cam/Documents/MOD Desktop/pedalboards/Doom_Bass.pedalboard"
    encoded = "file:///Users/cam/Documents/MOD%20Desktop/pedalboards/Doom_Bass.pedalboard/HighPassFilter/Out1"
    assert split_port_uri(encoded, bundle_with_space) == ("HighPassFilter", "Out1")


def test_classify() -> None:
    assert classify_endpoint("capture_1") == EndpointKind.SOURCE
    assert classify_endpoint("playback_2") == EndpointKind.SINK
    assert classify_endpoint("ChorusI") == EndpointKind.PLUGIN
    assert classify_endpoint("serial_midi_in") == EndpointKind.HW


def test_resolve_port_idx_hw_uses_suffix() -> None:
    assert resolve_port_idx(EndpointKind.SOURCE, "capture_1", "", False, None) == 0
    assert resolve_port_idx(EndpointKind.SOURCE, "capture_2", "", False, None) == 1
    assert resolve_port_idx(EndpointKind.SINK, "playback_2", "", True, None) == 1


def test_resolve_port_idx_plugin_uses_ttl_order() -> None:
    assert resolve_port_idx(EndpointKind.PLUGIN, "stereo", "inL", True, STEREO_INFO) == 0
    assert resolve_port_idx(EndpointKind.PLUGIN, "stereo", "inR", True, STEREO_INFO) == 1
    assert resolve_port_idx(EndpointKind.PLUGIN, "stereo", "outR", False, STEREO_INFO) == 1


def test_resolve_port_idx_unknown_symbol_defaults_to_zero() -> None:
    assert resolve_port_idx(EndpointKind.PLUGIN, "stereo", "ghost", True, STEREO_INFO) == 0


def test_resolve_port_idx_missing_info_defaults_to_zero() -> None:
    assert resolve_port_idx(EndpointKind.PLUGIN, "stereo", "inL", True, None) == 0


def test_build_connection_capture_to_plugin() -> None:
    conn = build_connection(
        f"file://{BUNDLE}/capture_1",
        f"file://{BUNDLE}/ChorusI/in",
        BUNDLE,
        {"ChorusI": CHORUS_INFO},
    )
    assert conn == Connection(
        src=Endpoint(EndpointKind.SOURCE, "capture_1", "", 0),
        dst=Endpoint(EndpointKind.PLUGIN, "ChorusI", "in", 0),
    )


def test_build_connection_plugin_to_playback_stereo() -> None:
    conn = build_connection(
        f"file://{BUNDLE}/stereo/outR",
        f"file://{BUNDLE}/playback_2",
        BUNDLE,
        {"stereo": STEREO_INFO},
    )
    assert conn.src.kind == EndpointKind.PLUGIN
    assert conn.src.port_idx == 1
    assert conn.dst.kind == EndpointKind.SINK
    assert conn.dst.port_idx == 1


def test_build_connection_unknown_plugin_resolves_to_port_idx_zero() -> None:
    """Resilient when plugin_info isn't available (e.g. missing LV2)."""
    conn = build_connection(
        f"file://{BUNDLE}/unknown/whatever",
        f"file://{BUNDLE}/playback_1",
        BUNDLE,
        {},
    )
    assert conn.src == Endpoint(EndpointKind.PLUGIN, "unknown", "whatever", 0)
    assert conn.dst.port_idx == 0
