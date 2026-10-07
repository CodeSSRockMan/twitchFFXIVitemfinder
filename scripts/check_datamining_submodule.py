#!/usr/bin/env python3
"""Check and optionally update the vendor/ffxiv-datamining submodule.

Usage:
  python scripts/check_datamining_submodule.py      # check status
  python scripts/check_datamining_submodule.py --update  # attempt fast-forward update
"""
import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd, cwd=None):
    return subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def main():
    parser = argparse.ArgumentParser(description="Check/update vendor/ffxiv-datamining submodule")
    parser.add_argument("--update", "-u", action="store_true", help="Attempt to fast-forward pull if update available")
    args = parser.parse_args()

    submodule = Path("vendor/ffxiv-datamining")
    if not submodule.exists() or not submodule.is_dir():
        print(f"Submodule not found at {submodule}")
        print("Add it with:")
        print("  git submodule add https://github.com/xivapi/ffxiv-datamining vendor/ffxiv-datamining")
        print("  git submodule update --init --recursive")
        sys.exit(1)

    # fetch origin
    run(["git", "fetch", "origin"], cwd=str(submodule))

    local = run(["git", "rev-parse", "HEAD"], cwd=str(submodule))
    if local.returncode != 0:
        print("Failed to get local commit")
        sys.exit(2)
    local_sha = local.stdout.strip()

    ls_remote = run(["git", "ls-remote", "origin", "HEAD"], cwd=str(submodule))
    remote_sha = ""
    if ls_remote.returncode == 0 and ls_remote.stdout:
        remote_sha = ls_remote.stdout.split()[0].strip()
    else:
        remote_ref = run(["git", "rev-parse", "origin/HEAD"], cwd=str(submodule))
        if remote_ref.returncode == 0:
            remote_sha = remote_ref.stdout.strip()

    if not remote_sha:
        print("Unable to determine remote HEAD commit.")
        sys.exit(3)

    if local_sha != remote_sha:
        print(f"Update available: local={local_sha} remote={remote_sha}")
        if args.update:
            pull = run(["git", "pull", "--ff-only"], cwd=str(submodule))
            if pull.returncode == 0:
                new = run(["git", "rev-parse", "HEAD"], cwd=str(submodule))
                print("Submodule updated to", new.stdout.strip())
            else:
                print("Pull failed; manual intervention required.")
                print(pull.stderr)
                sys.exit(4)
        else:
            print("Run with --update to attempt a fast-forward pull.")
    else:
        print("Submodule is up-to-date.")


if __name__ == '__main__':
    main()
