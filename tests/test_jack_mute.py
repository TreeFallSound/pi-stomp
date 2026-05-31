"""Unit tests for JackMute — jack_lsp/jack_connect/jack_disconnect orchestration."""

import subprocess
from unittest.mock import patch, call

import pytest

from modalapi.jack_mute import JackMute, _PAIRS


@pytest.fixture
def jm() -> JackMute:
    return JackMute()


# ---------- is_muted ----------


def test_is_muted_false_when_link_present(jm):
    out = "mod-monitor:out_1\n   system:playback_1\n   mod-peakmeter:in_3\n"
    with patch("subprocess.check_output", return_value=out) as m:
        assert jm.is_muted() is False
    assert m.call_args.args[0] == ["jack_lsp", "-c", "mod-monitor:out_1"]


def test_is_muted_true_when_link_absent(jm):
    out = "mod-monitor:out_1\n   mod-peakmeter:in_3\n"
    with patch("subprocess.check_output", return_value=out):
        assert jm.is_muted() is True


def test_is_muted_returns_false_when_jack_lsp_missing(jm):
    with patch("subprocess.check_output", side_effect=FileNotFoundError()):
        assert jm.is_muted() is False


def test_is_muted_returns_false_on_subprocess_error(jm):
    err = subprocess.CalledProcessError(1, ["jack_lsp"])
    with patch("subprocess.check_output", side_effect=err):
        assert jm.is_muted() is False


# ---------- mute / unmute ----------


def test_mute_disconnects_each_pair(jm):
    with patch("subprocess.call", return_value=0) as m:
        jm.mute()
    calls = [c.args[0] for c in m.call_args_list]
    expected = [["jack_disconnect", s, d] for s, d in _PAIRS]
    assert calls == expected


def test_unmute_connects_each_pair(jm):
    with patch("subprocess.call", return_value=0) as m:
        jm.unmute()
    calls = [c.args[0] for c in m.call_args_list]
    expected = [["jack_connect", s, d] for s, d in _PAIRS]
    assert calls == expected


def test_mute_swallows_nonzero_exit(jm):
    """jack_disconnect returns nonzero when the pair is already disconnected;
    that should not raise."""
    with patch("subprocess.call", return_value=1):
        jm.mute()  # no exception


def test_mute_swallows_missing_binary(jm):
    with patch("subprocess.call", side_effect=FileNotFoundError()):
        jm.mute()  # no exception


def test_pairs_only_playback_not_peakmeter():
    """Regression: we deliberately don't touch mod-peakmeter so VU meters keep
    bouncing while local audio is silent."""
    flat = {dst for _src, dst in _PAIRS}
    assert "system:playback_1" in flat
    assert "system:playback_2" in flat
    assert not any("peakmeter" in dst for _src, dst in _PAIRS)
