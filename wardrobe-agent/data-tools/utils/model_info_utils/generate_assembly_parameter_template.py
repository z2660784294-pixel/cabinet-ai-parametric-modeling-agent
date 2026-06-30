#!/usr/bin/env python3
"""Generate editable assembly parameter templates from combo-cabinet editorData files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_ROOT = REPO_ROOT / "temp" / "cases"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "temp" / "assembly-parameter-template"
UNNAMED_GROUP = "(unnamed)"
OTHER_GROUP = "【系统参数】"

PARAM_TYPE_LABELS = {
    0: "single = 0",
    1: "interval = 1",
    2: "enum = 2",
    3: "discrete = 3",
    4: "formula = 4",
    5: "fixedFormula = 5",
    6: "constant = 6",
    7: "formulaEnum = 7",
    8: "brandGoodEnum = 8",
    9: "brandGoodFormulaEnum = 9",
}


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def json_key(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def pct(count: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(count / total * 100)


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def most_common_value(counter: Counter[str]) -> str:
    if not counter:
        return ""
    return counter.most_common(1)[0][0]


def param_type_label(value: Any) -> str:
    try:
        numeric_value = int(value)
    except (TypeError, ValueError):
        return "" if value is None else str(value)
    return PARAM_TYPE_LABELS.get(numeric_value, f"unknown = {numeric_value}")


def bool_label(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return ""
    return str(value)


def formula_value(input_item: dict[str, Any]) -> str:
    formula = input_item.get("formula")
    if formula not in (None, ""):
        return str(formula)
    formula_form = input_item.get("formulaForm")
    if formula_form not in (None, ""):
        return str(formula_form)
    return ""


def discover_case_dirs(cases_root: Path, selected_cases: list[str], limit: int | None) -> tuple[list[Path], list[str]]:
    warnings: list[str] = []
    if selected_cases:
        case_dirs: list[Path] = []
        for case_id in selected_cases:
            case_dir = cases_root / case_id
            editor_path = case_dir / "editorData.json"
            if editor_path.exists():
                case_dirs.append(case_dir)
            else:
                warnings.append(f"指定 case 缺少 editorData.json: {case_id}")
    else:
        if not cases_root.exists():
            return [], [f"cases root 不存在: {cases_root}"]
        case_dirs = sorted(path.parent for path in cases_root.glob("*/editorData.json") if path.is_file())

    if limit is not None:
        case_dirs = case_dirs[:limit]
    return case_dirs, warnings


def build_input_map(editor_data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    input_map: dict[str, dict[str, Any]] = {}
    for input_item in editor_data.get("inputs", []) or []:
        if not isinstance(input_item, dict):
            continue
        param_name = input_item.get("paramName")
        if param_name:
            input_map[str(param_name)] = input_item
    return input_map


def empty_param_stat() -> dict[str, Any]:
    return {
        "cases": set(),
        "displayNames": Counter(),
        "valueTypes": Counter(),
        "descriptions": Counter(),
        "paramTypeIds": Counter(),
        "visibleValues": Counter(),
        "formulas": Counter(),
    }


def update_param_stat(stat: dict[str, Any], case_id: str, input_item: dict[str, Any]) -> None:
    stat["cases"].add(case_id)
    for source_key, counter_key in [
        ("displayName", "displayNames"),
        ("valueType", "valueTypes"),
        ("description", "descriptions"),
    ]:
        value = input_item.get(source_key)
        if value not in (None, ""):
            stat[counter_key][str(value)] += 1

    param_type_id = input_item.get("paramTypeId")
    if param_type_id is not None:
        stat["paramTypeIds"][json_key(param_type_id)] += 1

    if "visible" in input_item:
        stat["visibleValues"][json_key(input_item.get("visible"))] += 1

    formula = formula_value(input_item)
    if formula:
        stat["formulas"][formula] += 1


def counter_json_values(counter: Counter[str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for value, count in counter.most_common():
        try:
            parsed_value = json.loads(value)
        except json.JSONDecodeError:
            parsed_value = value
        result.append({"value": parsed_value, "count": count})
    return result


def render_param(param_name: str, stat: dict[str, Any], total_cases: int) -> dict[str, Any]:
    param_type_raw = most_common_value(stat["paramTypeIds"])
    visible_raw = most_common_value(stat["visibleValues"])
    try:
        param_type_value = json.loads(param_type_raw) if param_type_raw else None
    except json.JSONDecodeError:
        param_type_value = param_type_raw
    try:
        visible_value = json.loads(visible_raw) if visible_raw else None
    except json.JSONDecodeError:
        visible_value = visible_raw

    formula_variants = [
        {"formula": formula, "count": count}
        for formula, count in stat["formulas"].most_common()
    ]
    return {
        "paramName": param_name,
        "displayName": most_common_value(stat["displayNames"]),
        "valueType": most_common_value(stat["valueTypes"]),
        "description": most_common_value(stat["descriptions"]),
        "usageCondition": "",
        "paramTypeId": param_type_value,
        "paramType": param_type_label(param_type_value),
        "formula": formula_variants[0]["formula"] if formula_variants else "",
        "formulaVariants": formula_variants,
        "visible": visible_value,
        "visibleText": bool_label(visible_value),
        "count": len(stat["cases"]),
        "pct": pct(len(stat["cases"]), total_cases),
        "cases": sorted(stat["cases"]),
        "addToTemplate": "",
        "allDisplayNames": counter_json_values(stat["displayNames"]),
        "allValueTypes": counter_json_values(stat["valueTypes"]),
        "allDescriptions": counter_json_values(stat["descriptions"]),
        "allParamTypeIds": counter_json_values(stat["paramTypeIds"]),
        "allVisibleValues": counter_json_values(stat["visibleValues"]),
    }


def analyze_cases(cases_root: Path, selected_cases: list[str], limit: int | None) -> tuple[dict[str, Any], list[str]]:
    case_dirs, warnings = discover_case_dirs(cases_root, selected_cases, limit)
    group_stats: dict[str, dict[str, Any]] = {}
    global_param_stats: dict[str, dict[str, Any]] = defaultdict(empty_param_stat)
    missing_input_refs: list[dict[str, Any]] = []
    case_summaries: list[dict[str, Any]] = []

    for case_dir in case_dirs:
        case_id = case_dir.name
        editor_path = case_dir / "editorData.json"
        try:
            editor_data = load_json(editor_path)
        except Exception as exc:
            warnings.append(f"case {case_id} editorData.json 读取失败: {exc}")
            continue
        if not isinstance(editor_data, dict):
            warnings.append(f"case {case_id} editorData.json 不是 JSON object")
            continue

        input_map = build_input_map(editor_data)
        case_group_count = 0
        case_param_names: set[str] = set()
        for group in editor_data.get("customParamGroups", []) or []:
            if not isinstance(group, dict):
                continue
            group_name = str(group.get("groupName") or UNNAMED_GROUP)
            case_group_count += 1
            if group_name not in group_stats:
                group_stats[group_name] = {"cases": set(), "params": defaultdict(empty_param_stat)}
            group_stats[group_name]["cases"].add(case_id)

            seen_param_names: set[str] = set()
            for param_name_value in group.get("paramNames", []) or []:
                param_name = str(param_name_value)
                if param_name in seen_param_names:
                    continue
                seen_param_names.add(param_name)
                case_param_names.add(param_name)
                input_item = input_map.get(param_name)
                if not input_item:
                    missing_input_refs.append({"case": case_id, "groupName": group_name, "paramName": param_name})
                    continue
                update_param_stat(group_stats[group_name]["params"][param_name], case_id, input_item)
                update_param_stat(global_param_stats[param_name], case_id, input_item)

        other_param_names = sorted(param_name for param_name in input_map if param_name not in case_param_names)
        if other_param_names:
            if OTHER_GROUP not in group_stats:
                group_stats[OTHER_GROUP] = {"cases": set(), "params": defaultdict(empty_param_stat)}
            group_stats[OTHER_GROUP]["cases"].add(case_id)
            case_group_count += 1
            for param_name in other_param_names:
                input_item = input_map[param_name]
                case_param_names.add(param_name)
                update_param_stat(group_stats[OTHER_GROUP]["params"][param_name], case_id, input_item)
                update_param_stat(global_param_stats[param_name], case_id, input_item)

        case_summaries.append(
            {
                "case": case_id,
                "groupCount": case_group_count,
                "groupedParamCount": len(case_param_names),
                "inputCount": len(input_map),
                "missingInputRefCount": len([ref for ref in missing_input_refs if ref["case"] == case_id]),
            }
        )

    total_cases = len(case_summaries)
    groups: list[dict[str, Any]] = []
    for group_name, stat in group_stats.items():
        params = [
            render_param(param_name, param_stat, total_cases)
            for param_name, param_stat in stat["params"].items()
        ]
        params.sort(key=lambda item: (-item["count"], item["paramName"]))
        groups.append(
            {
                "name": group_name,
                "responsibility": "",
                "count": len(stat["cases"]),
                "pct": pct(len(stat["cases"]), total_cases),
                "cases": sorted(stat["cases"]),
                "addToTemplate": "",
                "params": params,
            }
        )
    groups.sort(key=lambda item: (0 if item["name"] == OTHER_GROUP else 1, -item["count"], item["name"]))

    params = [
        render_param(param_name, stat, total_cases)
        for param_name, stat in global_param_stats.items()
    ]
    params.sort(key=lambda item: (-item["count"], item["paramName"]))

    output = {
        "cases_root": str(cases_root),
        "total_cases": total_cases,
        "caseCountRequested": len(case_dirs),
        "cases": case_summaries,
        "groupCount": len(groups),
        "paramCount": len(params),
        "groups": groups,
        "params": params,
        "missingInputRefs": missing_input_refs,
        "warnings": warnings,
    }
    return output, warnings


def render_formula_variants(params: list[dict[str, Any]]) -> list[str]:
    lines = ["", "## 公式全集", ""]
    params_with_formulas = [param for param in params if param.get("formulaVariants")]
    if not params_with_formulas:
        lines.append("- 无")
        return lines

    for param in params_with_formulas:
        lines.append(f"### {md_escape(param['paramName'])} — {md_escape(param.get('displayName') or '')}")
        lines.append("")
        lines.append("| 公式 | 出现次数 |")
        lines.append("|---|---:|")
        for variant in param["formulaVariants"]:
            lines.append(f"| {md_escape(variant['formula'])} | {variant['count']} |")
        lines.append("")
    return lines


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 组合柜装配参数模板",
        "",
        f"> 数据来源：`{result['cases_root']}`。",
        f"> 样本数：{result['total_cases']}；参数组数：{result['groupCount']}；参数数：{result['paramCount']}；缺失输入引用：{len(result['missingInputRefs'])}；警告：{len(result['warnings'])}。",
        "",
        "## 参数组模板",
        "",
    ]

    if not result["groups"]:
        lines.append("- 无参数组")
    for group in result["groups"]:
        lines.append(f"### {md_escape(group['name'])}")
        lines.append("")
        lines.append("| 参数组 | 职责 | 出现占比 | 加入模版 |")
        lines.append("|---|---|---:|---|")
        lines.append(
            f"| {md_escape(group['name'])} | {md_escape(group['responsibility'])} | {group['pct']}% | {md_escape(group['addToTemplate'])} |"
        )
        lines.append("")
        lines.append("| 参数引用名 | 参数显示名 | 参数值类型 | 参数说明 | 使用条件 | 参数控件类型 | 公式样例 | 可见性 | 出现占比 | 加入模版 |")
        lines.append("|---|---|---|---|---|---|---|---|---:|---|")
        if group["params"]:
            for param in group["params"]:
                lines.append(
                    "| "
                    + " | ".join(
                        [
                            md_escape(param["paramName"]),
                            md_escape(param["displayName"]),
                            md_escape(param["valueType"]),
                            md_escape(param["description"]),
                            md_escape(param["usageCondition"]),
                            md_escape(param["paramType"]),
                            md_escape(param["formula"]),
                            md_escape(param["visibleText"]),
                            f"{param['pct']}%",
                            md_escape(param["addToTemplate"]),
                        ]
                    )
                    + " |"
                )
        else:
            lines.append("| — | — | — | — | — | — | — | — | 0% | — |")
        lines.append("")

    lines.extend(render_formula_variants(result["params"]))

    lines.extend(["", "## 数据校验", ""])
    if result["missingInputRefs"]:
        lines.append("### 缺失输入引用")
        lines.append("")
        for ref in result["missingInputRefs"]:
            lines.append(f"- {md_escape(ref['case'])} / {md_escape(ref['groupName'])} / {md_escape(ref['paramName'])}")
    else:
        lines.append("- 缺失输入引用：无")
    if result["warnings"]:
        lines.append("- 警告：")
        for warning in result["warnings"]:
            lines.append(f"  - {md_escape(warning)}")
    else:
        lines.append("- 警告：无")
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate editable assembly parameter templates from combo-cabinet editorData files.")
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT), help=f"Cases root (default: {DEFAULT_CASES_ROOT})")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("--case", action="append", default=[], help="Generate from only this case BGID; can be repeated")
    parser.add_argument("--limit", type=int, help="Limit number of cases after discovery")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings or missing input references")
    return parser.parse_args()


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    cases_root = Path(args.cases_root).resolve()
    output_dir = Path(args.output_dir).resolve()
    json_output = output_dir / "custom_params_template.json"
    md_output = output_dir / "custom_params_template.md"

    result, warnings = analyze_cases(cases_root, args.case, args.limit)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output.write_text(render_markdown(result), encoding="utf-8")

    print(
        json.dumps(
            {
                "status": "success",
                "output": str(json_output),
                "mdOutput": str(md_output),
                "total_cases": result["total_cases"],
                "groupCount": result["groupCount"],
                "paramCount": result["paramCount"],
                "missingInputRefCount": len(result["missingInputRefs"]),
                "warningCount": len(warnings),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if args.strict and (warnings or result["missingInputRefs"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
