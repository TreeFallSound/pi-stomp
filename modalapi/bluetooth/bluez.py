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

"""dbus-fast client for org.bluez, owning an asyncio loop in its own thread.

Device state is accumulated from InterfacesAdded / PropertiesChanged into a
lock-guarded dict, so callers never await anything: they read snapshot() and
issue verbs through call(), which blocks the calling (worker) thread on the
loop. Nothing here touches the panel stack."""

import asyncio
import logging
import threading
from typing import Any, Callable, Coroutine, Optional, TypeVar

from dbus_fast import BusType, DBusError, Message, MessageType, Variant
from dbus_fast.aio import MessageBus

from .agent import PairingAgent
from .types import (
    ADAPTER_IFACE,
    AGENT_MANAGER_IFACE,
    AGENT_PATH,
    BLUEZ_SERVICE,
    BtDevice,
    DEVICE_IFACE,
    device_kind,
    is_interesting,
)

T = TypeVar("T")

_PROPS_IFACE = "org.freedesktop.DBus.Properties"
_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
_BLUEZ_ROOT = "/org/bluez"

_MATCH_RULES = (
    f"type='signal',sender='{BLUEZ_SERVICE}',interface='{_PROPS_IFACE}',member='PropertiesChanged'",
    f"type='signal',sender='{BLUEZ_SERVICE}',interface='{_OM_IFACE}'",
)


def _unwrap(props: dict[str, Any]) -> dict[str, Any]:
    return {k: v.value if isinstance(v, Variant) else v for k, v in props.items()}


