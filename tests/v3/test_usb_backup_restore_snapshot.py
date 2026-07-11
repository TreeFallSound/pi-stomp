"""USB backup/restore LCD snapshots — drive-selection menu and outcome dialogs,
with two USB sticks mounted so the selection menu actually appears."""

from unittest.mock import patch

from uilib.misc import InputEvent

from tests.types import SystemFixture

_TWO_DRIVES = ["/media/STAGE_LEFT/backups", "/media/STAGE_RIGHT/backups"]


class _FakeUsage:
    def __init__(self, total: int):
        self.total = total


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

    with patch("subprocess.check_output", return_value=b""):
        _click_selected(handler)

    snapshot("complete")


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

    with patch("subprocess.check_output", return_value=b""), patch("os.system"):
        _click_selected(handler)

    snapshot("complete")


def test_v3_restore_skips_menu_when_only_one_drive_has_a_backup(v3_system: SystemFixture, snapshot):
    """With two sticks mounted but only one holding a backup, restore proceeds directly — no menu."""
    handler = v3_system.handler
    _setup_main_panel(v3_system)

    with (
        patch.object(handler, "check_usb", return_value=_TWO_DRIVES),
        patch("os.path.exists", side_effect=lambda p: p.startswith(_TWO_DRIVES[1])),
        patch("subprocess.check_output", return_value=b""),
        patch("os.system"),
    ):
        handler.user_restore_data(None)

    snapshot()
