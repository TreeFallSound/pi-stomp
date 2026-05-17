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
    SnapshotsJson,
    SnapshotStateDict,
)


class SnapshotManager:
    """Handles reading, parsing, and creating snapshots."""

    @staticmethod
    def read_snapshots_file(bundle_path: Path) -> SnapshotsJson:
        """Read and parse snapshots.json file."""
        snapshots_file = bundle_path / "snapshots.json"

        if not snapshots_file.exists():
            raise FileNotFoundError(f"snapshots.json not found: {snapshots_file}")

        try:
            with open(snapshots_file, "r") as f:
                data = json.load(f)
            logging.debug(f"Read snapshots.json with {len(data.get('snapshots', []))} snapshots")
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in snapshots.json: {e}")

    @staticmethod
    def resolve_snapshot_identifier(snapshots_json: SnapshotsJson, identifier: int | str) -> int:
        """Resolve snapshot identifier (index or name) to index."""
        snapshots = snapshots_json.get("snapshots", [])

        # If integer, validate and return
        if isinstance(identifier, int):
            if identifier < 0 or identifier >= len(snapshots):
                raise ValueError(f"Snapshot index {identifier} out of range (0-{len(snapshots) - 1})")
            return identifier

        # Case-insensitive exact match
        identifier_lower = identifier.lower()

        for i, snapshot in enumerate(snapshots):
            if snapshot.get("name", "").lower() == identifier_lower:
                logging.debug(f"Resolved snapshot '{identifier}' to index {i}")
                return i

        available = [f"{i}: {s.get('name', '')}" for i, s in enumerate(snapshots)]
        raise ValueError(f"No snapshot found matching '{identifier}'. Available: {', '.join(available)}")

    @staticmethod
    def parse_snapshot_data(snapshots_json: SnapshotsJson, snapshot_index: int) -> SnapshotStateDict:
        """Parse snapshot data and extract parameter values for all plugins in a snapshot."""
        snapshots = snapshots_json.get("snapshots", [])

        if snapshot_index >= len(snapshots):
            raise IndexError(f"Snapshot index {snapshot_index} out of range (max: {len(snapshots) - 1})")

        snapshot = snapshots[snapshot_index]
        snapshot_data = snapshot.get("data", {})
        state = {}

        # Iterate through plugins in snapshot
        for plugin_symbol, plugin_data in snapshot_data.items():
            instance_id = plugin_symbol

            # Extract parameter values from ports
            ports = plugin_data.get("ports", {})
            bypassed = plugin_data.get("bypassed", False)

            params = {}
            for param_symbol, value in ports.items():
                params[param_symbol] = value

            # Add bypass state as :bypass parameter
            # :bypass = 1.0 means bypassed, 0.0 means active (see plugin.py:49)
            params[":bypass"] = 1.0 if bypassed else 0.0

            state[instance_id] = params

        logging.debug(f"Parsed snapshot {snapshot_index}: {len(state)} plugins")
        return state

    @staticmethod
    def sync_blend_snapshots(
        bundle_path: Path, blend_configs: list[BlendSnapshotConfig] | None, root_uri: str
    ) -> dict[str, int]:
        """
        Sync blend snapshots with current configuration.

        Creates/recreates all blend snapshots defined in config. Each blend snapshot
        contains ONLY parameters that differ between stops, preventing conflicts with
        user edits to non-interpolated parameters.

        Args:
            bundle_path: Path to pedalboard bundle directory
            blend_configs: List of blend snapshot configs, or None/empty if no blend mode
            root_uri: MOD-UI root URI for snapshot reload notifications

        Returns:
            Dict mapping snapshot names to indices: {name: index}

        Raises:
            FileNotFoundError: If snapshots.json doesn't exist
            ValueError: If config is invalid
        """
        snapshots_file = bundle_path / "snapshots.json"
        snapshots_data = SnapshotManager.read_snapshots_file(bundle_path)

        # If no blend configs, nothing to create
        if not blend_configs:
            logging.debug("No blend snapshots to create")
            return {}

        snapshot_indices: dict[str, int] = {}
        snapshots_modified = False

        for blend_cfg in blend_configs:
            snapshot_name = blend_cfg.get("name")
            if not snapshot_name:
                logging.warning("Blend config missing 'name', skipping")
                continue

            # Check if blend snapshot already exists
            existing_idx = None
            existing_snapshot = None
            for i, snapshot in enumerate(snapshots_data.get("snapshots", [])):
                if snapshot.get("name") == snapshot_name:
                    existing_idx = i
                    existing_snapshot = snapshot
                    break

            # Get stops configuration for validation
            stops_config = blend_cfg.get("stops")
            if not stops_config:
                logging.warning(f"Blend snapshot '{snapshot_name}' missing 'stops', skipping")
                continue

            # Validate stops count
            stop_count = len(stops_config)
            if stop_count < 2:
                logging.warning(f"Blend snapshot '{snapshot_name}' needs at least 2 stops, skipping")
                continue

            # Check if existing snapshot is already correct (empty)
            if existing_snapshot is not None:
                if not existing_snapshot.get("data"):
                    # Already exists and is empty - no need to recreate
                    logging.debug(
                        f"Blend snapshot '{snapshot_name}' already exists and is empty (index {existing_idx})"
                    )
                    snapshot_indices[snapshot_name] = existing_idx
                    continue
                else:
                    # Exists but has stale data - remove it
                    logging.info(f"Removing blend snapshot '{snapshot_name}' with stale data for recreation")
                    snapshots_data["snapshots"].pop(existing_idx)
                    snapshots_modified = True

            # Create completely empty blend snapshot
            # All parameters (including bypass states) are sent via WebSocket on activation
            # This prevents the snapshot from getting out of date with stop changes
            logging.info(f"Creating empty blend snapshot '{snapshot_name}'")
            blend_snapshot: SnapshotData = {
                "name": snapshot_name,
                "data": {},  # Completely empty - everything sent via WebSocket
            }

            # Append new snapshot
            snapshots_data["snapshots"].append(blend_snapshot)
            new_idx = len(snapshots_data["snapshots"]) - 1
            snapshot_indices[snapshot_name] = new_idx
            snapshots_modified = True

            logging.debug(f"Created blend snapshot '{snapshot_name}' at index {new_idx}")

        # Write updated snapshots if any changes were made
        if snapshots_modified:
            with open(snapshots_file, "w") as f:
                json.dump(snapshots_data, f, indent=4)

            # Notify MOD-UI
            SnapshotManager._notify_mod_ui(root_uri)
            logging.info(f"Synced {len(snapshot_indices)} blend snapshots")

        return snapshot_indices

    @staticmethod
    def _notify_mod_ui(root_uri: str) -> None:
        """Notify MOD-UI to reload snapshots."""
        try:
            url = root_uri + "snapshot/list"
            resp = req.get(url)
            if resp.status_code != 200:
                logging.warning(f"Failed to reload snapshots in MOD-UI: status {resp.status_code}")
            else:
                logging.debug("MOD-UI snapshots reloaded")
        except Exception as e:
            logging.warning(f"Failed to notify MOD-UI: {e}")
