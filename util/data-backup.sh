#!/bin/bash

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
if [ -d "$dest_dir" ]; then
  echo "Backup of: $src_dir"
  pushd $src_dir
  sudo zip -rq $1 . -x ".lv2/*"
  popd
else
  echo "Parent directory does not exist: $parent_dir"
  exit 2
fi

exit 0