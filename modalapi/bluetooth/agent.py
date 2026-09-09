# This file is part of pi-stomp.
#
# pi-stomp is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pi-stomp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pi-stomp.  If not, see <https://www.gnu.org/licenses/>.

"""org.bluez.Agent1, NoInputNoOutput.

With no agent registered anywhere on the image, headless pairing cannot
complete at all — bluez has nobody to ask. NoInputNoOutput selects Just Works,
so every request auto-accepts and the user never sees a passkey prompt. Safe
here only because we are central-only and never discoverable: nothing can
solicit a pairing we did not initiate."""

import logging

from dbus_fast import DBusError
from dbus_fast.annotations import DBusObjectPath, DBusStr, DBusUInt16, DBusUInt32
from dbus_fast.service import ServiceInterface, dbus_method

from .types import AGENT_IFACE

_REJECTED = "org.bluez.Error.Rejected"


class PairingAgent(ServiceInterface):
    def __init__(self) -> None:
        super().__init__(AGENT_IFACE)

    @dbus_method()
    def Release(self) -> None:  # noqa: N802 — D-Bus method names are CamelCase
        logging.debug("BT agent released")

    @dbus_method()
    def RequestAuthorization(self, device: DBusObjectPath) -> None:  # noqa: N802
        logging.debug("BT agent authorizing %s", device)

    @dbus_method()
    def AuthorizeService(self, device: DBusObjectPath, uuid: DBusStr) -> None:  # noqa: N802
        logging.debug("BT agent authorizing service %s on %s", uuid, device)

    @dbus_method()
    def RequestConfirmation(self, device: DBusObjectPath, passkey: DBusUInt32) -> None:  # noqa: N802
        logging.debug("BT agent confirming passkey for %s", device)

    @dbus_method()
    def DisplayPasskey(  # noqa: N802
        self, device: DBusObjectPath, passkey: DBusUInt32, entered: DBusUInt16
    ) -> None:
        logging.debug("BT passkey for %s: %s", device, passkey)

    @dbus_method()
    def DisplayPinCode(self, device: DBusObjectPath, pincode: DBusStr) -> None:  # noqa: N802
        logging.debug("BT pin for %s: %s", device, pincode)

    # NoInputNoOutput never negotiates a passkey or PIN. If bluez asks anyway
    # the device wants an input method we do not have — reject rather than guess.
    @dbus_method()
    def RequestPasskey(self, device: DBusObjectPath) -> DBusUInt32:  # noqa: N802
        raise DBusError(_REJECTED, "pi-Stomp has no keypad")

    @dbus_method()
    def RequestPinCode(self, device: DBusObjectPath) -> DBusStr:  # noqa: N802
        raise DBusError(_REJECTED, "pi-Stomp has no keypad")

    @dbus_method()
    def Cancel(self) -> None:  # noqa: N802
        logging.debug("BT agent request cancelled")
