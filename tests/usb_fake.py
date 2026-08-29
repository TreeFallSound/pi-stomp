"""Fake USB drives for backup/restore tests."""

from contextlib import contextmanager
from unittest.mock import patch

from modalapi.usb import UsbDrive


def drive(name: str, *, writable: bool = True, archive: bool = True) -> UsbDrive:
    mount = f"/media/{name}"
    return UsbDrive(
        mount=mount,
        writable=writable,
        archive=f"{mount}/backups/pistomp_backup.zip" if archive else None,
    )


@contextmanager
def backup_dirs_exist():
    """Stop `ensure_backup_dir` from a true mkdir below /media."""
    with patch("modalapi.usb.ensure_backup_dir", side_effect=lambda d: d.backup_dir):
        yield
