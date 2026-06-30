from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


KNOWN_RESULT_ARTIFACTS = (
    "editData.json",
    "output.log",
    "compare.json",
    "instance_compare.json",
    "bbox_diff.json",
    "Report.md",
    "design.json",
    "cabinet_script.js",
    "resultImage.png",
)


@dataclass(frozen=True)
class CaseRunResult:
    case_id: str
    regression: str
    status: str
    message: str
    artifacts: dict[str, str]

    def to_json(self) -> dict[str, Any]:
        return {
            "caseId": self.case_id,
            "regression": self.regression,
            "status": self.status,
            "message": self.message,
            "artifacts": self.artifacts,
        }


def clean_known_result_artifacts(result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    for artifact in KNOWN_RESULT_ARTIFACTS:
        path = result_dir / artifact
        if path.exists() and path.is_file():
            path.unlink()


def collect_artifacts(result_dir: Path, base_dir: Path | None = None) -> dict[str, str]:
    artifacts: dict[str, str] = {}
    for artifact in KNOWN_RESULT_ARTIFACTS:
        path = result_dir / artifact
        if path.exists():
            artifacts[artifact] = path.relative_to(base_dir).as_posix() if base_dir else str(path)
    return artifacts


def create_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def git_info(repo_root: Path) -> dict[str, str]:
    info: dict[str, str] = {}
    for key, command in {
        "branch": ["git", "branch", "--show-current"],
        "commit": ["git", "rev-parse", "HEAD"],
    }.items():
        completed = subprocess.run(command, cwd=repo_root, text=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)
        if completed.returncode == 0:
            info[key] = completed.stdout.strip()
    return info


def summarize_counts(results: list[CaseRunResult]) -> dict[str, int]:
    return {
        "passed": sum(1 for result in results if result.status == "passed"),
        "needs_review": sum(1 for result in results if result.status == "needs_review"),
        "error": sum(1 for result in results if result.status == "error"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
    }


def exit_code_for_results(results: list[CaseRunResult]) -> int:
    if any(result.status == "error" for result in results):
        return 2
    if any(result.status == "needs_review" for result in results):
        return 1
    return 0


def _load_json_if_exists(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError:
        return None


def _summarize_design2edit_message(result_dir: Path) -> str:
    compare = _load_json_if_exists(result_dir / "compare.json")
    if not isinstance(compare, dict):
        return "compare.json: 未生成"
    status = compare.get("status", "unknown")
    summary = compare.get("summary", {})
    if not isinstance(summary, dict):
        return f"compare.json: {status}"
    return (
        f"compare.json: {status} - "
        f"added {summary.get('added', 0)}, "
        f"removed {summary.get('removed', 0)}, "
        f"changed {summary.get('changed', 0)}"
    )


def _summarize_instance_compare(path: Path) -> str:
    instance = _load_json_if_exists(path)
    if not isinstance(instance, dict):
        return "instance_compare.json: 未生成"
    status = instance.get("status", "unknown")
    parts = [f"instance_compare.json: {status}"]
    if "expectedCount" in instance and "actualCount" in instance:
        parts.append(f"期望 {instance.get('expectedCount')} 个，实际 {instance.get('actualCount')} 个")
    missing_bgids = instance.get("missingBgids", [])
    extra_bgids = instance.get("extraBgids", [])
    if missing_bgids and extra_bgids:
        parts.append("BGID 有缺失和多余")
    elif missing_bgids:
        parts.append("BGID 有缺失")
    elif extra_bgids:
        parts.append("BGID 有多余")
    if instance.get("error"):
        parts.append(str(instance["error"]))
    return " - ".join(parts)


def _summarize_bbox_diff(path: Path) -> str:
    bbox = _load_json_if_exists(path)
    if not isinstance(bbox, dict):
        return "bbox_diff.json: 未生成"
    summary = bbox.get("summary")
    if not isinstance(summary, dict):
        return "bbox_diff.json: error - missing summary"
    different = int(summary.get("different", 0) or 0)
    only_in_scene = int(summary.get("only_in_scene", 0) or 0)
    only_in_abd = int(summary.get("only_in_abd", 0) or 0)
    status = "needs_review" if different or only_in_scene or only_in_abd else "passed"
    parts = [f"bbox_diff.json: {status}"]
    if status == "needs_review":
        parts.append(
            f"different {different}, only_in_scene {only_in_scene}, only_in_abd {only_in_abd}"
        )
    return " - ".join(parts)


def _summarize_abd2edit_message(result_dir: Path) -> str:
    return " - ".join([
        _summarize_instance_compare(result_dir / "instance_compare.json"),
        _summarize_bbox_diff(result_dir / "bbox_diff.json"),
    ])


def build_case_message(result_dir: Path, regression: str, status: str, fallback: str = "") -> str:
    if status in {"passed", "skipped"}:
        return fallback
    if regression == "design2edit":
        artifact_message = _summarize_design2edit_message(result_dir)
    elif regression == "abd2edit":
        artifact_message = _summarize_abd2edit_message(result_dir)
    else:
        artifact_message = ""
    if fallback and artifact_message:
        return f"{fallback} - {artifact_message}"
    return artifact_message or fallback


def _markdown_table_cell(value: Any) -> str:
    return str(value or "").replace("\n", "<br>").replace("|", "\\|")


def _relative_existing_path(paths: tuple[Path, ...], base_dir: Path) -> str:
    for path in paths:
        if path.exists():
            return path.relative_to(base_dir).as_posix()
    return ""


def _result_with_images(result: CaseRunResult, cases_root: Path) -> dict[str, Any]:
    item = result.to_json()
    case_dir = cases_root / result.case_id
    item["previewImg"] = _relative_existing_path((
        case_dir / "source" / "previewImg.jpg",
        case_dir / "source" / "previewImg.png",
        case_dir / "source" / "previewImage.png",
    ), cases_root)
    item["currentImg"] = _relative_existing_path((
        case_dir / "result" / "currentImg.jpg",
        case_dir / "result" / "currentImg.png",
        case_dir / "result" / "resultImage.png",
    ), cases_root)
    return item


def write_run_summary(cases_root: Path, repo_root: Path, command: str, results: list[CaseRunResult]) -> Path:
    run_id = create_run_id()
    run_dir = cases_root / ".runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    counts = summarize_counts(results)
    summary = {
        "runId": run_id,
        "command": command,
        "git": git_info(repo_root),
        "counts": counts,
        "results": [_result_with_images(result, cases_root) for result in results],
    }
    summary_path = run_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    write_summary_markdown(run_dir / "Summary.md", summary)
    return summary_path


def write_summary_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        f"# Regression Summary: {summary['runId']}",
        "",
        "## Counts",
        "",
        "| Status | Count |",
        "| --- | ---: |",
    ]
    for status, count in summary["counts"].items():
        lines.append(f"| {status} | {count} |")
    lines.extend([
        "",
        "## Results",
        "",
        "| Case | Regression | Status | Message | Preview Img | Current Img | Artifacts |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])
    for result in summary["results"]:
        artifact_links = "<br>".join(
            f"[{name}](../../{artifact_path})" for name, artifact_path in result.get("artifacts", {}).items()
        )
        preview_img = result.get("previewImg", "")
        current_img = result.get("currentImg", "")
        preview_link = f"![](../../{preview_img})" if preview_img else ""
        current_link = f"![](../../{current_img})" if current_img else ""
        lines.append(
            f"| {_markdown_table_cell(result['caseId'])} | "
            f"{_markdown_table_cell(result['regression'])} | "
            f"{_markdown_table_cell(result['status'])} | "
            f"{_markdown_table_cell(result['message'])} | "
            f"{preview_link} | "
            f"{current_link} | "
            f"{artifact_links} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
