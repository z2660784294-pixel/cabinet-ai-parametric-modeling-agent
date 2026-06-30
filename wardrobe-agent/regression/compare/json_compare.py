from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_IGNORE_PATHS = (
    "$.inputs[*].id",
    "$.modelInstances[*].uniqueId",
)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def matches_ignore_path(path: str, pattern: str) -> bool:
    path_parts = path.replace("[", ".[").split(".")
    pattern_parts = pattern.replace("[", ".[").split(".")
    if len(path_parts) != len(pattern_parts):
        return False
    for value, expected in zip(path_parts, pattern_parts):
        if expected == "[*]" and value.startswith("[") and value.endswith("]"):
            continue
        if value != expected:
            return False
    return True


def should_ignore(path: str, ignore_paths: tuple[str, ...]) -> bool:
    return any(matches_ignore_path(path, pattern) for pattern in ignore_paths)


def diff_values(
    baseline: Any,
    actual: Any,
    path: str,
    ignore_paths: tuple[str, ...],
    diffs: list[dict[str, Any]],
) -> None:
    if should_ignore(path, ignore_paths):
        return
    if type(baseline) is not type(actual):
        diffs.append({
            "path": path,
            "type": "changed",
            "baselineType": type(baseline).__name__,
            "actualType": type(actual).__name__,
            "baseline": baseline,
            "actual": actual,
        })
        return
    if isinstance(baseline, dict):
        baseline_keys = set(baseline)
        actual_keys = set(actual)
        for key in sorted(baseline_keys - actual_keys):
            child_path = f"{path}.{key}"
            if not should_ignore(child_path, ignore_paths):
                diffs.append({"path": child_path, "type": "removed", "baseline": baseline[key]})
        for key in sorted(actual_keys - baseline_keys):
            child_path = f"{path}.{key}"
            if not should_ignore(child_path, ignore_paths):
                diffs.append({"path": child_path, "type": "added", "actual": actual[key]})
        for key in sorted(baseline_keys & actual_keys):
            diff_values(baseline[key], actual[key], f"{path}.{key}", ignore_paths, diffs)
        return
    if isinstance(baseline, list):
        common = min(len(baseline), len(actual))
        for index in range(common):
            diff_values(baseline[index], actual[index], f"{path}[{index}]", ignore_paths, diffs)
        for index in range(common, len(baseline)):
            child_path = f"{path}[{index}]"
            if not should_ignore(child_path, ignore_paths):
                diffs.append({"path": child_path, "type": "removed", "baseline": baseline[index]})
        for index in range(common, len(actual)):
            child_path = f"{path}[{index}]"
            if not should_ignore(child_path, ignore_paths):
                diffs.append({"path": child_path, "type": "added", "actual": actual[index]})
        return
    if baseline != actual:
        diffs.append({"path": path, "type": "changed", "baseline": baseline, "actual": actual})


def compare_json_values(
    baseline: Any,
    actual: Any,
    ignore_paths: tuple[str, ...] = DEFAULT_IGNORE_PATHS,
) -> dict[str, Any]:
    diffs: list[dict[str, Any]] = []
    diff_values(baseline, actual, "$", ignore_paths, diffs)
    status = "passed" if not diffs else "needs_review"
    return {
        "status": status,
        "summary": {
            "added": sum(1 for diff in diffs if diff["type"] == "added"),
            "removed": sum(1 for diff in diffs if diff["type"] == "removed"),
            "changed": sum(1 for diff in diffs if diff["type"] == "changed"),
        },
        "diffs": diffs,
    }


def compare_json_files(
    baseline_path: Path,
    actual_path: Path,
    output_path: Path,
    ignore_paths: tuple[str, ...] = DEFAULT_IGNORE_PATHS,
) -> dict[str, Any]:
    result = compare_json_values(load_json(baseline_path), load_json(actual_path), ignore_paths)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
