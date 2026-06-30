from __future__ import annotations

import json
import posixpath
from pathlib import Path
from typing import Any


PASSED = "passed"
NEEDS_REVIEW = "needs_review"
ERROR = "error"


def load_json_if_exists(path: Path) -> Any:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def md_rel_path(from_dir: Path, target: Path) -> str:
    return posixpath.join(*target.relative_to(from_dir).parts) if target.is_relative_to(from_dir) else posixpath.join(*Path("..", *target.relative_to(from_dir.parent).parts).parts)


def artifact_link(result_dir: Path, path: Path, label: str) -> str:
    if not path.exists():
        return f"- {label}: 未生成"
    return f"- [{label}]({md_rel_path(result_dir, path)})"


def bbox_status(bbox_diff: Any) -> str:
    if not isinstance(bbox_diff, dict):
        return ERROR
    summary = bbox_diff.get("summary")
    if not isinstance(summary, dict):
        return ERROR
    if any(int(summary.get(key, 0) or 0) for key in ("different", "only_in_scene", "only_in_abd")):
        return NEEDS_REVIEW
    return PASSED


def generate_case_report(case: Any, overall_status: str | None = None) -> Path:
    result_dir = case.result_dir
    instance_compare = load_json_if_exists(result_dir / "instance_compare.json")
    bbox_diff = load_json_if_exists(result_dir / "bbox_diff.json")
    instance_status = instance_compare.get("status", ERROR) if isinstance(instance_compare, dict) else ERROR
    current_bbox_status = bbox_status(bbox_diff)
    if overall_status is None:
        overall_status = ERROR if ERROR in {instance_status, current_bbox_status} else NEEDS_REVIEW if NEEDS_REVIEW in {instance_status, current_bbox_status} else PASSED

    lines = [
        f"# Regression 2 Report: {case.case_id}",
        "",
        "## Summary",
        "",
        "| Item | Status |",
        "| --- | --- |",
        f"| Overall | {overall_status} |",
        f"| Instance Count | {instance_status} |",
        f"| BBox / Size | {current_bbox_status} |",
        "",
        "## Images",
        "",
    ]

    preview_image = case.source_dir / "previewImage.png"
    if preview_image.exists():
        lines.append(f"输入图：![preview]({md_rel_path(result_dir, preview_image)})")
    else:
        lines.append("输入图：未提供输入图")
    result_image = result_dir / "resultImage.png"
    if result_image.exists():
        lines.append(f"输出图：![result](resultImage.png)")
    else:
        lines.append("输出图：未生成结果图")

    lines.extend(["", "## Instance Count", ""])
    if isinstance(instance_compare, dict):
        lines.extend([
            f"- expectedCount: {instance_compare.get('expectedCount', 0)}",
            f"- actualCount: {instance_compare.get('actualCount', 0)}",
            f"- missingBgids: {', '.join(instance_compare.get('missingBgids', [])) or '无'}",
            f"- extraBgids: {', '.join(instance_compare.get('extraBgids', [])) or '无'}",
        ])
    else:
        lines.append("未生成 instance_compare.json")

    lines.extend(["", "## BBox / Size", ""])
    if isinstance(bbox_diff, dict) and isinstance(bbox_diff.get("summary"), dict):
        summary = bbox_diff["summary"]
        lines.extend([
            f"- total_compared: {summary.get('total_compared', 0)}",
            f"- identical: {summary.get('identical', 0)}",
            f"- different: {summary.get('different', 0)}",
            f"- only_in_scene: {summary.get('only_in_scene', 0)}",
            f"- only_in_abd: {summary.get('only_in_abd', 0)}",
        ])
    else:
        lines.append("未生成 bbox_diff.json")

    lines.extend([
        "",
        "## Artifacts",
        "",
        artifact_link(result_dir, result_dir / "design.json", "design.json"),
        artifact_link(result_dir, result_dir / "cabinet_script.js", "cabinet_script.js"),
        artifact_link(result_dir, result_dir / "editData.json", "editData.json"),
        artifact_link(result_dir, result_dir / "instance_compare.json", "instance_compare.json"),
        artifact_link(result_dir, result_dir / "bbox_diff.json", "bbox_diff.json"),
        artifact_link(result_dir, result_dir / "output.log", "output.log"),
    ])

    output_path = result_dir / "Report.md"
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return output_path
