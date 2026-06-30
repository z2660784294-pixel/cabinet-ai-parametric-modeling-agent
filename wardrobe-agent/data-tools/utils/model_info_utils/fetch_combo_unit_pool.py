#!/usr/bin/env python3
"""Fetch visible unit-cabinet assets referenced by combo cases."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from fetch_model_library.api import ApiError, get_product_preview_img_url
from fetch_combo_case_data import (
    download_preview,
    fetch_model_data,
    list_products_in_categories,
    resolve_category_id,
    validate_case_files,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_ROOT = REPO_ROOT / "temp" / "cases"
DEFAULT_UNIT_ROOT = REPO_ROOT / "temp" / "unit-pool"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def extract_visible_child_instances(param_model: dict[str, Any]) -> list[dict[str, Any]]:
    return param_model.get("modelInstances", [])[1:]


def numeric_from_instance(instance: dict[str, Any]) -> int | None:
    numeric = instance.get("brandGoodId")
    if numeric is None:
        return None
    try:
        return int(numeric)
    except (TypeError, ValueError):
        return None


def extract_visible_child_numerics(param_model: dict[str, Any]) -> list[int]:
    numerics: list[int] = []
    for instance in extract_visible_child_instances(param_model):
        numeric = numeric_from_instance(instance)
        if numeric is not None:
            numerics.append(numeric)
    return numerics


def extract_editor_instances(editor_data: dict[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for instance in editor_data.get("modelInstances", []) or []:
        bgid = instance.get("obsBrandGoodId") or instance.get("brandGoodId")
        if not bgid:
            continue
        result.append(
            {
                "bgid": str(bgid),
                "name": instance.get("name") or instance.get("showName") or instance.get("modelName"),
                "uniqueId": instance.get("uniqueId"),
            }
        )
    return result


def editor_instances_by_unique_id(editor_instances: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for instance in editor_instances:
        unique_id = instance.get("uniqueId")
        if unique_id:
            result[str(unique_id)] = instance
    return result


def match_child_bgids(child_instances: list[dict[str, Any]], editor_instances: list[dict[str, Any]]) -> list[str | None]:
    editor_by_unique_id = editor_instances_by_unique_id(editor_instances)
    matched: list[str | None] = []
    for child in child_instances:
        unique_id = child.get("uniqueId")
        editor_instance = editor_by_unique_id.get(str(unique_id)) if unique_id else None
        matched.append(editor_instance["bgid"] if editor_instance else None)
    return matched


def fetch_preview_url_by_bgid(bgid: str) -> str:
    """Return previewImgUrl for a BGID via direct HTTP API."""
    preview_url = get_product_preview_img_url(bgid)
    if not preview_url:
        raise ApiError(f"Product has no previewImgUrl: {bgid}")
    return preview_url


def ensure_unit_assets(
    bgid: str,
    unit_root: Path,
    overwrite: bool,
) -> dict[str, Any]:
    unit_dir = unit_root / bgid
    model_result = fetch_model_data(bgid, unit_dir, overwrite)
    preview_url = fetch_preview_url_by_bgid(bgid)
    preview_result = download_preview(preview_url, unit_dir / "previewImage.png", overwrite)
    files = validate_case_files(unit_dir)
    if not all(files.values()):
        raise ApiError(f"Unit files are incomplete for {bgid}: {files}")
    return {
        "bgid": bgid,
        "outputDir": str(unit_dir),
        "modelData": model_result,
        "previewImage": preview_result,
        "files": files,
    }


def resolve_combo_units_manifest_only(combo_bgid: str, cases_root: Path) -> dict[str, Any]:
    combo_dir = cases_root / combo_bgid
    param_path = combo_dir / "paramModel.json"
    editor_path = combo_dir / "editorData.json"
    if not param_path.exists() or not editor_path.exists():
        raise ApiError(f"Combo source files missing for {combo_bgid}: {combo_dir}")

    child_instances = [
        instance for instance in extract_visible_child_instances(load_json(param_path)) if numeric_from_instance(instance) is not None
    ]
    child_numerics = [numeric_from_instance(instance) for instance in child_instances]
    editor_instances = extract_editor_instances(load_json(editor_path))
    matched_bgids = match_child_bgids(child_instances, editor_instances)
    unit_bgids: list[str] = []
    unresolved: list[int] = []
    warnings = []
    for child, bgid in zip(child_instances, matched_bgids):
        numeric = numeric_from_instance(child)
        if numeric is None:
            continue
        if bgid:
            unit_bgids.append(bgid)
        else:
            unresolved.append(numeric)
    counts = Counter(unit_bgids)
    if len(unit_bgids) + len(unresolved) != len(child_numerics):
        warnings.append("resolved and unresolved child count does not match visible child numeric count")
    return {
        "comboBgid": combo_bgid,
        "visibleChildNumerics": child_numerics,
        "unitBgids": unit_bgids,
        "unitCounts": dict(counts),
        "unresolvedNumerics": unresolved,
        "fetched": [],
        "warnings": warnings,
        "status": "success" if not unresolved and not warnings else "failed",
    }


def combo_bgids_from_args(args: argparse.Namespace, cases_root: Path) -> tuple[list[str], str | None]:
    if args.bgid:
        return [args.bgid], None
    category_id = args.category_id or resolve_category_id(args.category_name)
    products = list_products_in_categories([category_id], args.batch_size)
    bgids = [product["bgid"] for product in products]
    if args.limit is not None:
        bgids = bgids[: args.limit]
    missing = [bgid for bgid in bgids if not (cases_root / bgid / "paramModel.json").exists()]
    if missing:
        raise ApiError(f"Combo case data missing; run Task 1 script first for: {missing}")
    return bgids, category_id


def write_manifests(unit_root: Path, combo_bgids: list[str], results: list[dict[str, Any]], category_id: str | None) -> dict[str, Any]:
    unit_root.mkdir(parents=True, exist_ok=True)
    ordered_units: list[str] = []
    seen = set()
    by_combo: dict[str, list[str]] = {}
    for result in results:
        bgids = result.get("unitBgids", [])
        by_combo[result["comboBgid"]] = bgids
        for bgid in bgids:
            if bgid not in seen:
                seen.add(bgid)
                ordered_units.append(bgid)
    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceCategoryId": category_id,
        "comboBgids": combo_bgids,
        "unitBgids": ordered_units,
        "byCombo": by_combo,
        "results": results,
    }
    json_path = unit_root / "bgid-list.json"
    txt_path = unit_root / "bgid-list.txt"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path.write_text("\n".join(ordered_units) + ("\n" if ordered_units else ""), encoding="utf-8")
    return {"json": str(json_path), "txt": str(txt_path), "unitCount": len(ordered_units)}


def fetch_units_from_manifest(
    unit_bgids: list[str],
    unit_root: Path,
    overwrite: bool,
) -> list[dict[str, Any]]:
    results = []
    for bgid in unit_bgids:
        try:
            result = ensure_unit_assets(bgid, unit_root, overwrite)
            result["status"] = "success"
            results.append(result)
        except Exception as exc:
            results.append({"bgid": bgid, "status": "failed", "error": str(exc)})
    return results


def validate_unit_pool(unit_root: Path, unit_bgids: list[str]) -> dict[str, Any]:
    missing = {}
    for bgid in unit_bgids:
        files = validate_case_files(unit_root / bgid)
        absent = [name for name, exists in files.items() if not exists]
        if absent:
            missing[bgid] = absent
    return {"total": len(unit_bgids), "complete": len(unit_bgids) - len(missing), "missing": missing}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch visible unit assets for combo cases.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bgid", help="Single combo BGID to analyze")
    mode.add_argument("--category-id", help="Combo catalogue categoryId to analyze")
    mode.add_argument("--category-name", help="Combo catalogue category display name or path to analyze")
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT), help=f"Cases root (default: {DEFAULT_CASES_ROOT})")
    parser.add_argument("--unit-root", default=str(DEFAULT_UNIT_ROOT), help=f"Unit output root (default: {DEFAULT_UNIT_ROOT})")
    parser.add_argument("--batch-size", type=int, default=20, help="Category query batch size")
    parser.add_argument("--limit", type=int, help="Limit combo count for smoke testing")
    parser.add_argument("--overwrite", action="store_true", help="Re-fetch files even if outputs already exist")
    parser.add_argument("--manifest-only", action="store_true", help="Only write bgid-list.json and bgid-list.txt without fetching unit assets")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases_root = Path(args.cases_root).resolve()
    unit_root = Path(args.unit_root).resolve()

    try:
        combo_bgids, category_id = combo_bgids_from_args(args, cases_root)
        results = [resolve_combo_units_manifest_only(combo_bgid, cases_root) for combo_bgid in combo_bgids]
        manifest = write_manifests(unit_root, combo_bgids, results, category_id)
        all_units = load_json(Path(manifest["json"])).get("unitBgids", [])
        failed = [result for result in results if result.get("status") != "success"]
        if args.manifest_only or failed:
            summary = {
                "status": "success" if not failed else "failed",
                "mode": "manifest-only" if args.manifest_only else "manifest",
                "comboCount": len(combo_bgids),
                "unitCount": len(all_units),
                "failedCombos": [result["comboBgid"] for result in failed],
                "manifest": manifest,
                "results": results,
            }
            print(json.dumps(summary, ensure_ascii=False, indent=2))
            return 0 if not failed else 1

        fetch_results = fetch_units_from_manifest(all_units, unit_root, args.overwrite)
        validation = validate_unit_pool(unit_root, all_units)
        failed_fetches = [result for result in fetch_results if result.get("status") != "success"]
        summary = {
            "status": "success" if not failed_fetches and not validation["missing"] else "failed",
            "mode": "manifest-and-fetch",
            "comboCount": len(combo_bgids),
            "unitCount": len(all_units),
            "failedCombos": [],
            "manifest": manifest,
            "validation": validation,
            "fetchResults": fetch_results,
            "results": results,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary["status"] == "success" else 1
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
