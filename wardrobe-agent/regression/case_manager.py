from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


REQUIRED_DESIGN2EDIT_SOURCE_FILES = ("abd.json", "design.json", "baseline.json")
DEFAULT_MANIFEST = {
    "enabled": True,
    "regressions": ["design2edit", "abd2edit"],
    "compare": {
        "ignorePaths": [],
        "numericTolerance": 0,
        "bboxToleranceMm": 20,
    },
}


@dataclass(frozen=True)
class RegressionCase:
    case_id: str
    case_dir: Path
    source_dir: Path
    result_dir: Path
    abd_path: Path
    design_path: Path
    baseline_path: Path
    preview_path: Path
    manifest_path: Path
    manifest: dict[str, Any]

    @property
    def enabled(self) -> bool:
        return bool(self.manifest.get("enabled", True))

    @property
    def regressions(self) -> tuple[str, ...]:
        values = self.manifest.get("regressions", ["design2edit", "abd2edit"])
        if not isinstance(values, list):
            return ("design2edit", "abd2edit")
        return tuple(str(value) for value in values)

    def has_design2edit_inputs(self) -> bool:
        return all((self.source_dir / name).exists() for name in REQUIRED_DESIGN2EDIT_SOURCE_FILES)

    def has_abd2edit_inputs(self) -> bool:
        return self.abd_path.exists()


def load_json_file(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def merge_manifest(raw_manifest: dict[str, Any] | None) -> dict[str, Any]:
    manifest = {
        "enabled": DEFAULT_MANIFEST["enabled"],
        "regressions": list(DEFAULT_MANIFEST["regressions"]),
        "compare": dict(DEFAULT_MANIFEST["compare"]),
    }
    if not raw_manifest:
        return manifest
    if "enabled" in raw_manifest:
        manifest["enabled"] = bool(raw_manifest["enabled"])
    if "regressions" in raw_manifest:
        regressions = raw_manifest["regressions"]
        if not isinstance(regressions, list) or not all(isinstance(value, str) for value in regressions):
            raise RuntimeError("case.json regressions must be a list of strings")
        manifest["regressions"] = regressions
    if "compare" in raw_manifest:
        compare = raw_manifest["compare"]
        if not isinstance(compare, dict):
            raise RuntimeError("case.json compare must be an object")
        manifest["compare"].update(compare)
    return manifest


def load_manifest(source_dir: Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = source_dir / "case.json"
    if not manifest_path.exists():
        return manifest_path, merge_manifest(None)
    try:
        raw_manifest = load_json_file(manifest_path)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {manifest_path}: {exc}") from exc
    if not isinstance(raw_manifest, dict):
        raise RuntimeError(f"case manifest must be a JSON object: {manifest_path}")
    return manifest_path, merge_manifest(raw_manifest)


def load_case(cases_root: Path, case_id: str) -> RegressionCase:
    case_dir = cases_root / case_id
    source_dir = case_dir / "source"
    result_dir = case_dir / "result"
    result_dir.mkdir(parents=True, exist_ok=True)
    manifest_path, manifest = load_manifest(source_dir)
    return RegressionCase(
        case_id=case_id,
        case_dir=case_dir,
        source_dir=source_dir,
        result_dir=result_dir,
        abd_path=source_dir / "abd.json",
        design_path=source_dir / "design.json",
        baseline_path=source_dir / "baseline.json",
        preview_path=source_dir / "previewImage.png",
        manifest_path=manifest_path,
        manifest=manifest,
    )


def validate_json_file(path: Path) -> None:
    try:
        load_json_file(path)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid JSON in {path}: {exc}") from exc


def validate_case_for_design2edit(case: RegressionCase) -> None:
    for name in REQUIRED_DESIGN2EDIT_SOURCE_FILES:
        path = case.source_dir / name
        if not path.exists():
            raise RuntimeError(f"missing required source file: {path}")
        validate_json_file(path)


def validate_case_for_abd2edit(case: RegressionCase) -> None:
    if not case.abd_path.exists():
        raise RuntimeError(f"missing required source file: {case.abd_path}")
    validate_json_file(case.abd_path)


def list_cases(cases_root: Path) -> list[RegressionCase]:
    if not cases_root.exists():
        return []
    cases: list[RegressionCase] = []
    for child in sorted(cases_root.iterdir(), key=lambda path: path.name):
        if child.is_dir() and not child.name.startswith("."):
            cases.append(load_case(cases_root, child.name))
    return cases


def compare_ignore_paths(case: RegressionCase) -> tuple[str, ...] | None:
    compare = case.manifest.get("compare", {})
    ignore_paths = compare.get("ignorePaths", []) if isinstance(compare, dict) else []
    if not isinstance(ignore_paths, list) or not all(isinstance(value, str) for value in ignore_paths):
        raise RuntimeError("case.json compare.ignorePaths must be a list of strings")
    if not ignore_paths:
        return None
    return tuple(ignore_paths)


def copy_json_source(src: Path, dest: Path) -> None:
    validate_json_file(src)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)


def add_case(
    cases_root: Path,
    case_id: str,
    abd_path: Path,
    preview_path: Path | None = None,
    design_path: Path | None = None,
    baseline_path: Path | None = None,
    overwrite: bool = False,
) -> RegressionCase:
    case_dir = cases_root / case_id
    source_dir = case_dir / "source"
    if case_dir.exists() and not overwrite:
        raise RuntimeError(f"case already exists: {case_dir}")
    source_dir.mkdir(parents=True, exist_ok=True)
    copy_json_source(abd_path, source_dir / "abd.json")
    if design_path is not None:
        copy_json_source(design_path, source_dir / "design.json")
    if baseline_path is not None:
        copy_json_source(baseline_path, source_dir / "baseline.json")
    if preview_path is not None:
        if not preview_path.exists():
            raise RuntimeError(f"missing preview file: {preview_path}")
        shutil.copy2(preview_path, source_dir / "previewImage.png")
    return load_case(cases_root, case_id)


def latest_case_status(cases_root: Path, case_id: str, regression: str) -> str | None:
    runs_dir = cases_root / ".runs"
    if not runs_dir.exists():
        return None
    for run_dir in sorted((path for path in runs_dir.iterdir() if path.is_dir()), key=lambda path: path.name, reverse=True):
        summary_path = run_dir / "summary.json"
        if not summary_path.exists():
            continue
        try:
            summary = load_json_file(summary_path)
        except json.JSONDecodeError:
            continue
        for result in summary.get("results", []):
            if result.get("caseId") == case_id and result.get("regression") == regression:
                return result.get("status")
    return None


def rebaseline_case(cases_root: Path, case_id: str, force: bool = False) -> Path:
    case = load_case(cases_root, case_id)
    edit_data_path = case.result_dir / "editData.json"
    if not edit_data_path.exists():
        raise RuntimeError(f"missing result editData.json: {edit_data_path}")
    validate_json_file(edit_data_path)
    latest_status = latest_case_status(cases_root, case_id, "design2edit")
    if latest_status != "needs_review" and not force:
        raise RuntimeError("rebaseline requires latest design2edit status needs_review; use --force to override")
    if case.baseline_path.exists():
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = case.source_dir / f"baseline.{timestamp}.json"
        shutil.copy2(case.baseline_path, backup_path)
    case.source_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(edit_data_path, case.baseline_path)
    return case.baseline_path
