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

"""Snapshot file operations for blend mode."""

import json
import logging
import requests as req
from pathlib import Path

from blend.types import (
    BlendSnapshotConfig,
    SnapshotData,
    SnapshotRef,
    SnapshotStateDict,
    SnapshotsJson,
)


class SnapshotManager:
    """Reads, parses, and creates entries in `snapshots.json`."""

    @staticmethod
    def read_snapshots_file(bundle_path: Path) -> SnapshotsJson:
        snapshots_file = bundle_path / "snapshots.json"
        if not snapshots_file.exists():
            raise FileNotFoundError(f"snapshots.json not found: {snapshots_file}")

        try:
            with open(snapshots_file, "r") as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in snapshots.json: {e}")
        logging.debug(f"Read snapshots.json with {len(data.get('snapshots', []))} snapshots")
        return data

    @staticmethod
    def resolve_snapshot_identifier(snapshots_json: SnapshotsJson, identifier: SnapshotRef) -> int:
        """Resolve a snapshot reference (index or name) to its index."""
        snapshots = snapshots_json.get("snapshots", [])

        if isinstance(identifier, int):
            if not 0 <= identifier < len(snapshots):
                raise ValueError(f"Snapshot index {identifier} out of range (0-{len(snapshots) - 1})")
            return identifier

        target = identifier.lower()
        for i, snapshot in enumerate(snapshots):
            if snapshot.get("name", "").lower() == target:
                logging.debug(f"Resolved snapshot '{identifier}' to index {i}")
                return i

        available = [f"{i}: {s.get('name', '')}" for i, s in enumerate(snapshots)]
        raise ValueError(f"No snapshot found matching '{identifier}'. Available: {', '.join(available)}")

    @staticmethod
    def parse_snapshot_data(snapshots_json: SnapshotsJson, snapshot_index: int) -> SnapshotStateDict:
        """Extract `{instance_id: {symbol: value}}` for a snapshot, including ':bypass'."""
        snapshots = snapshots_json.get("snapshots", [])
        if snapshot_index >= len(snapshots):
            raise IndexError(f"Snapshot index {snapshot_index} out of range (max: {len(snapshots) - 1})")

        snapshot_data = snapshots[snapshot_index].get("data", {})
        state: SnapshotStateDict = {}
        for instance_id, plugin_data in snapshot_data.items():
            params = dict(plugin_data.get("ports", {}))
            # :bypass = 1.0 means bypassed, 0.0 means active (see plugin.py:49)
            params[":bypass"] = 1.0 if plugin_data.get("bypassed", False) else 0.0
            state[instance_id] = params

        logging.debug(f"Parsed snapshot {snapshot_index}: {len(state)} plugins")
        return state

    @staticmethod
    def sync_blend_snapshots(
        bundle_path: Path,
        blend_configs: list[BlendSnapshotConfig] | None,
        root_uri: str,
    ) -> dict[str, int]:
        """Ensure each configured blend snapshot exists as an empty entry.

        Each blend snapshot is created with `data: {}` because every parameter
        (including bypass states) is pushed via WebSocket on activation. Keeping
        the on-disk entry empty prevents the stored snapshot from drifting out
        of sync with the stops.

        Returns `{name: index}` for every configured blend snapshot.
        """
        if not blend_configs:
            logging.debug("No blend snapshots to create")
            return {}

        snapshots_file = bundle_path / "snapshots.json"
        snapshots_data = SnapshotManager.read_snapshots_file(bundle_path)
        snapshots = snapshots_data.setdefault("snapshots", [])

        indices: dict[str, int] = {}
        modified = False

        for cfg in blend_configs:
            name = cfg.get("name")
            stops = cfg.get("stops")
            if not name:
                logging.warning("Blend config missing 'name', skipping")
                continue
            if not stops or len(stops) < 2:
                logging.warning(f"Blend snapshot '{name}' needs at least 2 stops, skipping")
                continue

            existing = next(((i, s) for i, s in enumerate(snapshots) if s.get("name") == name), None)

            if existing and not existing[1].get("data"):
                # Already exists and is empty — leave it alone.
                indices[name] = existing[0]
                logging.debug(f"Blend snapshot '{name}' already exists and is empty (index {existing[0]})")
                continue

            if existing:
                logging.info(f"Removing blend snapshot '{name}' with stale data for recreation")
                snapshots.pop(existing[0])

            logging.info(f"Creating empty blend snapshot '{name}'")
            new_entry: SnapshotData = {"name": name, "data": {}}
            snapshots.append(new_entry)
            indices[name] = len(snapshots) - 1
            modified = True

        if modified:
            with open(snapshots_file, "w") as f:
                json.dump(snapshots_data, f, indent=4)
            SnapshotManager._notify_mod_ui(root_uri)
            logging.info(f"Synced {len(indices)} blend snapshots")

        return indices

    @staticmethod
    def _notify_mod_ui(root_uri: str) -> None:
        """Ask MOD-UI to reload its snapshot list."""
        try:
            resp = req.get(root_uri + "snapshot/list")
            if resp.status_code != 200:
                logging.warning(f"Failed to reload snapshots in MOD-UI: status {resp.status_code}")
            else:
                logging.debug("MOD-UI snapshots reloaded")
        except Exception as e:
            logging.warning(f"Failed to notify MOD-UI: {e}")
