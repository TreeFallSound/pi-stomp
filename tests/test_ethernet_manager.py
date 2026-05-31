"""Unit tests for EthernetManager — carrier/sysfs/systemctl/ip orchestration.

The background polling thread is suppressed so each test drives state
explicitly via _refresh() or the static _probe_* helpers. All blocking I/O
runs on the poll thread; the public read_* accessors just return cached
values, so they're exercised via _refresh.
"""

from unittest.mock import patch, mock_open

import pytest

from modalapi.ethernet.manager import EthernetManager


@pytest.fixture
def em() -> EthernetManager:
    """An EthernetManager with the polling thread suppressed and state primed off."""
    with patch.object(EthernetManager, "_run", lambda self: None):
        m = EthernetManager()
    yield m
    m.shutdown()


# ---------- _probe_carrier ----------

def test_probe_carrier_true_when_sysfs_reports_1():
    with patch("builtins.open", mock_open(read_data="1\n")):
        assert EthernetManager._probe_carrier() is True


def test_probe_carrier_false_when_sysfs_reports_0():
    with patch("builtins.open", mock_open(read_data="0\n")):
        assert EthernetManager._probe_carrier() is False


def test_probe_carrier_false_when_iface_missing():
    with patch("builtins.open", side_effect=OSError("no such file")):
        assert EthernetManager._probe_carrier() is False


# ---------- _probe_service_active ----------

def test_probe_service_active_true_on_exit_0():
    with patch("subprocess.call", return_value=0):
        assert EthernetManager._probe_service_active() is True


def test_probe_service_active_false_on_nonzero_exit():
    with patch("subprocess.call", return_value=3):
        assert EthernetManager._probe_service_active() is False


def test_probe_service_active_false_on_subprocess_error():
    with patch("subprocess.call", side_effect=OSError("boom")):
        assert EthernetManager._probe_service_active() is False


# ---------- _refresh + drain_changed ----------

def test_refresh_flips_changed_on_state_transition(em):
    assert em.drain_changed() is False  # baseline
    with patch.object(EthernetManager, "_probe_carrier", return_value=True), \
         patch.object(EthernetManager, "_probe_service_active", return_value=True), \
         patch.object(EthernetManager, "_probe_ipv4", return_value="10.0.0.5/24"), \
         patch.object(EthernetManager, "_probe_jack_int", return_value=48000), \
         patch.object(EthernetManager, "_probe_xrun_buckets", return_value=(0, 0, 0)):
        em._refresh()
    assert em.carrier_up is True
    assert em.service_active is True
    assert em.drain_changed() is True
    assert em.drain_changed() is False  # drained


def test_refresh_no_change_keeps_flag_clear(em):
    em.carrier_up = True
    em.service_active = False
    with patch.object(EthernetManager, "_probe_carrier", return_value=True), \
         patch.object(EthernetManager, "_probe_service_active", return_value=False), \
         patch.object(EthernetManager, "_probe_ipv4", return_value=None):
        em._refresh()
    assert em.drain_changed() is False


def test_refresh_skips_systemctl_and_jack_when_carrier_down(em):
    """Optimization: if no cable, don't bother shelling out to systemctl/ip/jack."""
    with patch.object(EthernetManager, "_probe_carrier", return_value=False), \
         patch.object(EthernetManager, "_probe_service_active") as mock_active, \
         patch.object(EthernetManager, "_probe_ipv4") as mock_ipv4, \
         patch.object(EthernetManager, "_probe_jack_int") as mock_jack, \
         patch.object(EthernetManager, "_probe_xrun_buckets") as mock_xrun:
        em._refresh()
    mock_active.assert_not_called()
    mock_ipv4.assert_not_called()
    mock_jack.assert_not_called()
    mock_xrun.assert_not_called()
    assert em.service_active is False
    assert em.read_ipv4() is None
    assert em.read_jack_settings() == (None, None)


