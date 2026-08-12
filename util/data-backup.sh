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

default_src_dir="/home/pistomp/data"

# Check if an argument is passed
if [ -z "$1" ]; then
  echo "Usage: $0 <backup_file> [<source_directory>]"
  exit 1
fi

# Check the source dir
if [ -z "$2" ]; then
  src_dir=$default_src_dir
else
  src_dir=$2
fi
if [ ! -d "$src_dir" ]; then
  echo "Source directory does not exist: $src_dir"
  exit 2
fi

# Check if the destination parent directory exists
dest_dir=$(dirname "$1")
if [ ! -d "$dest_dir" ]; then
  echo "Parent directory does not exist: $dest_dir"
  exit 2
fi

# zip updates an existing archive in place, so deleted files would linger forever.
tmp="$1.tmp"
trap 'rm -f "$tmp"' EXIT INT TERM

echo "Backup of: $src_dir"
pushd "$src_dir" > /dev/null || exit 2
# -1 over the default -6: 18s vs 26s, for 6MB on a 344MB archive.
zip -r -1 "$tmp" . -x ".lv2/*"
rc=$?
popd > /dev/null

if [ $rc -ne 0 ]; then
  exit $rc
fi

mv -f "$tmp" "$1" || exit 2
trap - EXIT

exit 0
