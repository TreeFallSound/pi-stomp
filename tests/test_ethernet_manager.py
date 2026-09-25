"""Unit tests for EthernetManager — carrier/sysfs + jackbridge-pi-status parsing.

The polling thread is suppressed, so each test drives state through
_refresh() or the _probe_* helpers. All blocking I/O is mocked, so this
runs off-device.

The start/stop verbs are gone (the Mac owns the lifecycle), so their
tests went with them. What remains: carrier detection via sysfs, IPv4
parsing via `ip`, jackbridge-pi-status parsing, the "service=active
unlocks the hw_params read" gating, and the read_* accessor contract.
"""

from typing import Generator
from unittest.mock import mock_open, patch

import pytest

from modalapi.ethernet.manager import EthernetManager
from pistomp.alsa_pcm import read_hw_params

# _refresh calls read_hw_params through the manager's namespace.
_HW = "modalapi.ethernet.manager.read_hw_params"


@pytest.fixture
def em() -> Generator[EthernetManager, None, None]:
    """An EthernetManager with the polling thread suppressed and iface pinned to eth0."""
    with (
        patch.object(EthernetManager, "_run", lambda self: None),
        patch("os.listdir", return_value=["eth0", "lo"]),
        patch("os.path.exists", return_value=False),
    ):
        m = EthernetManager()
        assert m.iface == "eth0"  # force cached_property to compute under the mock
    yield m
    m.shutdown()


# ---------- _probe_carrier ----------


def test_probe_carrier_true_when_sysfs_reports_1(em: EthernetManager):
    with patch("builtins.open", mock_open(read_data="1\n")):
        assert em._probe_carrier() is True


def test_probe_carrier_false_when_sysfs_reports_0(em: EthernetManager):
    with patch("builtins.open", mock_open(read_data="0\n")):
        assert em._probe_carrier() is False


def test_probe_carrier_false_when_iface_missing(em: EthernetManager):
    with patch("builtins.open", side_effect=OSError("no such file")):
        assert em._probe_carrier() is False


# ---------- _read_pi_status ----------


def test_read_pi_status_parses_key_value_lines():
    out = (
        "service=active\n"
        "netadapters=1\n"
        "ports_wired=6\n"
        "route=eth0\n"
        "iface=eth0\n"
        "xruns_1m=0\n"
        "xruns_5m=2\n"
        "xruns_15m=5\n"
        "link=resyncing\n"
        "net_restarts=4\n"
        "a line with no equals sign\n"
    )
    with patch("subprocess.check_output", return_value=out):
        s = EthernetManager._read_pi_status()
    assert s["service"] == "active"
    assert s["netadapters"] == "1"
    assert s["ports_wired"] == "6"
    assert s["route"] == "eth0"
    assert s["xruns_15m"] == "5"
    assert s["link"] == "resyncing"
    assert len(s) == 10  # the no-equals line is skipped


def test_read_pi_status_empty_on_missing_helper():
    with patch("subprocess.check_output", side_effect=OSError("not installed")):
        assert EthernetManager._read_pi_status() == {}


# ---------- _refresh + drain_changed ----------


def _pi_status(
    service="active",
    netadapters="1",
    ports_wired="6",
    route="eth0",
    x1="0",
    x5="0",
    x15="0",
    link="up",
    net_restarts="0",
):
    return (
        f"service={service}\n"
        f"netadapters={netadapters}\n"
        f"ports_wired={ports_wired}\n"
        f"route={route}\n"
        f"iface=eth0\n"
        f"xruns_1m={x1}\n"
        f"xruns_5m={x5}\n"
        f"xruns_15m={x15}\n"
        f"link={link}\n"
        f"net_restarts={net_restarts}\n"
    )


def test_refresh_flips_changed_on_state_transition(em: EthernetManager):
    assert em.drain_changed() is False  # baseline
    with (
        patch.object(EthernetManager, "_probe_carrier", return_value=True),
        patch.object(EthernetManager, "_probe_ipv4", return_value="10.0.0.5/24"),
        patch("subprocess.check_output", return_value=_pi_status(service="active")),
        patch(_HW, return_value={"rate": "48000", "period_size": "64"}),
    ):
        em._refresh()
    assert em.carrier_up is True
    assert em.service_active is True
    assert em.drain_changed() is True
    assert em.drain_changed() is False  # drained


def test_refresh_no_change_keeps_flag_clear(em: EthernetManager):
    em.carrier_up = True
    em.service_active = True
    with (
        patch.object(EthernetManager, "_probe_carrier", return_value=True),
        patch.object(EthernetManager, "_probe_ipv4", return_value="10.0.0.5/24"),
        patch("subprocess.check_output", return_value=_pi_status(service="active")),
        patch(_HW, return_value={"rate": "48000", "period_size": "64"}),
    ):
        em._refresh()
    assert em.drain_changed() is False


