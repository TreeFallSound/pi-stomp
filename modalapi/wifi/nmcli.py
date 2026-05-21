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

import subprocess
from typing import Literal, Optional, cast

TerseField = Literal[
    "GENERAL.STATE",
    "GENERAL.CONNECTION",
    "IP4.ADDRESS",
    "NAME",
    "UUID",
    "TYPE",
    "TIMESTAMP",
    "802-11-wireless.ssid",
    "802-11-wireless.mode",
    "802-11-wireless-security.psk",
    "IN-USE",
    "SSID",
    "SIGNAL",
    "SECURITY",
]


def split_terse(line: str) -> list[str]:
    """Split an nmcli `-t` line, unescaping `\\:` and `\\\\`."""
    fields: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == "\\" and i + 1 < len(line):
            buf.append(line[i + 1])
            i += 2
            continue
        if ch == ":":
            fields.append("".join(buf))
            buf.clear()
            i += 1
            continue
        buf.append(ch)
        i += 1
    fields.append("".join(buf))
    return fields


def parse_kv_lines(stdout: str) -> dict[TerseField, str]:
    """Parse nmcli `-t` key:value output; empty and `--` values are dropped."""
    out: dict[TerseField, str] = {}
    for line in stdout.split("\n"):
        if not line:
            continue
        parts = split_terse(line)
        if len(parts) < 2:
            continue
        key, value = parts[0], parts[1]
        if not value or value == "--":
            continue
        out[cast(TerseField, key)] = value
    return out


def nmcli(
    args: list[str],
    *,
    sudo: bool = False,
    timeout: float = 20.0,
    terse_fields: Optional[list[TerseField]] = None,
    show_secrets: bool = False,
) -> tuple[Optional[str], Optional[bytes]]:
    """Run nmcli; returns `(stdout, None)` on success or `(None, error_bytes)` on any failure."""
    cmd: list[str] = ["sudo"] if sudo else []
    cmd.append("nmcli")
    if show_secrets:
        cmd.append("-s")
    if terse_fields is not None:
        cmd += ["-t", "-f", ",".join(terse_fields)]
    cmd += args
    try:
        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return None, b"timed out"
    except Exception as e:
        return None, str(e).encode("utf-8", errors="replace")
    if result.returncode != 0:
        stderr = (result.stderr or "").strip() or "exit %d" % result.returncode
        return None, stderr.encode("utf-8", errors="replace")
    return result.stdout, None
