from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any


PASSED = "passed"
NEEDS_REVIEW = "needs_review"
ERROR = "error"
REPO_ROOT = Path(__file__).resolve().parents[2]
BBOX_COMPARE_SCRIPT = REPO_ROOT / "workspace" / "skills" / "parametric-model-design" / "scripts" / "compare_scene_bbox.py"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def extract_abd_instances(abd_data: Any) -> tuple[list[str], Counter[str], list[str]]:
    if not isinstance(abd_data, dict):
        raise ValueError("abd root must be an object")
    units = abd_data.get("units")
    if not isinstance(units, list):
        raise ValueError("abd units must be an array")
    bgids: list[str] = []
    unit_ids: list[str] = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            raise ValueError(f"abd units[{index}] must be an object")
        bgid = unit.get("obsBrandGoodId")
        if isinstance(bgid, str) and bgid:
            bgids.append(bgid)
        unit_id = unit.get("id")
        if isinstance(unit_id, str) and unit_id:
            unit_ids.append(unit_id)
    return bgids, Counter(bgids), unit_ids


def extract_scene_instances(scene_data: Any) -> tuple[list[str], Counter[str]]:
    if not isinstance(scene_data, dict):
        raise ValueError("scene root must be an object")
    instances = scene_data.get("modelInstances")
    if instances is None:
        instances = scene_data.get("scene_info", {}).get("modelInstances") if isinstance(scene_data.get("scene_info"), dict) else None
    if not isinstance(instances, list):
        raise ValueError("scene modelInstances must be an array")
    bgids: list[str] = []
    for index, instance in enumerate(instances):
        if not isinstance(instance, dict):
            raise ValueError(f"modelInstances[{index}] must be an object")
        bgid = instance.get("obsBrandGoodId")
        if isinstance(bgid, str) and bgid:
            bgids.append(bgid)
    return bgids, Counter(bgids)


def compare_instance_counts(abd_data: Any, scene_data: Any) -> dict[str, Any]:
    try:
        expected_bgids, expected_counts, unit_ids = extract_abd_instances(abd_data)
        actual_bgids, actual_counts = extract_scene_instances(scene_data)
    except ValueError as exc:
        return {
            "status": ERROR,
            "error": str(exc),
            "expectedCount": 0,
            "actualCount": 0,
            "missingBgids": [],
            "extraBgids": [],
        }

    missing_bgids = sorted(bgid for bgid in expected_counts if actual_counts.get(bgid, 0) < expected_counts[bgid])
    extra_bgids = sorted(bgid for bgid in actual_counts if expected_counts.get(bgid, 0) < actual_counts[bgid])
    status = PASSED if len(expected_bgids) == len(actual_bgids) and not missing_bgids and not extra_bgids else NEEDS_REVIEW
    return {
        "status": status,
        "expectedCount": len(expected_bgids),
        "actualCount": len(actual_bgids),
        "missingBgids": missing_bgids,
        "extraBgids": extra_bgids,
        "unitIds": unit_ids,
        "expectedBgidCounts": dict(sorted(expected_counts.items())),
        "actualBgidCounts": dict(sorted(actual_counts.items())),
    }


def compare_instance_files(abd_path: Path, scene_path: Path, output_path: Path) -> dict[str, Any]:
    result = compare_instance_counts(load_json(abd_path), load_json(scene_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def evaluate_bbox_diff(output_path: Path) -> dict[str, Any]:
    data = load_json(output_path)
    summary = data.get("summary") if isinstance(data, dict) else None
    if not isinstance(summary, dict):
        return {"status": ERROR, "error": "bbox_diff.json missing summary"}
    different = int(summary.get("different", 0) or 0)
    only_in_scene = int(summary.get("only_in_scene", 0) or 0)
    only_in_abd = int(summary.get("only_in_abd", 0) or 0)
    status = PASSED if different == 0 and only_in_scene == 0 and only_in_abd == 0 else NEEDS_REVIEW
    return {
        "status": status,
        "summary": summary,
        "note": "bboxToleranceMm is fixed by compare_scene_bbox.py; runner does not override it.",
    }


def run_bbox_compare(abd_path: Path, output_path: Path, result_dir: Path, parameditor_base_url: str) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_parameditor_url = parameditor_base_url.rstrip("/")
    if normalized_parameditor_url.endswith("/sse"):
        normalized_parameditor_url = normalized_parameditor_url[:-4]
    command = [
        sys.executable,
        str(BBOX_COMPARE_SCRIPT),
        "--abd",
        str(abd_path),
        "--parameditor-base-url",
        normalized_parameditor_url,
        "-o",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.stdout:
        with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
            log_file.write(completed.stdout.rstrip() + "\n")
    if completed.returncode != 0:
        with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
            log_file.write(f"error: compare_scene_bbox.py failed with exit code {completed.returncode}\n")
        return {"status": ERROR, "error": "compare_scene_bbox.py failed"}
    return evaluate_bbox_diff(output_path)
