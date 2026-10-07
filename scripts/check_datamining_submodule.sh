#!/usr/bin/env bash
set -euo pipefail

SUBMODULE_PATH="vendor/ffxiv-datamining"

if [ ! -d "$SUBMODULE_PATH" ]; then
  echo "Submodule not found at $SUBMODULE_PATH"
  echo "Add it with:"
  echo "  git submodule add https://github.com/xivapi/ffxiv-datamining $SUBMODULE_PATH"
  echo "  git submodule update --init --recursive"
  exit 1
fi

cd "$SUBMODULE_PATH"
git fetch origin >/dev/null 2>&1 || true
LOCAL=$(git rev-parse HEAD)
REMOTE_LINE=$(git ls-remote origin HEAD || true)
REMOTE=$(echo "$REMOTE_LINE" | awk '{print $1}')

if [ -z "$REMOTE" ]; then
  echo "Could not determine remote HEAD for origin. Falling back to origin/HEAD if available."
  REMOTE=$(git rev-parse origin/HEAD 2>/dev/null || true)
fi

if [ -z "$REMOTE" ]; then
  echo "Unable to determine remote commit. Abort."
  exit 2
fi

if [ "$LOCAL" != "$REMOTE" ]; then
  echo "Update available for submodule:"
  echo "  local:  $LOCAL"
  echo "  remote: $REMOTE"
  if [ "${1-}" = "--update" ] || [ "${1-}" = "-u" ]; then
    echo "Attempting fast-forward pull..."
    git pull --ff-only || { echo "Pull failed (non fast-forward). Manual intervention required."; exit 3; }
    echo "Submodule updated to $(git rev-parse HEAD)"
  else
    echo "Run: $0 --update   to pull the latest changes into the submodule (fast-forward only)."
  fi
else
  echo "Submodule is up-to-date."
fi