def test_refresh_caches_values_for_ui_thread(em):
    """The public read_* accessors return whatever the last _refresh stored — no I/O."""
    with patch.object(EthernetManager, "_probe_carrier", return_value=True), \
         patch.object(EthernetManager, "_probe_service_active", return_value=True), \
         patch.object(EthernetManager, "_probe_ipv4", return_value="169.254.1.2/16"), \
         patch.object(EthernetManager, "_probe_jack_int", side_effect=[48000, 128]), \
         patch.object(EthernetManager, "_probe_xrun_buckets", return_value=(1, 2, 3)):
        em._refresh()
    assert em.read_ipv4() == "169.254.1.2/16"
    assert em.read_jack_settings() == (48000, 128)
    assert em.read_xrun_buckets() == (1, 2, 3)


# ---------- _probe_ipv4 ----------

def test_probe_ipv4_parses_inet_line():
    out = b"2: end0    inet 169.254.125.193/16 brd 169.254.255.255 scope link end0\\       valid_lft forever\n"
    with patch("subprocess.check_output", return_value=out):
        assert EthernetManager._probe_ipv4() == "169.254.125.193/16"


def test_probe_ipv4_returns_none_when_no_address():
    with patch("subprocess.check_output", return_value=b""):
        assert EthernetManager._probe_ipv4() is None


def test_probe_ipv4_returns_none_on_command_error():
    with patch("subprocess.check_output", side_effect=OSError("boom")):
        assert EthernetManager._probe_ipv4() is None


# ---------- _probe_jack_int ----------

def test_probe_jack_int_parses_value():
    with patch("subprocess.check_output", return_value=b"48000\n"):
        assert EthernetManager._probe_jack_int("jack_samplerate") == 48000


def test_probe_jack_int_returns_none_when_jack_down():
    with patch("subprocess.check_output", side_effect=FileNotFoundError()):
        assert EthernetManager._probe_jack_int("jack_samplerate") is None


def test_probe_jack_int_handles_empty_output():
    with patch("subprocess.check_output", return_value=b""):
        assert EthernetManager._probe_jack_int("jack_samplerate") is None


# ---------- _probe_xrun_buckets ----------

def test_probe_xrun_buckets_zero_when_file_missing():
    with patch("builtins.open", side_effect=OSError):
        assert EthernetManager._probe_xrun_buckets() == (0, 0, 0)


def test_probe_xrun_buckets_bins_by_age():
    # File format: "<epoch_sec_of_minute> <count>" per line, bucket end at ts+60.
    # now=1000; buckets centered so their END (ts+60) gives dt = now-(ts+60):
    #   ts=910, count=2  -> dt=30   -> 1m,5m,15m
    #   ts=740, count=3  -> dt=200  -> 5m,15m
    #   ts=340, count=5  -> dt=600  -> 15m
    #   ts=-260, count=7 -> dt=1200 -> none
    #   garbage and a malformed 1-field line are skipped.
    data = "910 2\n740 3\n340 5\n-260 7\ngarbage\n970\n"
    with patch("builtins.open", mock_open(read_data=data)), \
         patch("time.time", return_value=1000.0):
        b1, b5, b15 = EthernetManager._probe_xrun_buckets()
    assert (b1, b5, b15) == (2, 5, 10)


# ---------- start_service / stop_service ----------

def test_start_service_spawns_systemctl_non_blocking(em):
    with patch("subprocess.Popen") as m:
        em.start_service()
    m.assert_called_once()
    args, _ = m.call_args
    assert args[0] == ["sudo", "systemctl", "start", "pi-stomp-jackbridge.service"]


def test_stop_service_spawns_systemctl_non_blocking(em):
    with patch("subprocess.Popen") as m:
        em.stop_service()
    m.assert_called_once()
    args, _ = m.call_args
    assert args[0] == ["sudo", "systemctl", "stop", "pi-stomp-jackbridge.service"]
