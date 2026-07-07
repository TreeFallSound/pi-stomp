#!/bin/bash
# expand-git.sh — turn a packaged pi-stomp install into a real git repo.
#
# The .deb ships no .git directory, just .git-meta/ (origin URL, branch,
# and the exact commit that was packaged). This script initializes a repo,
# fetches full history + tags from that origin, and points the branch at
# the recorded built-sha — the commit whose tree matches what's already on
# disk — so the working tree lines up with HEAD without touching any files.
# From there `git pull`, `git log`, and rich `git describe` (e.g.
# "v3.0.4-224-g…") all work as they would on a normal clone.
#
# Run on the device:
#     ~/pi-stomp/util/expand-git.sh
#
# Idempotent: if the repo already has full history, it no-ops.
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
META_DIR="$SRC_DIR/.git-meta"

if [ ! -f "$META_DIR/origin-url" ]; then
    echo "Error: $META_DIR/origin-url not found (not a git-packaged install?)" >&2
    exit 1
fi

BRANCH=$(cat "$META_DIR/branch" 2>/dev/null || echo "main")
BUILT_SHA=$(cat "$META_DIR/built-sha" 2>/dev/null || true)

if [ ! -d "$SRC_DIR/.git" ]; then
    echo "==> Initializing git repo"
    git init -q -b "$BRANCH" "$SRC_DIR"
    git -C "$SRC_DIR" config user.email "pi-stomp@local"
    git -C "$SRC_DIR" config user.name "pi-stomp"
    git -C "$SRC_DIR" remote add origin "$(cat "$META_DIR/origin-url")"
fi

ORIGIN=$(git -C "$SRC_DIR" remote get-url origin)

echo "==> Fetching full history + tags from $ORIGIN ($BRANCH)"
git -C "$SRC_DIR" fetch --tags origin "$BRANCH"

# Point the branch at the exact commit that was packaged (built-sha, if we
# have one — otherwise fall back to the fetched tip) and update the index
# to match. reset --mixed never touches the working tree, which already
# holds the packaged files, so this can't clobber anything on disk.
TARGET="${BUILT_SHA:-origin/$BRANCH}"
git -C "$SRC_DIR" symbolic-ref HEAD "refs/heads/$BRANCH"
git -C "$SRC_DIR" reset --mixed "$TARGET" >/dev/null

echo "==> Done"
# Write the EXPANDED marker so pi-stomp knows to use `git describe --dirty=*`
# for the version string, and pistomp-recovery knows to refuse apt upgrades
# that would overwrite the developer's git-managed tree.
touch "$SRC_DIR/.git/EXPANDED"
git -C "$SRC_DIR" describe --dirty='*' --always || true
