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

"""Config loading: file format, adapter, and the model the application reads."""

from pathlib import Path
from pistomp.config.adapt_v1 import adapt
from pistomp.config.model import (
    AnalogBinding,
    ControlType,
    EncoderBinding,
    FootswitchBinding,
    LongpressAction,
    LongpressBoard,
    LongpressMidiCC,
    LongpressPreset,
    PedalboardConfig,
    PresetStep,
)
from pistomp.config.schema_v1 import (
    DEFAULT_CONFIG_FILE,
    ConfigDocument,
    ConfigError,
    data_dir,
    hardware_version,
    json_schema,
    load_cfg_from_file,
    load_default_cfg,
    merge,
    parse,
    read_bundle_config,
)

__all__ = [
    "AnalogBinding",
    "ConfigDocument",
    "ConfigError",
    "ControlType",
    "DEFAULT_CONFIG_FILE",
    "EncoderBinding",
    "FootswitchBinding",
    "LongpressAction",
    "LongpressBoard",
    "LongpressMidiCC",
    "LongpressPreset",
    "PedalboardConfig",
    "PresetStep",
    "data_dir",
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
