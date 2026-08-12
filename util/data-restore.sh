#!/bin/bash

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
unzip -o -u "$backup"
rc=$?
popd > /dev/null
exit $rc

exit 0