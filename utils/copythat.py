"""Utility to copy a directory tree.

Safe to import in tests (no top-level execution).
"""
import shutil
import sys
from pathlib import Path


def copytree(src, dst, **kwargs):
	"""Copy directory `src` to `dst`. Wraps shutil.copytree.

	Returns the destination path.
	"""
	src_p = Path(src)
	dst_p = Path(dst)
	if not src_p.exists():
		raise FileNotFoundError(f"Source not found: {src}")
	return shutil.copytree(str(src_p), str(dst_p), **kwargs)


def main(argv=None):
	argv = argv or sys.argv
	if len(argv) < 3:
		print("Usage: copythat.py <source> <destination>")
		raise SystemExit(2)
	source_directory = argv[1]
	destination_directory = argv[2]
	return copytree(source_directory, destination_directory)


if __name__ == '__main__':
	main()