class BluezClient:
    """Live view of org.bluez. start() is idempotent-ish and never raises —
    a missing bus, missing bluez, or missing adapter all land as available=False,
    which the UI reads as "this board has no Bluetooth"."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: dict[str, dict[str, Any]] = {}
        self._adapter_props: dict[str, Any] = {}
        self._adapter_path: Optional[str] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._bus: Optional[MessageBus] = None
        self._agent: Optional[PairingAgent] = None
        self._ready = threading.Event()
        self._started = False
        self._on_change: Optional[Callable[[], None]] = None

    # ----- lifecycle -----

    def start(self, on_change: Optional[Callable[[], None]] = None) -> bool:
        """Bring up the loop thread and connect. Blocks until the first
        GetManagedObjects lands (or setup fails). Returns available()."""
        if self._started:
            return self.available
        self._started = True
        self._on_change = on_change
        self._thread = threading.Thread(target=self._run_loop, name="bluez", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=10.0)
        return self.available

    def _run_loop(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._setup())
        except Exception as e:
            logging.info("Bluetooth unavailable: %s", e)
            self._ready.set()
            return
        finally:
            self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _setup(self) -> None:
        bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        self._bus = bus

        agent = PairingAgent()
        self._agent = agent
        bus.export(AGENT_PATH, agent)

        for rule in _MATCH_RULES:
            await bus.call(
                Message(
                    destination="org.freedesktop.DBus",
                    path="/org/freedesktop/DBus",
                    interface="org.freedesktop.DBus",
                    member="AddMatch",
                    signature="s",
                    body=[rule],
                )
            )
        bus.add_message_handler(self._on_signal)

        await self._refresh_objects()
        if self._adapter_path is None:
            raise RuntimeError("no bluetooth adapter")
        await self._register_agent()

    async def _register_agent(self) -> None:
        try:
            await self._raw_call(
                _BLUEZ_ROOT, AGENT_MANAGER_IFACE, "RegisterAgent", "os", [AGENT_PATH, "NoInputNoOutput"]
            )
        except DBusError as e:
            if "AlreadyExists" not in str(e):
                raise
        await self._raw_call(_BLUEZ_ROOT, AGENT_MANAGER_IFACE, "RequestDefaultAgent", "o", [AGENT_PATH])

    async def _refresh_objects(self) -> None:
        body = await self._raw_call("/", _OM_IFACE, "GetManagedObjects")
        objects: dict[str, dict[str, dict[str, Any]]] = body[0]
        with self._lock:
            self._devices.clear()
            for path, ifaces in objects.items():
                if ADAPTER_IFACE in ifaces and self._adapter_path is None:
                    self._adapter_path = path
                    self._adapter_props = _unwrap(ifaces[ADAPTER_IFACE])
                if DEVICE_IFACE in ifaces:
                    self._devices[path] = _unwrap(ifaces[DEVICE_IFACE])

    def stop(self) -> None:
        loop = self._loop
        if loop is None:
            return
        loop.call_soon_threadsafe(loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    # ----- signals -----

    def _on_signal(self, msg: Message) -> Optional[bool]:
        if msg.message_type is not MessageType.SIGNAL:
            return None
        changed = False
        if msg.interface == _OM_IFACE and msg.member == "InterfacesAdded":
            path, ifaces = msg.body[0], msg.body[1]
            if DEVICE_IFACE in ifaces:
                with self._lock:
                    self._devices[path] = _unwrap(ifaces[DEVICE_IFACE])
                changed = True
        elif msg.interface == _OM_IFACE and msg.member == "InterfacesRemoved":
            path, ifaces = msg.body[0], msg.body[1]
            if DEVICE_IFACE in ifaces:
                with self._lock:
                    changed = self._devices.pop(path, None) is not None
        elif msg.interface == _PROPS_IFACE and msg.member == "PropertiesChanged":
            iface, props = msg.body[0], _unwrap(msg.body[1])
            path = msg.path or ""
            with self._lock:
                if iface == DEVICE_IFACE:
                    self._devices.setdefault(path, {}).update(props)
                    changed = True
                elif iface == ADAPTER_IFACE and path == self._adapter_path:
                    self._adapter_props.update(props)
                    changed = True
        if changed and self._on_change is not None:
            try:
                self._on_change()
            except Exception:
                logging.exception("Bluetooth change callback failed")
        return None

    # ----- reads -----

    @property
    def available(self) -> bool:
        return self._adapter_path is not None

    @property
    def powered(self) -> bool:
        with self._lock:
            return bool(self._adapter_props.get("Powered"))

    @property
    def discovering(self) -> bool:
        with self._lock:
            return bool(self._adapter_props.get("Discovering"))

    def snapshot(self) -> list[BtDevice]:
        """Every device bluez currently knows, filtered to MIDI/HID/paired."""
        with self._lock:
            items = list(self._devices.items())
        out: list[BtDevice] = []
        for path, props in items:
            if not is_interesting(props):
                continue
            rssi = props.get("RSSI")
            out.append(
                BtDevice(
                    path=path,
                    address=str(props.get("Address") or ""),
                    name=str(props.get("Name") or ""),
                    kind=device_kind(props),
                    paired=bool(props.get("Paired")),
                    connected=bool(props.get("Connected")),
                    trusted=bool(props.get("Trusted")),
                    rssi=int(rssi) if isinstance(rssi, int) else None,
                )
            )
        return out

    def device_props(self, path: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._devices.get(path) or {})

    def find_path(self, address: str) -> Optional[str]:
        with self._lock:
            for path, props in self._devices.items():
                if str(props.get("Address") or "").upper() == address.upper():
                    return path
        return None

    # ----- calls -----

    def call(self, coro: Coroutine[Any, Any, T], timeout: float = 30.0) -> T:
        """Run a coroutine on the client's loop and block until it returns.
        Called from CommandQueue's worker thread, never the main thread."""
        loop = self._loop
        if loop is None or not loop.is_running():
            raise RuntimeError("bluetooth is not running")
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout)

    async def _raw_call(
        self, path: str, iface: str, member: str, signature: str = "", body: Optional[list] = None
    ) -> list:
        bus = self._bus
        if bus is None:
            raise RuntimeError("bluetooth is not connected")
        reply = await bus.call(
            Message(
                destination=BLUEZ_SERVICE,
                path=path,
                interface=iface,
                member=member,
                signature=signature,
                body=body or [],
            )
        )
        if reply is None:
            return []
        if reply.message_type is MessageType.ERROR:
            raise DBusError(reply.error_name or "org.bluez.Error.Failed", str(reply.body[0] if reply.body else ""))
        return reply.body

    @property
    def adapter_path(self) -> str:
        path = self._adapter_path
        if path is None:
            raise RuntimeError("no bluetooth adapter")
        return path

    async def set_adapter_property(self, name: str, value: Variant) -> None:
        await self._raw_call(self.adapter_path, _PROPS_IFACE, "Set", "ssv", [ADAPTER_IFACE, name, value])

    async def set_device_property(self, path: str, name: str, value: Variant) -> None:
        await self._raw_call(path, _PROPS_IFACE, "Set", "ssv", [DEVICE_IFACE, name, value])

    async def device_call(self, path: str, member: str) -> None:
        await self._raw_call(path, DEVICE_IFACE, member)

    async def adapter_call(self, member: str, signature: str = "", body: Optional[list] = None) -> None:
        await self._raw_call(self.adapter_path, ADAPTER_IFACE, member, signature, body)
