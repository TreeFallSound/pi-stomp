"""Unit tests for EthernetManager — carrier/sysfs/systemctl/ip orchestration.

The background polling thread is suppressed so each test drives state
explicitly via _refresh() or the on-demand readers.
"""

from io import StringIO
from unittest.mock import patch, mock_open, MagicMock

import pytest

from modalapi.ethernet.manager import EthernetManager


@pytest.fixture
def em() -> EthernetManager:
    """An EthernetManager with the polling thread suppressed and state primed off."""
    with patch.object(EthernetManager, "_run", lambda self: None):
        m = EthernetManager()
    yield m
    m.shutdown()


# ---------- _read_carrier ----------

def test_read_carrier_true_when_sysfs_reports_1():
    with patch("builtins.open", mock_open(read_data="1\n")):
        assert EthernetManager._read_carrier() is True


def test_read_carrier_false_when_sysfs_reports_0():
    with patch("builtins.open", mock_open(read_data="0\n")):
        assert EthernetManager._read_carrier() is False


def test_read_carrier_false_when_iface_missing():
    with patch("builtins.open", side_effect=OSError("no such file")):
        assert EthernetManager._read_carrier() is False


# ---------- _read_service_active ----------

def test_read_service_active_true_on_exit_0():
    with patch("subprocess.call", return_value=0):
        assert EthernetManager._read_service_active() is True


def test_read_service_active_false_on_nonzero_exit():
    with patch("subprocess.call", return_value=3):
        assert EthernetManager._read_service_active() is False


def test_read_service_active_false_on_subprocess_error():
    with patch("subprocess.call", side_effect=OSError("boom")):
        assert EthernetManager._read_service_active() is False


# ---------- _refresh + drain_changed ----------

def test_refresh_flips_changed_on_state_transition(em):
    assert em.drain_changed() is False  # baseline
    with patch.object(EthernetManager, "_read_carrier", return_value=True), \
         patch.object(EthernetManager, "_read_service_active", return_value=True):
        em._refresh()
    assert em.carrier_up is True
    assert em.service_active is True
    assert em.drain_changed() is True
    assert em.drain_changed() is False  # drained


def test_refresh_no_change_keeps_flag_clear(em):
    em.carrier_up = True
    em.service_active = False
    with patch.object(EthernetManager, "_read_carrier", return_value=True), \
         patch.object(EthernetManager, "_read_service_active", return_value=False):
        em._refresh()
    assert em.drain_changed() is False


def test_refresh_skips_systemctl_when_carrier_down(em):
    """Optimization: if no cable, don't bother shelling out to systemctl."""
    with patch.object(EthernetManager, "_read_carrier", return_value=False), \
         patch.object(EthernetManager, "_read_service_active") as mock_active:
        em._refresh()
    mock_active.assert_not_called()
    assert em.service_active is False


# ---------- read_ipv4 ----------

def test_read_ipv4_parses_inet_line(em):
    out = b"2: end0    inet 169.254.125.193/16 brd 169.254.255.255 scope link end0\\       valid_lft forever\n"
    with patch("subprocess.check_output", return_value=out):
        assert em.read_ipv4() == "169.254.125.193/16"


def test_read_ipv4_returns_none_when_no_address(em):
    with patch("subprocess.check_output", return_value=b""):
        assert em.read_ipv4() is None


def test_read_ipv4_returns_none_on_command_error(em):
    with patch("subprocess.check_output", side_effect=OSError("boom")):
        assert em.read_ipv4() is None


# ---------- read_jack_settings ----------

def test_read_jack_settings_parses_both(em):
    def fake_co(cmd, **kw):
        return {"jack_samplerate": b"48000\n", "jack_bufsize": b"128\n"}[cmd[0]]
    with patch("subprocess.check_output", side_effect=fake_co):
        assert em.read_jack_settings() == (48000, 128)


def test_read_jack_settings_returns_nones_when_jack_down(em):
    with patch("subprocess.check_output", side_effect=FileNotFoundError()):
        assert em.read_jack_settings() == (None, None)


def test_read_jack_settings_handles_empty_output(em):
    with patch("subprocess.check_output", return_value=b""):
        assert em.read_jack_settings() == (None, None)


# ---------- read_xrun_buckets ----------

def test_read_xrun_buckets_zero_when_file_missing():
    with patch("builtins.open", side_effect=OSError):
        assert EthernetManager.read_xrun_buckets() == (0, 0, 0)


def test_read_xrun_buckets_bins_by_age():
    # now=1000; entries at 30s ago (in all 3), 200s ago (in 5m/15m), 600s ago (in 15m only),
    # 1200s ago (in none), plus a garbage line.
    data = "970.0\n800.0\n400.0\n-200.0\ngarbage\n"
    with patch("builtins.open", mock_open(read_data=data)), \
         patch("time.time", return_value=1000.0):
        b1, b5, b15 = EthernetManager.read_xrun_buckets()
    assert (b1, b5, b15) == (1, 2, 3)


# ---------- start_service / stop_service ----------

def test_start_service_invokes_systemctl(em):
    with patch("os.system") as m:
        em.start_service()
    m.assert_called_once_with("sudo systemctl start pi-stomp-jackbridge.service")


def test_stop_service_invokes_systemctl(em):
    with patch("os.system") as m:
        em.stop_service()
    m.assert_called_once_with("sudo systemctl stop pi-stomp-jackbridge.service")