def test_refresh_skips_status_and_jack_when_carrier_down(em: EthernetManager):
    """Optimisation: with no cable, skip jackbridge-pi-status, ip, and jack."""
    with (
        patch.object(EthernetManager, "_probe_carrier", return_value=False),
        patch("subprocess.check_output") as m_co,
        patch(_HW) as m_hw,
    ):
        em._refresh()
    m_co.assert_not_called()
    m_hw.assert_not_called()
    assert em.read_jack_settings() == (None, None)


def test_refresh_caches_values_for_ui_thread(em):
    """The read_* accessors return what the last _refresh stored, with no I/O."""
    with (
        patch.object(EthernetManager, "_probe_carrier", return_value=True),
        patch.object(EthernetManager, "_probe_ipv4", return_value="10.0.0.5/24"),
        patch(
            "subprocess.check_output",
            return_value=_pi_status(
                service="active",
                netadapters="2",
                ports_wired="4",
                route="eth0",
                x1="1",
                x5="2",
                x15="3",
            ),
        ),
        patch(_HW, return_value={"rate": "48000", "period_size": "64"}),
    ):
        em._refresh()
    assert em.read_ipv4() == "10.0.0.5/24"
    assert em.read_jack_settings() == (48000, 64)
    assert em.read_xrun_buckets() == (1, 2, 3)
    assert em.read_netadapter_health() == (2, 4, "eth0")
    assert em.read_link_health() == (False, 0)


def test_refresh_flips_changed_when_link_starts_resyncing(em: EthernetManager):
    """netadapter restarts leave the graph, the ports and the xrun rate
    healthy, so a link flip is its own state change or the screen keeps
    the readout it had."""
    em.carrier_up = True
    em.service_active = True
    with (
        patch.object(EthernetManager, "_probe_carrier", return_value=True),
        patch.object(EthernetManager, "_probe_ipv4", return_value="10.0.0.5/24"),
        patch("subprocess.check_output", return_value=_pi_status(link="resyncing", net_restarts="4")),
        patch(_HW, return_value={"rate": "48000", "period_size": "64"}),
    ):
        em._refresh()
    assert em.read_link_health() == (True, 4)
    assert em.drain_changed() is True


def test_refresh_link_unknown_reads_as_not_resyncing(em: EthernetManager):
    """`link=unknown` means the watcher has written nothing yet. That is not
    evidence of a fault."""
    with (
        patch.object(EthernetManager, "_probe_carrier", return_value=True),
        patch.object(EthernetManager, "_probe_ipv4", return_value="10.0.0.5/24"),
        patch("subprocess.check_output", return_value=_pi_status(link="unknown")),
        patch(_HW, return_value={"rate": "48000", "period_size": "64"}),
    ):
        em._refresh()
    assert em.read_link_health() == (False, 0)


# ---------- _probe_ipv4 ----------


def test_probe_ipv4_parses_inet_line(em: EthernetManager):
    out = b"2: end0    inet 169.254.125.193/16 brd 169.254.255.255 scope link end0\\       valid_lft forever\n"
    with patch("subprocess.check_output", return_value=out):
        assert em._probe_ipv4() == "169.254.125.193/16"


def test_probe_ipv4_returns_none_when_no_address(em: EthernetManager):
    with patch("subprocess.check_output", return_value=b""):
        assert em._probe_ipv4() is None


def test_probe_ipv4_returns_none_on_command_error(em: EthernetManager):
    with patch("subprocess.check_output", side_effect=OSError("boom")):
        assert em._probe_ipv4() is None


# ---------- read_hw_params ----------

_HW_PARAMS = (
    "access: MMAP_INTERLEAVED\n"
    "format: S32_LE\n"
    "subformat: STD\n"
    "channels: 2\n"
    "rate: 48000 (48000/1)\n"
    "period_size: 128\n"
    "buffer_size: 512\n"
)


def test_read_hw_params_takes_first_token_of_each_value():
    with patch("builtins.open", mock_open(read_data=_HW_PARAMS)):
        params = read_hw_params()
    assert params["rate"] == "48000"
    assert params["period_size"] == "128"
    assert params["channels"] == "2"


def test_read_hw_params_empty_when_pcm_closed():
    with patch("builtins.open", mock_open(read_data="closed\n")):
        assert read_hw_params() == {}


def test_read_hw_params_empty_off_device():
    with patch("builtins.open", side_effect=FileNotFoundError()):
        assert read_hw_params() == {}
