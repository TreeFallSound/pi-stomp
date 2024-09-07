#!/bin/bash

# Change dir to pedalboards location
pushd /home/pistomp/data/pb/test3 > /dev/null || { echo "Cannot change to pedalboard dir"; exit 1; }

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
  git stash apply --index --quiet || { echo "git stash apply failed"; exit 1; }

  if [[ $count -eq 0 ]]; then
    echo "Already up to date"
  else
    echo "$count update(s) applied"
  fi
  exit 0
fi