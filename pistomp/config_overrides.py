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

from pathlib import Path
from typing import Any

import yaml

# Sentinels for set_field's value argument.
# UNSET: remove the key from the override (revert to default).
# NULL:  write null explicitly (suppress the default).


class _Sentinel:
    def __init__(self, name: str) -> None:
        self._name = name

    def __repr__(self) -> str:
        return self._name


UNSET = _Sentinel("UNSET")
NULL = _Sentinel("NULL")

_LIST_KEY: dict[str, str] = {
    "footswitch": "footswitches",
    "encoder": "encoders",
}


def load_override(bundle_path: Path) -> dict | None:
    f = bundle_path / "config.yml"
    if not f.exists():
        return None
    with open(f) as fp:
        return yaml.safe_load(fp) or {}


def write_override(bundle_path: Path, doc: dict | None) -> None:
    """Atomic write. Deletes the file instead of writing an empty one."""
    f = bundle_path / "config.yml"
    if not _has_overrides(doc):
        if f.exists():
            f.unlink()
        return
    tmp = f.with_suffix(".yml.tmp")
    with open(tmp, "w") as fp:
        yaml.dump(doc, fp, default_flow_style=False, allow_unicode=True)
    tmp.replace(f)


def _has_overrides(doc: dict | None) -> bool:
    if not doc:
        return False
    hw = doc.get("hardware")
    if not hw:
        return False
    return any(hw.get(key) for key in _LIST_KEY.values())


def _find_entry(entries: list, index: int) -> dict | None:
    for e in entries:
        if e.get("id") == index:
            return e
    return None


def set_field(doc: dict, target: str, index: int, field: str, value: Any) -> None:
    """Mutate doc in place. value may be a real value, UNSET, or NULL."""
    hw = doc.setdefault("hardware", {})
    list_key = _LIST_KEY[target]
    entries = hw.setdefault(list_key, [])
    entry = _find_entry(entries, index)
    if entry is None:
        entry: dict[str, Any] = {"id": index}
        entries.append(entry)

    if value is UNSET:
        entry.pop(field, None)
        if set(entry.keys()) <= {"id"}:
            entries.remove(entry)
        if not entries:
            del hw[list_key]
        if not {k: v for k, v in hw.items() if v}:
            doc.pop("hardware", None)
    elif value is NULL:
        entry[field] = None
    else:
        entry[field] = value


def get_effective(
    default_cfg: dict, override_doc: dict | None, target: str, index: int, field: str
) -> Any:
    """Return the value the running pedalboard would see for target[index].field."""
    list_key = _LIST_KEY[target]
    if override_doc:
        hw_o = override_doc.get("hardware", {})
        entry = _find_entry(hw_o.get(list_key, []), index)
        if entry is not None and field in entry:
            return entry[field]
    hw_d = default_cfg.get("hardware", {})
    entry = _find_entry(hw_d.get(list_key, []), index)
    if entry is not None:
        return entry.get(field)
    return None
