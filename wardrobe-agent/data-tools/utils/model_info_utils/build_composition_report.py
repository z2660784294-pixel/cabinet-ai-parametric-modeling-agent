#!/usr/bin/env python3
"""Build a TV-cabinet combo-to-unit composition report from local temp data."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_ROOT = REPO_ROOT / "temp" / "cases"
DEFAULT_UNIT_ROOT = REPO_ROOT / "temp" / "unit-pool"
DEFAULT_MANIFEST = DEFAULT_UNIT_ROOT / "bgid-list.json"
DEFAULT_OUTPUT = REPO_ROOT / "temp" / "电视柜-composition-report.md"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_combo_dir(case_dir: Path) -> list[str]:
    required = ["editorData.json", "paramModel.json", "previewImage.png"]
    return [name for name in required if not (case_dir / name).exists()]


def validate_unit_dir(unit_dir: Path) -> list[str]:
    missing = [name for name in ["editorData.json", "paramModel.json"] if not (unit_dir / name).exists()]
    if not (unit_dir / "previewImage.png").exists() and not (unit_dir / "previewImage.jpg").exists():
        missing.append("previewImage.png|previewImage.jpg")
    return missing


def extract_root_name(editor_data: Any, fallback: str) -> str:
    instances = editor_data.get("modelInstances", []) if isinstance(editor_data, dict) else []
    if not instances:
        return fallback
    first = instances[0]
    for key in ("name", "showName", "modelName"):
        value = first.get(key) if isinstance(first, dict) else None
        if value:
            return str(value)
    return fallback


def build_name_index(root: Path, bgids: list[str]) -> dict[str, str]:
    names: dict[str, str] = {}
    for bgid in bgids:
        editor_path = root / bgid / "editorData.json"
        try:
            names[bgid] = extract_root_name(load_json(editor_path), bgid)
        except Exception:
            names[bgid] = bgid
    return names


def combo_preview_cell(output_dir: Path, cases_root: Path, bgid: str) -> str:
    path = cases_root / bgid / "previewImage.png"
    if not path.exists():
        return "—"
    return f"![]({path.relative_to(output_dir).as_posix()})"


def unit_preview_cell(output_dir: Path, unit_root: Path, bgid: str) -> str:
    for filename in ("previewImage.png", "previewImage.jpg"):
        path = unit_root / bgid / filename
        if path.exists():
            return f"![]({path.relative_to(output_dir).as_posix()})"
    return "—"


def validate_manifest(manifest: Any) -> list[str]:
    warnings: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest is not a JSON object"]
    for key in ("comboBgids", "unitBgids", "byCombo"):
        if key not in manifest:
            warnings.append(f"manifest missing key: {key}")
    if warnings:
        return warnings
    by_combo = manifest.get("byCombo", {})
    for combo_bgid in manifest.get("comboBgids", []):
        if combo_bgid not in by_combo:
            warnings.append(f"manifest byCombo missing combo: {combo_bgid}")
    return warnings


def collect_validation_warnings(cases_root: Path, unit_root: Path, manifest: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    for combo_bgid in manifest.get("comboBgids", []):
        missing = validate_combo_dir(cases_root / combo_bgid)
        if missing:
            warnings.append(f"组合柜 {combo_bgid} 缺少文件: {', '.join(missing)}")
    for unit_bgid in manifest.get("unitBgids", []):
        missing = validate_unit_dir(unit_root / unit_bgid)
        if missing:
            warnings.append(f"单元柜 {unit_bgid} 缺少文件: {', '.join(missing)}")
    by_combo = manifest.get("byCombo", {})
    unit_set = set(manifest.get("unitBgids", []))
    for combo_bgid, unit_bgids in by_combo.items():
        for unit_bgid in unit_bgids:
            if unit_bgid not in unit_set:
                warnings.append(f"组合柜 {combo_bgid} 引用了未列入 unitBgids 的单元柜: {unit_bgid}")
    return warnings


def render_header(
    manifest: dict[str, Any], cases_root: Path, unit_root: Path, manifest_path: Path, warnings: list[str]
) -> str:
    combo_count = len(manifest.get("comboBgids", []))
    unit_count = len(manifest.get("unitBgids", []))
    lines = [
        f"# {combo_count} 个电视柜组合柜组成关系报告",
        "",
        f"> 数据来源：`{cases_root.as_posix()}`、`{unit_root.as_posix()}`、`{manifest_path.as_posix()}`。",
        "> 解析方式：使用 `temp/unit-pool/bgid-list.json` 中的 `byCombo` 作为组合柜到可见子部件的有序关系；重复子部件会保留。",
        "> 预览图路径：组合柜 = `cases/{BGID}/previewImage.png`；子部件 = `unit-pool/{BGID}/previewImage.png`。",
        f"> 数据校验：组合柜 {combo_count} 个，去重单元柜 {unit_count} 个，警告 {len(warnings)} 条。",
        "",
    ]
    return "\n".join(lines)


def render_combo_section(
    output_dir: Path,
    cases_root: Path,
    unit_root: Path,
    combo_bgid: str,
    combo_name: str,
    unit_bgids: list[str],
    unit_names: dict[str, str],
) -> str:
    lines = [
        "---",
        "",
        f"## {combo_bgid} — {combo_name}",
        "",
        "| 组合柜名称 | 组合柜 ID | 组合柜预览图 | 子部件数量 | 子部件名称 | 子部件 ID | 子部件预览图 |",
        "|---|---|---|---:|---|---|---|",
        f"| {combo_name} | {combo_bgid} | {combo_preview_cell(output_dir, cases_root, combo_bgid)} | {len(unit_bgids)} |  |  |  |",
    ]
    for unit_bgid in unit_bgids:
        lines.append(
            f"|  |  |  |  | {unit_names.get(unit_bgid, unit_bgid)} | {unit_bgid} | {unit_preview_cell(output_dir, unit_root, unit_bgid)} |"
        )
    lines.append("")
    return "\n".join(lines)


def render_warning_section(warnings: list[str]) -> str:
    lines = ["---", "", "## 数据校验警告", ""]
    if not warnings:
        lines.append("- 无")
    else:
        lines.extend(f"- {warning}" for warning in warnings)
    lines.append("")
    return "\n".join(lines)


def build_report(
    cases_root: Path, unit_root: Path, manifest_path: Path, output_path: Path, strict: bool
) -> tuple[str, list[str]]:
    manifest = load_json(manifest_path)
    warnings = validate_manifest(manifest)
    if warnings and strict:
        return "", warnings
    warnings.extend(collect_validation_warnings(cases_root, unit_root, manifest))

    combo_bgids = manifest.get("comboBgids", [])
    unit_bgids = manifest.get("unitBgids", [])
    by_combo = manifest.get("byCombo", {})
    combo_names = build_name_index(cases_root, combo_bgids)
    unit_names = build_name_index(unit_root, unit_bgids)
    output_dir = output_path.parent

    parts = [render_header(manifest, cases_root, unit_root, manifest_path, warnings)]
    for combo_bgid in combo_bgids:
        parts.append(
            render_combo_section(
                output_dir,
                cases_root,
                unit_root,
                combo_bgid,
                combo_names.get(combo_bgid, combo_bgid),
                by_combo.get(combo_bgid, []),
                unit_names,
            )
        )
    parts.append(render_warning_section(warnings))
    return "\n".join(parts), warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build TV-cabinet composition report from temp data.")
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT), help=f"Cases root (default: {DEFAULT_CASES_ROOT})")
    parser.add_argument("--unit-root", default=str(DEFAULT_UNIT_ROOT), help=f"Unit root (default: {DEFAULT_UNIT_ROOT})")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help=f"Manifest path (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help=f"Output markdown path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if validation warnings exist")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases_root = Path(args.cases_root).resolve()
    unit_root = Path(args.unit_root).resolve()
    manifest_path = Path(args.manifest).resolve()
    output_path = Path(args.output).resolve()

    try:
        report, warnings = build_report(cases_root, unit_root, manifest_path, output_path, args.strict)
        if args.strict and warnings:
            print(json.dumps({"status": "failed", "warnings": warnings}, ensure_ascii=False, indent=2), file=sys.stderr)
            return 1
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(report, encoding="utf-8")
        print(
            json.dumps(
                {"status": "success", "output": str(output_path), "warnings": warnings, "warningCount": len(warnings)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
