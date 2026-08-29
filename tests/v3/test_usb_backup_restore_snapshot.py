"""USB backup/restore LCD snapshots — drive-selection menu and outcome dialogs,
with two USB sticks mounted so the selection menu actually appears."""

from unittest.mock import patch

import time

from pistomp.input.event import SwitchEvent, SwitchEventKind
from tests.v3.nav_helpers import nav_click, nav_encoder
from uilib.misc import InputEvent

from modalapi.archive import JobState
from tests.archive_fake import fake_jobs
from tests.types import SystemFixture
from ui.archive_panel import ArchiveProgressPanel

_TWO_DRIVES = ["/media/STAGE_LEFT/backups", "/media/STAGE_RIGHT/backups"]


class _FakeUsage:
    def __init__(self, total: int, free: int = 31_000_000_000):
        self.total = total
        self.free = free


def _setup_main_panel(v3_system: SystemFixture):
    handler = v3_system.handler
    hw = v3_system.hw
    handler.lcd.link_data(handler.pedalboard_list, handler.current, hw.footswitches)
    handler.lcd.draw_main_panel()


def _navigate_to_drive(handler, backup_dir: str):
    """Move the open selection menu's highlight to the item for backup_dir, the way an
    encoder turn would, so the resulting snapshot shows that item selected rather than
    whichever the menu defaults to."""
    menu = handler.lcd.pstack.stack[-1]
    flat = menu.sel_children()
    for widget in flat:
        if getattr(widget, "data", None) and widget.data[2] == backup_dir:
            menu.sel_widget(widget)
            return
    raise AssertionError(f"no menu item for {backup_dir}")


def _tick(handler):
    """Drive one UI poll so the progress panel picks up the job's state."""
    handler.lcd.poll_updates()


def _click_selected(handler):
    """Simulate a real click on the open selection menu's currently-highlighted item,
    driving the same dismiss-then-callback path a physical encoder click would."""
    menu = handler.lcd.pstack.stack[-1]
    menu.sel_ref.input_event(InputEvent.CLICK)


def test_v3_backup_shows_usb_drive_selection_menu(v3_system: SystemFixture, snapshot):
    """user_backup_data() with two sticks mounted lets the user pick one first, labeled with size."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=_TWO_DRIVES),
        patch("shutil.disk_usage", return_value=_FakeUsage(32_000_000_000)),
    ):
        handler.user_backup_data(None)

    snapshot()


def test_v3_backup_completes_after_drive_chosen(v3_system: SystemFixture, snapshot):
    """Choosing a drive from the selection menu runs the backup and shows the result."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=_TWO_DRIVES),
        patch("shutil.disk_usage", return_value=_FakeUsage(32_000_000_000)),
    ):
        handler.user_backup_data(None)
    _navigate_to_drive(handler, _TWO_DRIVES[1])
    snapshot("selection")

    with fake_jobs() as jobs, patch("shutil.disk_usage", return_value=_FakeUsage(58_000_000_000, 57_000_000_000)):
        _click_selected(handler)
        _tick(handler)
        snapshot("in_progress")

        jobs[0].advance(0.62, "user-files/NAM Models/Boost Pedal Pack/FORTIN GRIND.nam")
        _tick(handler)
        snapshot("partway")

        jobs[0].finish(JobState.DONE)
        _tick(handler)
        snapshot("complete")


def test_v3_backup_cancel_leaves_previous_archive(v3_system: SystemFixture, snapshot):
    """Cancel is offered while a backup runs; the panel then reports the old archive is intact."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=[_TWO_DRIVES[0]]),
        patch("shutil.disk_usage", return_value=_FakeUsage(58_000_000_000, 57_000_000_000)),
        fake_jobs() as jobs,
    ):
        handler.user_backup_data(None)
        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None

        jobs[0].advance(0.4, "user-files/NAM Models/DDE - Life Droner (NoCab).nam")
        _tick(handler)
        panel._on_button()
        _tick(handler)

    assert jobs[0].cancelled
    snapshot("cancelled")


def test_v3_backup_failure_shows_error(v3_system: SystemFixture, snapshot):
    """A failed backup surfaces the script's last output line instead of dying silently."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=[_TWO_DRIVES[0]]),
        patch("shutil.disk_usage", return_value=_FakeUsage(58_000_000_000, 57_000_000_000)),
        fake_jobs() as jobs,
    ):
        handler.user_backup_data(None)
        jobs[0].finish(JobState.FAILED, error="zip I/O error: No space left on device")
        _tick(handler)

    snapshot("failed")


