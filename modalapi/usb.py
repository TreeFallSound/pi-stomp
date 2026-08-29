# SPDX-License-Identifier: AGPL-3.0-or-later
#
# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""Mounted USB drives, and what each drive can do.

Backup needs a writable drive. Restore only reads the archive, thus a read-only
drive is a correct restore source. Some MIDI controllers show a read-only
mass-storage volume, which mounts with the true drives.

Ask the kernel each time. Do not cache eligibility.
"""

import os
from dataclasses import dataclass

_MEDIA_ROOT = "/media"
_BACKUP_SUBDIR = "backups"


@dataclass(frozen=True)
class UsbDrive:
    """One mounted USB partition. `archive` is the backup on the drive, if there is one."""

    mount: str
    writable: bool
    archive: str | None

    @property
    def name(self) -> str:
        return os.path.basename(self.mount)

    @property
    def backup_dir(self) -> str:
        return os.path.join(self.mount, _BACKUP_SUBDIR)


def media_mounts() -> list[str]:
    # Only pi-gen-pistomp's pistomp-usb-mount udev script writes to /media, one
    # subdir per USB partition. Thus each mount below /media is a USB drive.
    if not os.path.isdir(_MEDIA_ROOT):
        return []
    return [
        os.path.join(_MEDIA_ROOT, name)
        for name in sorted(os.listdir(_MEDIA_ROOT))
        if os.path.ismount(os.path.join(_MEDIA_ROOT, name))
    ]


def discover(archive_name: str) -> list[UsbDrive]:
    """All mounted drives, with their eligibility. Creates no directories."""
    drives = []
    for mount in media_mounts():
        archive = os.path.join(mount, _BACKUP_SUBDIR, archive_name)
        drives.append(
            UsbDrive(
                mount=mount,
                # access(2) gives EROFS for a read-only mount. Thus this one test
                # covers the mount flags and the permission bits.
                writable=os.access(mount, os.W_OK),
                archive=archive if os.path.exists(archive) else None,
            )
        )
    return drives


def ensure_backup_dir(drive: UsbDrive) -> str:
    """Make the backups dir if it is absent. Raises OSError on a read-only drive."""
    if not os.path.exists(drive.backup_dir):
        os.mkdir(drive.backup_dir)
    return drive.backup_dir
