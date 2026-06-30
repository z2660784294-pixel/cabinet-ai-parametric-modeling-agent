#!/usr/bin/env python3
"""Run the category analysis pipeline for combo-cabinet model categories."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
UTILS_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "temp" / "category"


class PipelineError(RuntimeError):
    pass


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def run_step(name: str, command: list[str], cwd: Path) -> dict[str, Any]:
    print(f"\n=== {name} ===", flush=True)
    print(" ".join(command), flush=True)
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.stdout:
        print(completed.stdout, end="", flush=True)
    if completed.stderr:
        print(completed.stderr, end="", file=sys.stderr, flush=True)
    result = {
        "name": name,
        "command": command,
        "returnCode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
    if completed.returncode != 0:
        raise PipelineError(f"Step failed: {name}")
    return result


def required_files_complete(root: Path, bgids: list[str]) -> tuple[bool, dict[str, list[str]]]:
    missing: dict[str, list[str]] = {}
    for bgid in bgids:
        item_missing = [
            filename
            for filename in ("editorData.json", "paramModel.json", "previewImage.png")
            if not (root / bgid / filename).exists()
        ]
        if item_missing:
            missing[bgid] = item_missing
    return not missing, missing


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_outputs(output_root: Path) -> dict[str, Any]:
    cases_root = output_root / "cases"
    unit_root = output_root / "unit-pool"
    manifest_path = unit_root / "bgid-list.json"
    manifest = load_json(manifest_path)
    combo_bgids = [str(item) for item in manifest.get("comboBgids", [])]
    unit_bgids = [str(item) for item in manifest.get("unitBgids", [])]
    cases_complete, cases_missing = required_files_complete(cases_root, combo_bgids)
    units_complete, units_missing = required_files_complete(unit_root, unit_bgids)
    expected_files = {
        "compositionReport": output_root / "组合柜-单元柜关系.md",
        "customParamsJson": output_root / "custom-params-analysis.json",
        "customParamsMd": output_root / "custom-params-analysis.md",
        "customParamsTemplateJson": output_root / "custom_params_template.json",
        "customParamsTemplateMd": output_root / "custom_params_template.md",
        "paramRelationJson": output_root / "paramRelation.json",
        "paramRelationMd": output_root / "paramRelation.md",
        "paramRelationTreeMd": output_root / "paramRelation_tree.md",
    }
    missing_outputs = {name: str(path) for name, path in expected_files.items() if not path.exists()}
    return {
        "status": "success" if cases_complete and units_complete and not missing_outputs else "failed",
        "comboCount": len(combo_bgids),
        "unitCount": len(unit_bgids),
        "casesMissing": cases_missing,
        "unitsMissing": units_missing,
        "missingOutputs": missing_outputs,
        "outputs": {name: str(path) for name, path in expected_files.items()},
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run category data fetch and analysis pipeline.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--category-name", help="Catalogue category display name or path to analyze")
    mode.add_argument("--category-id", help="Catalogue categoryId to analyze")
    parser.add_argument("--output-root", default=str(DEFAULT_OUTPUT_ROOT), help=f"Pipeline output folder (default: {DEFAULT_OUTPUT_ROOT})")
    parser.add_argument("--batch-size", type=int, default=20, help="Category query batch size")
    parser.add_argument("--limit", type=int, help="Limit combo count for smoke testing")
    parser.add_argument("--overwrite", action="store_true", help="Re-fetch files even if outputs already exist")
    parser.add_argument("--strict", action="store_true", help="Run validation/report steps in strict mode")
    return parser.parse_args()


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    output_root = Path(args.output_root).resolve()
    cases_root = output_root / "cases"
    unit_root = output_root / "unit-pool"
    manifest_path = unit_root / "bgid-list.json"
    category_arg = ["--category-id", args.category_id] if args.category_id else ["--category-name", args.category_name]
    common_limit = ["--limit", str(args.limit)] if args.limit is not None else []
    overwrite = ["--overwrite"] if args.overwrite else []
    strict = ["--strict"] if args.strict else []
    python = sys.executable

    steps = [
        (
            "fetch combo cases",
            [
                python,
                str(UTILS_ROOT / "fetch_combo_case_data.py"),
                *category_arg,
                "--output-root",
                str(cases_root),
                "--batch-size",
                str(args.batch_size),
                *common_limit,
                *overwrite,
            ],
        ),
        (
            "fetch unit pool",
            [
                python,
                str(UTILS_ROOT / "fetch_combo_unit_pool.py"),
                *category_arg,
                "--cases-root",
                str(cases_root),
                "--unit-root",
                str(unit_root),
                "--batch-size",
                str(args.batch_size),
                *common_limit,
                *overwrite,
            ],
        ),
        (
            "build composition report",
            [
                python,
                str(UTILS_ROOT / "build_composition_report.py"),
                "--cases-root",
                str(cases_root),
                "--unit-root",
                str(unit_root),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output_root / "组合柜-单元柜关系.md"),
                *strict,
            ],
        ),
        (
            "analyze custom params",
            [
                python,
                str(UTILS_ROOT / "analyze_custom_params.py"),
                "--cases-root",
                str(cases_root),
                "--output",
                str(output_root / "custom-params-analysis.json"),
                "--md-output",
                str(output_root / "custom-params-analysis.md"),
                *strict,
            ],
        ),
        (
            "generate assembly parameter template",
            [
                python,
                str(UTILS_ROOT / "generate_assembly_parameter_template.py"),
                "--cases-root",
                str(cases_root),
                "--output-dir",
                str(output_root),
                *strict,
            ],
        ),
        (
            "analyze param relations",
            [
                python,
                str(UTILS_ROOT / "analyze_param_relations.py"),
                "--cases-root",
                str(cases_root),
                "--unit-root",
                str(unit_root),
                "--manifest",
                str(manifest_path),
                "--output",
                str(output_root / "paramRelation.json"),
                "--md-output",
                str(output_root / "paramRelation.md"),
                *strict,
            ],
        ),
        (
            "render param relation tree",
            [
                python,
                str(UTILS_ROOT / "analyze_param_relations_tree.py"),
                "--cases-root",
                str(cases_root),
                "--unit-root",
                str(unit_root),
                "--manifest",
                str(manifest_path),
                "--md-output",
                str(output_root / "paramRelation_tree.md"),
                *strict,
            ],
        ),
    ]

    results: list[dict[str, Any]] = []
    try:
        output_root.mkdir(parents=True, exist_ok=True)
        for name, command in steps:
            results.append(run_step(name, command, REPO_ROOT))
        validation = validate_outputs(output_root)
        summary = {
            "status": validation["status"],
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "category": args.category_id or args.category_name,
            "outputRoot": str(output_root),
            "casesRoot": str(cases_root),
            "unitRoot": str(unit_root),
            "manifest": str(manifest_path),
            "validation": validation,
            "steps": results,
        }
        summary_path = output_root / "pipeline-summary.json"
        summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in summary.items() if k != "steps"}, ensure_ascii=False, indent=2))
        return 0 if validation["status"] == "success" else 1
    except Exception as exc:
        summary = {
            "status": "failed",
            "generatedAt": datetime.now(timezone.utc).isoformat(),
            "category": args.category_id or args.category_name,
            "outputRoot": str(output_root),
            "error": str(exc),
            "steps": results,
        }
        output_root.mkdir(parents=True, exist_ok=True)
        (output_root / "pipeline-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(summary, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
