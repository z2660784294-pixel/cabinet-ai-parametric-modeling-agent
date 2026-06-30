from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from regression.workspace_bridge.mcp_client import ParamEditorClient  # noqa: E402


DEFAULT_PARAMEDITOR_URL = "http://localhost:7764/sse"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clear the param editor scene and execute a cabinet_script.js file.",
    )
    parser.add_argument("cabinet_script", type=Path, help="Path to cabinet_script.js to execute")
    parser.add_argument(
        "--parameditor-url",
        default=DEFAULT_PARAMEDITOR_URL,
        help=f"ParamEditor MCP SSE URL, default: {DEFAULT_PARAMEDITOR_URL}",
    )
    return parser


def resolve_cabinet_script(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    try:
        mode = resolved.stat().st_mode
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"cabinet script not found: {resolved}") from exc
    if not stat.S_ISREG(mode):
        raise ValueError(f"cabinet script is not a file: {resolved}")
    return resolved


def run(cabinet_script: Path, parameditor_url: str) -> None:
    parameditor = ParamEditorClient(parameditor_url)
    parameditor.clear_scene()
    parameditor.execute_script(cabinet_script)


def main() -> int:
    args = build_parser().parse_args()
    try:
        cabinet_script = resolve_cabinet_script(args.cabinet_script)
        run(cabinet_script, args.parameditor_url)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"executed cabinet script: {cabinet_script}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
