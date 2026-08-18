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

# Change dir to pedalboards location
pushd /home/pistomp/.pedalboards > /dev/null || { echo "Cannot change to pedalboard dir"; exit 1; }

# See if the dir has any user made changes
git diff --quiet

if [[ $? -eq 0 ]]; then
  # Pull remote changes
  git fetch --quiet || { echo "git fetch failed"; exit 1; }
  count=$(git rev-list HEAD..origin/$(git rev-parse --abbrev-ref HEAD) --count)
  git pull --quiet || { echo "git pull failed"; exit 1; }

  if [[ $count -eq 0 ]]; then
    echo "Already up to date"
  else
    echo "$count update(s) applied"
  fi
  exit 0

else
  # Changes already exist, so stash 'em before pulling

  # Stash away local changes
  git stash --quiet || { echo "git stash failed"; exit 1; }

  # Pull remote changes
  git fetch --quiet || { echo "git fetch failed"; exit 1; }
  count=$(git rev-list HEAD..origin/$(git rev-parse --abbrev-ref HEAD) --count)
  git pull --quiet || { echo "git pull failed"; exit 1; }

  # Reapply the local stashed changes, favor stashed version.  XXX possibility of badly merged changes
  if ! git stash apply --index --quiet; then
    echo "git stash apply failed"
    git stash pop --index
    exit 1
  fi

  if [[ $count -eq 0 ]]; then
    echo "Already up to date"
  else
    echo "$count update(s) applied"
  fi
  exit 0
fi