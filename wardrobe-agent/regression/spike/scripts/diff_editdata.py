from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def diff_values(left: Any, right: Any, path: str = "$", diffs: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if diffs is None:
        diffs = []
    if type(left) is not type(right):
        diffs.append({"path": path, "type": "type_changed", "leftType": type(left).__name__, "rightType": type(right).__name__, "left": left, "right": right})
        return diffs
    if isinstance(left, dict):
        left_keys = set(left)
        right_keys = set(right)
        for key in sorted(left_keys - right_keys):
            diffs.append({"path": f"{path}.{key}", "type": "removed", "left": left[key]})
        for key in sorted(right_keys - left_keys):
            diffs.append({"path": f"{path}.{key}", "type": "added", "right": right[key]})
        for key in sorted(left_keys & right_keys):
            diff_values(left[key], right[key], f"{path}.{key}", diffs)
        return diffs
    if isinstance(left, list):
        common = min(len(left), len(right))
        for index in range(common):
            diff_values(left[index], right[index], f"{path}[{index}]", diffs)
        for index in range(common, len(left)):
            diffs.append({"path": f"{path}[{index}]", "type": "removed", "left": left[index]})
        for index in range(common, len(right)):
            diffs.append({"path": f"{path}[{index}]", "type": "added", "right": right[index]})
        return diffs
    if left != right:
        diffs.append({"path": path, "type": "changed", "left": left, "right": right})
    return diffs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument("--output", required=True)
    parser.add_argument("--summary", required=True)
    args = parser.parse_args()

    left = json.loads(Path(args.left).read_text(encoding="utf-8"))
    right = json.loads(Path(args.right).read_text(encoding="utf-8"))
    diffs = diff_values(left, right)
    summary = {
        "status": "identical" if not diffs else "different",
        "summary": {
            "added": sum(1 for item in diffs if item["type"] == "added"),
            "removed": sum(1 for item in diffs if item["type"] == "removed"),
            "changed": sum(1 for item in diffs if item["type"] in {"changed", "type_changed"}),
            "total": len(diffs),
        },
        "diffs": diffs,
    }
    Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(args.summary).write_text(
        "# editData run1/run2 diff summary\n\n"
        f"- status: {summary['status']}\n"
        f"- added: {summary['summary']['added']}\n"
        f"- removed: {summary['summary']['removed']}\n"
        f"- changed: {summary['summary']['changed']}\n"
        f"- total: {summary['summary']['total']}\n",
        encoding="utf-8",
    )
    print(json.dumps(summary["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
