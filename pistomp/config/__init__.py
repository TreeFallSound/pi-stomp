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

"""Config loading: the file format, the adapter, and the model.

Import the model types from `pistomp.config.model`. This module holds the
entry points that read a file.
"""

from pathlib import Path

from pistomp.config.adapt_v1 import adapt
from pistomp.config.model import PedalboardConfig
from pistomp.config.schema_v1 import (
    ConfigDocument,
    ConfigError,
    hardware_version,
    json_schema,
    load_cfg_from_file,
    load_default_cfg,
    merge,
    parse,
    read_bundle_config,
)

__all__ = [
    "ConfigDocument",
    "ConfigError",
    "hardware_version",
    "json_schema",
    "load_cfg_from_file",
    "load_default_cfg",
    "parse",
    "resolve",
]


def resolve(default: ConfigDocument, bundle: str | Path | None = None) -> PedalboardConfig:
    """The configuration in effect for one pedalboard bundle."""
    return adapt(merge(default, read_bundle_config(bundle)))