def test_v3_restore_shows_usb_drive_selection_menu(v3_system: SystemFixture, snapshot):
    """user_restore_data() with two sticks that both have a backup lets the user pick one first."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=_TWO_DRIVES),
        patch("shutil.disk_usage", return_value=_FakeUsage(32_000_000_000)),
        patch("os.path.exists", return_value=True),
    ):
        handler.user_restore_data(None)

    snapshot()


def test_v3_restore_completes_after_drive_chosen(v3_system: SystemFixture, snapshot):
    """Choosing a drive from the selection menu runs the restore and shows the result."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=_TWO_DRIVES),
        patch("shutil.disk_usage", return_value=_FakeUsage(32_000_000_000)),
        patch("os.path.exists", return_value=True),
    ):
        handler.user_restore_data(None)
    _navigate_to_drive(handler, _TWO_DRIVES[1])
    snapshot("selection")

    with fake_jobs() as jobs, patch("os.system"):
        _click_selected(handler)
        _tick(handler)
        snapshot("in_progress")

        jobs[0].finish(JobState.DONE)
        _tick(handler)
        snapshot("complete")


def test_v3_restore_skips_menu_when_only_one_drive_has_a_backup(v3_system: SystemFixture, snapshot):
    """With two sticks mounted but only one holding a backup, restore proceeds directly — no menu."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=_TWO_DRIVES),
        patch("os.path.exists", side_effect=lambda p: p.startswith(_TWO_DRIVES[1])),
        fake_jobs(),
        patch("os.system"),
    ):
        handler.user_restore_data(None)
        _tick(handler)

    snapshot()


def test_v3_restore_offers_no_way_out_while_running(v3_system: SystemFixture):
    """A running restore is deliberately undismissable — unzip is overwriting data/ in
    place and a half-restored tree cannot be undone, so there is no button to press."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=[_TWO_DRIVES[0]]),
        patch("os.path.exists", return_value=True),
        fake_jobs(),
    ):
        handler.user_restore_data(None)
        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None

        assert panel.sel_ref is None
        assert not panel._btn.visible
        nav_click(handler)

        assert handler.lcd.pstack.find_panel_type(ArchiveProgressPanel) is panel


def test_v3_running_job_swallows_footswitches(v3_system: SystemFixture):
    """The old blocking implementation froze the UI thread, so nothing could act mid-run.
    Now that the job is off-thread the panel must swallow input itself — a footswitch
    reaching the cascade would toggle a bypass (mod-ui writes data/) during the restore."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=[_TWO_DRIVES[0]]),
        patch("os.path.exists", return_value=True),
        fake_jobs() as jobs,
    ):
        handler.user_restore_data(None)
        fs = SwitchEvent(controller=v3_system.hw.footswitches[0], kind=SwitchEventKind.PRESS, timestamp=time.monotonic())
        nav = SwitchEvent(controller=nav_encoder(handler), kind=SwitchEventKind.PRESS, timestamp=time.monotonic())

        assert handler.lcd.handle(fs) is True
        assert handler.lcd.handle(nav) is True

        # Once finished the panel stops hoarding input.
        jobs[0].finish(JobState.DONE)
        _tick(handler)
        assert handler.lcd.handle(fs) is False


def test_v3_restore_button_is_nav_reachable_once_finished(v3_system: SystemFixture):
    """When the job ends the button must be both visible and *selected* — it is the panel's
    only selectable, so if add_sel_widget did not auto-select it the user would be trapped."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=[_TWO_DRIVES[0]]),
        patch("os.path.exists", return_value=True),
        patch.object(handler, "restart_ui_stack") as mock_restart,
        fake_jobs() as jobs,
    ):
        handler.user_restore_data(None)
        panel = handler.lcd.pstack.find_panel_type(ArchiveProgressPanel)
        assert panel is not None

        jobs[0].finish(JobState.DONE)
        _tick(handler)

        assert panel.sel_ref is panel._btn
        nav_click(handler)

    mock_restart.assert_called_once_with()
    assert handler.lcd.pstack.find_panel_type(ArchiveProgressPanel) is None
