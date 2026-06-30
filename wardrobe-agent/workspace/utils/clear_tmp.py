"""
Clear all contents under workspace tmp/.

Usage:
    python utils/clear_tmp.py
    python utils/clear_tmp.py --tmp-dir path/to/tmp
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parent


def clear_tmp(tmp_dir: Path) -> list[str]:
    """Remove all files and directories directly under tmp_dir. Returns deleted names."""
    if not tmp_dir.is_dir():
        return []

    deleted: list[str] = []
    for path in sorted(tmp_dir.iterdir()):
        name = path.name + ("/" if path.is_dir() else "")
        if path.is_file() or path.is_symlink():
            path.unlink()
            deleted.append(name)
        elif path.is_dir():
            shutil.rmtree(path)
            deleted.append(name)
    return deleted


def main() -> int:
    parser = argparse.ArgumentParser(description="Clear all contents under workspace tmp/.")
    parser.add_argument(
        "--tmp-dir",
        type=Path,
        default=WORKSPACE_ROOT / "tmp",
        help="tmp directory to clean (default: <workspace>/tmp)",
    )
    args = parser.parse_args()
    tmp_dir = args.tmp_dir.resolve()

    deleted = clear_tmp(tmp_dir)
    if deleted:
        print(f"Cleared {len(deleted)} path(s) under {tmp_dir}")
        for name in deleted:
            print(f"  - {name}")
    else:
        print(f"Nothing to clear under {tmp_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
