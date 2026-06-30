"""
Wipe contents under workspace tmp/, optionally preserving files by basename.

Usage:
    python utils/wipe_temp.py --all
    python utils/wipe_temp.py --all --except abd.json
    python utils/wipe_temp.py --all --except abd.json param_current.json
    python utils/wipe_temp.py --all --tmp-dir path/to/tmp
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

DATA_TOOLS_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = DATA_TOOLS_ROOT.parent
DEFAULT_TMP_DIR = REPO_ROOT / "workspace" / "tmp"


def _collect_keep_paths(tmp_dir: Path, except_names: set[str]) -> set[Path]:
    """Return absolute paths of files to keep and their ancestor dirs under tmp_dir."""
    tmp_resolved = tmp_dir.resolve()
    keep: set[Path] = set()
    if not except_names or not tmp_dir.is_dir():
        return keep

    for path in tmp_dir.rglob("*"):
        if not path.is_file() or path.name not in except_names:
            continue
        current = path.resolve()
        keep.add(current)
        parent = current.parent
        while True:
            keep.add(parent)
            if parent == tmp_resolved:
                break
            parent = parent.parent
    return keep


def wipe_tmp(tmp_dir: Path, except_names: set[str] | None = None) -> tuple[list[str], list[str]]:
    """
    Remove files and directories under tmp_dir.

    When except_names is given, matching files (by basename anywhere under tmp_dir)
    and their parent directory chain are preserved.

    Returns (deleted, kept) as relative path strings.
    """
    if not tmp_dir.is_dir():
        return [], []

    tmp_resolved = tmp_dir.resolve()
    keep = _collect_keep_paths(tmp_dir, except_names or set())

    all_paths = sorted(
        {p for p in tmp_dir.rglob("*")} | set(tmp_dir.iterdir()),
        key=lambda p: len(p.parts),
        reverse=True,
    )

    deleted: list[str] = []
    kept: list[str] = []

    for path in all_paths:
        resolved = path.resolve()
        rel = str(path.relative_to(tmp_dir))
        if resolved in keep:
            if path.is_file():
                kept.append(rel)
            continue

        if path.is_file() or path.is_symlink():
            path.unlink()
            deleted.append(rel)
        elif path.is_dir():
            try:
                path.rmdir()
            except OSError:
                shutil.rmtree(path)
            deleted.append(rel + "/")

    return deleted, kept


def main() -> int:
    parser = argparse.ArgumentParser(description="Wipe contents under workspace tmp/.")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Delete all files and subdirectories under tmp",
    )
    parser.add_argument(
        "--except",
        nargs="+",
        dest="except_names",
        metavar="FILENAME",
        help="Basenames to preserve along with their parent directory structure",
    )
    parser.add_argument(
        "--tmp-dir",
        type=Path,
        default=DEFAULT_TMP_DIR,
        help=f"tmp directory to clean (default: {DEFAULT_TMP_DIR})",
    )
    args = parser.parse_args()

    if not args.all:
        parser.error("--all is required")

    tmp_dir = args.tmp_dir.resolve()
    except_set = set(args.except_names or [])
    deleted, kept = wipe_tmp(tmp_dir, except_set)

    if except_set:
        print(f"Preserved basenames: {', '.join(sorted(except_set))}")
    if kept:
        print(f"Kept {len(kept)} file(s) under {tmp_dir}")
        for name in sorted(kept):
            print(f"  + {name}")
    if deleted:
        print(f"Removed {len(deleted)} path(s) under {tmp_dir}")
        for name in deleted:
            print(f"  - {name}")
    elif not kept:
        print(f"Nothing to clear under {tmp_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
