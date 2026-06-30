#!/usr/bin/env python3
"""
Create directory links so Cursor (prototype/.cursor/) or Claude Code
(prototype/.claude/) shares prototype/agents/ and prototype/skills/ on macOS,
Linux, and Windows.

Run once after clone (or when links are missing), from repo root:
    python scripts/setup_agent.py cursor
    python scripts/setup_agent.py claude
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
WORKSPACE = REPO_ROOT / "prototype"

# (link_path, target_path) — target is canonical content under prototype/
CURSOR_LINKS: list[tuple[Path, Path]] = [
    (WORKSPACE / ".cursor" / "agents", WORKSPACE / "agents"),
    (WORKSPACE / ".cursor" / "skills", WORKSPACE / "skills"),
]
CLAUDE_LINKS: list[tuple[Path, Path]] = [
    (WORKSPACE / ".claude" / "agents", WORKSPACE / "agents"),
    (WORKSPACE / ".claude" / "skills", WORKSPACE / "skills"),
]


def _resolve_target(link: Path) -> Path | None:
    """Return resolved target if link already points at the expected directory."""
    if not link.exists():
        return None
    try:
        resolved = link.resolve()
        return resolved if resolved.is_dir() else None
    except OSError:
        return None


def _remove_existing(link: Path) -> None:
    if link.is_symlink():
        link.unlink()
        return
    if link.is_file():
        link.unlink()
        return
    if link.is_dir():
        try:
            link.unlink()
            return
        except OSError:
            pass
        shutil.rmtree(link)
        return
    if link.exists():
        link.unlink()


def _create_link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    _remove_existing(link)
    rel_target = os.path.relpath(target, link.parent)
    if sys.platform == "win32":
        result = subprocess.run(
            ["cmd", "/c", "mklink", "/J", str(link), str(target.resolve())],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"mklink failed for {link}:\n{result.stderr or result.stdout}"
            )
    else:
        os.symlink(rel_target, link, target_is_directory=True)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create junction/symlinks so one editor's config dir shares "
            "prototype/agents/ and prototype/skills/."
        )
    )
    parser.add_argument(
        "tool",
        choices=("cursor", "claude"),
        help="Which tool to wire: cursor (prototype/.cursor/) or claude (prototype/.claude/).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    links = CURSOR_LINKS if args.tool == "cursor" else CLAUDE_LINKS
    errors: list[str] = []
    for link, target in links:
        if not target.is_dir():
            errors.append(f"target directory missing: {target}")
            continue

        existing = _resolve_target(link)
        if existing == target.resolve():
            print(
                f"ok    {link.relative_to(REPO_ROOT)}  ->  "
                f"{target.relative_to(REPO_ROOT)} (already linked)"
            )
            continue

        if existing is not None and existing != target.resolve():
            print(
                f"fix   {link.relative_to(REPO_ROOT)}  "
                f"(was -> {existing.relative_to(REPO_ROOT)})",
                file=sys.stderr,
            )

        try:
            print(
                f"link  {link.relative_to(REPO_ROOT)}  ->  "
                f"{target.relative_to(REPO_ROOT)}"
            )
            _create_link(link, target)
        except OSError as exc:
            errors.append(f"{link}: {exc}")

    if errors:
        for msg in errors:
            print(f"error: {msg}", file=sys.stderr)
        return 1

    label = "Cursor" if args.tool == "cursor" else "Claude Code"
    print(f"done — {label} will read shared agents/ and skills/ under prototype/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
