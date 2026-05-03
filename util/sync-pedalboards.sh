#!/bin/bash
# sync-pedalboards.sh [--dry-run] [PEDALBOARDS_DIR]
#
# Conflict-safe pedalboard sync. Never modifies the working tree if a conflict
# is possible; detects conflicts first and aborts with a clear message.
#
# Exit codes:
#   0  success (already up to date, or updates applied)
#   2  network / fetch failure
#   3  conflicts detected — sync aborted, working tree unchanged
#   1  any other error

DRY_RUN=false
PEDALBOARDS_DIR=""

for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        *) PEDALBOARDS_DIR="$arg" ;;
    esac
done

[[ -z "$PEDALBOARDS_DIR" ]] && PEDALBOARDS_DIR="/home/pistomp/data/.pedalboards"

cd "$PEDALBOARDS_DIR" 2>/dev/null || { echo "Cannot change to pedalboard dir: $PEDALBOARDS_DIR"; exit 1; }
git rev-parse --git-dir > /dev/null 2>&1 || { echo "Not a git repository: $PEDALBOARDS_DIR"; exit 1; }

# Step 2: fetch
FETCH_ERR=$(mktemp)
if ! git fetch --quiet 2>"$FETCH_ERR"; then
    echo "network: $(cat "$FETCH_ERR")"
    rm -f "$FETCH_ERR"
    exit 2
fi
rm -f "$FETCH_ERR"

# Step 3: compute refs
LOCAL=$(git rev-parse HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

if ! REMOTE=$(git rev-parse "origin/$BRANCH" 2>/dev/null); then
    echo "network: no remote tracking branch origin/$BRANCH"
    exit 2
fi

BASE=$(git merge-base "$LOCAL" "$REMOTE")

# Step 4: already up to date
if [[ "$LOCAL" == "$REMOTE" ]]; then
    echo "Already up to date"
    exit 0
fi

# Step 5: fast-forwardable with clean working tree — safe to apply directly
if [[ "$LOCAL" == "$BASE" ]] && git diff --quiet && git diff --cached --quiet; then
    COUNT=$(git rev-list HEAD.."origin/$BRANCH" --count)
    if ! $DRY_RUN; then
        git merge --ff-only --quiet "origin/$BRANCH"
        echo "$COUNT update(s) applied"
    else
        echo "$COUNT update(s) would be applied"
    fi
    exit 0
fi

# Step 6: conflict detection — never touch working tree until this passes
CONFLICTS=()

# 6a: committed-history conflicts via merge-tree (requires git >= 2.38, available on Debian Bookworm)
if [[ "$LOCAL" != "$BASE" ]]; then
    while IFS= read -r line; do
        [[ -n "$line" ]] && CONFLICTS+=("$line")
    done < <(git merge-tree --write-tree --name-only --no-messages "$LOCAL" "origin/$BRANCH" 2>/dev/null || true)
fi

# 6b: uncommitted-edit conflicts — conservative check: any file modified locally
#     that upstream also changed since the merge base is flagged
if ! git diff --quiet || ! git diff --cached --quiet; then
    mapfile -t modified < <(git diff --name-only HEAD)
    mapfile -t upstream_changed < <(git diff --name-only "$BASE" "origin/$BRANCH")
    for f in "${modified[@]}"; do
        for uc in "${upstream_changed[@]}"; do
            if [[ "$f" == "$uc" ]]; then
                CONFLICTS+=("$f (uncommitted edit)")
                break
            fi
        done
    done
fi

# Deduplicate and report
if [[ ${#CONFLICTS[@]} -gt 0 ]]; then
    printf '%s\n' "${CONFLICTS[@]}" | sort -u
    echo "Conflicts: resolve via SSH (cd $PEDALBOARDS_DIR && git pull). Sync aborted; pedalboards unchanged."
    exit 3
fi

# Step 8: no conflicts — perform the actual merge
COUNT=$(git rev-list HEAD.."origin/$BRANCH" --count)
if ! $DRY_RUN; then
    git merge --no-edit --ff "origin/$BRANCH" --quiet
    echo "$COUNT update(s) applied"
else
    echo "$COUNT update(s) would be applied"
fi
exit 0
