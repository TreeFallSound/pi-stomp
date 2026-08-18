#!/bin/bash

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

default_target_dir="/home/pistomp/data"

# Check if an argument is passed
if [ -z "$1" ]; then
  echo "Usage: $0 <backup_file> [<target_directory>]"
  exit 1
fi

if [ ! -f "$1" ]; then
  echo "Backup file doesn't exist: $1"
  exit 2
fi

# Check the target dir
if [ -z "$2" ]; then
  target_dir=$default_target_dir
else
  target_dir=$2
fi
if [ ! -d "$target_dir" ]; then
  echo "Target directory does not exist: $target_dir"
  exit 2
fi

# Restore
backup=$(realpath "$1")
pushd "$target_dir" > /dev/null || exit 2
unzip -o "$backup"
rc=$?
popd > /dev/null
exit $rc

exit 0