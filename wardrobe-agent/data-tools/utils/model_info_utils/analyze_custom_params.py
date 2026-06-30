#!/usr/bin/env python3
"""Analyze custom parameter groups in combo-cabinet case editorData files."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_ROOT = REPO_ROOT / "temp" / "cases"
DEFAULT_OUTPUT = REPO_ROOT / "temp" / "custom-params-analysis.json"
DEFAULT_MD_OUTPUT = REPO_ROOT / "temp" / "custom-params-analysis.md"
UNNAMED_GROUP = "(unnamed)"


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


def unique_values(values: list[Any], limit: int | None = None) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for value in values:
        key = json_key(value)
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
        if limit is not None and len(result) >= limit:
            break
    return result


def discover_case_dirs(cases_root: Path, selected_cases: list[str], limit: int | None) -> tuple[list[Path], list[str]]:
    warnings: list[str] = []
    if selected_cases:
        case_dirs = []
        for case_id in selected_cases:
            case_dir = cases_root / case_id
            if case_dir.is_dir():
                case_dirs.append(case_dir)
            else:
                warnings.append(f"指定 case 不存在: {case_id}")
    else:
        if not cases_root.exists():
            return [], [f"cases root 不存在: {cases_root}"]
        case_dirs = sorted(path for path in cases_root.iterdir() if path.is_dir())

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


def analyze_case(case_id: str, editor_data: dict[str, Any]) -> dict[str, Any]:
    input_map = build_input_map(editor_data)
    grouped_param_names: set[str] = set()
    group_summaries: list[dict[str, Any]] = []
    missing_refs: list[dict[str, Any]] = []

    for group in editor_data.get("customParamGroups", []) or []:
        if not isinstance(group, dict):
            continue
        group_name = str(group.get("groupName") or UNNAMED_GROUP)
        param_names = [str(name) for name in (group.get("paramNames", []) or [])]
        group_summaries.append({"groupName": group_name, "paramNames": param_names})
        for param_name in param_names:
            grouped_param_names.add(param_name)
            if param_name not in input_map:
                missing_refs.append({"case": case_id, "groupName": group_name, "paramName": param_name})

    ungrouped = sorted(param_name for param_name in input_map if param_name not in grouped_param_names)
    return {
        "case": case_id,
        "inputMap": input_map,
        "groups": group_summaries,
        "groupedParamNames": grouped_param_names,
        "ungroupedInputParams": ungrouped,
        "missingInputRefs": missing_refs,
    }


def analyze_cases(cases_root: Path, selected_cases: list[str], limit: int | None) -> tuple[dict[str, Any], list[str]]:
    case_dirs, warnings = discover_case_dirs(cases_root, selected_cases, limit)
    case_results: list[dict[str, Any]] = []
    param_stats: dict[str, dict[str, Any]] = {}
    group_stats: dict[str, dict[str, Any]] = {}
    ungrouped_by_param: dict[str, set[str]] = defaultdict(set)
    missing_input_refs: list[dict[str, Any]] = []

    for case_dir in case_dirs:
        case_id = case_dir.name
        editor_path = case_dir / "editorData.json"
        if not editor_path.exists():
            warnings.append(f"case {case_id} 缺少 editorData.json")
            continue
        try:
            editor_data = load_json(editor_path)
        except Exception as exc:
            warnings.append(f"case {case_id} editorData.json 读取失败: {exc}")
            continue
        if not isinstance(editor_data, dict):
            warnings.append(f"case {case_id} editorData.json 不是 JSON object")
            continue

        case_analysis = analyze_case(case_id, editor_data)
        case_results.append(case_analysis)
        missing_input_refs.extend(case_analysis["missingInputRefs"])

        for param_name in case_analysis["ungroupedInputParams"]:
            ungrouped_by_param[param_name].add(case_id)

        input_map = case_analysis["inputMap"]
        for group in case_analysis["groups"]:
            group_name = group["groupName"]
            if group_name not in group_stats:
                group_stats[group_name] = {"paramNames": set(), "cases": set()}
            group_stats[group_name]["cases"].add(case_id)
            for param_name in group["paramNames"]:
                group_stats[group_name]["paramNames"].add(param_name)
                if param_name not in param_stats:
                    param_stats[param_name] = {
                        "displayName": "",
                        "groups": set(),
                        "cases": set(),
                        "values": [],
                        "formulaCounter": Counter(),
                        "formulaFormCounter": Counter(),
                    }
                stat = param_stats[param_name]
                stat["cases"].add(case_id)
                stat["groups"].add(group_name)
                input_item = input_map.get(param_name)
                if not input_item:
                    continue
                display_name = input_item.get("displayName")
                if display_name:
                    stat["displayName"] = str(display_name)
                formula = input_item.get("formula")
                if formula not in (None, ""):
                    stat["formulaCounter"][str(formula)] += 1
                formula_form = input_item.get("formulaForm")
                if formula_form not in (None, ""):
                    stat["formulaFormCounter"][str(formula_form)] += 1
                if "value" in input_item and input_item.get("value") is not None:
                    stat["values"].append(input_item.get("value"))

    total_cases = len(case_results)
    params = []
    for param_name, stat in param_stats.items():
        formulas = stat["formulaCounter"] or stat["formulaFormCounter"]
        formula_variants = [
            {"formula": formula, "count": count}
            for formula, count in formulas.most_common()
        ]
        params.append(
            {
                "paramName": param_name,
                "displayName": stat["displayName"],
                "count": len(stat["cases"]),
                "pct": pct(len(stat["cases"]), total_cases),
                "groups": sorted(stat["groups"]),
                "cases": sorted(stat["cases"]),
                "formula": formula_variants[0]["formula"] if formula_variants else None,
                "formulaVariants": formula_variants,
                "sampleValues": unique_values(stat["values"], 5),
            }
        )
    params.sort(key=lambda item: (-item["count"], item["paramName"]))

    groups = []
    for group_name, stat in group_stats.items():
        groups.append(
            {
                "name": group_name,
                "count": len(stat["cases"]),
                "pct": pct(len(stat["cases"]), total_cases),
                "paramNames": sorted(stat["paramNames"]),
                "cases": sorted(stat["cases"]),
            }
        )
    groups.sort(key=lambda item: (-item["count"], item["name"]))

    case_summaries = []
    for result in case_results:
        case_summaries.append(
            {
                "case": result["case"],
                "groupCount": len(result["groups"]),
                "groupedParamCount": len(result["groupedParamNames"]),
                "inputCount": len(result["inputMap"]),
                "ungroupedInputParamCount": len(result["ungroupedInputParams"]),
                "missingInputRefCount": len(result["missingInputRefs"]),
            }
        )

    output = {
        "total_cases": total_cases,
        "cases_root": str(cases_root),
        "cases": case_summaries,
        "params": params,
        "groups": groups,
        "ungroupedInputParams": [
            {"paramName": param_name, "count": len(cases), "cases": sorted(cases)}
            for param_name, cases in sorted(ungrouped_by_param.items())
        ],
        "missingInputRefs": missing_input_refs,
        "warnings": warnings,
    }
    return output, warnings


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def compact_formula(param: dict[str, Any]) -> str:
    if param.get("formula"):
        variants = param.get("formulaVariants", [])
        if len(variants) <= 1:
            return md_escape(param["formula"])
        return md_escape(f"{param['formula']} 等 {len(variants)} 种")
    values = param.get("sampleValues", [])
    if values:
        return md_escape("样本值: " + ", ".join(str(value) for value in values[:5]))
    return "—"


def render_markdown(result: dict[str, Any]) -> str:
    total = result["total_cases"]
    lines = [
        f"# 组合柜自定义参数分析报告",
        "",
        f"> 数据来源：`{result['cases_root']}`。",
        f"> 样本数：{total}；分组参数数：{len(result['params'])}；参数组数：{len(result['groups'])}；缺失输入引用：{len(result['missingInputRefs'])}；警告：{len(result['warnings'])}。",
        "",
        "## 参数总览",
        "",
        "| 参数名 | 中文名 | 出现频次 | 占比 | 所属分组 | 公式 / 典型值 |",
        "|---|---|---:|---:|---|---|",
    ]
    for param in result["params"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(param["paramName"]),
                    md_escape(param["displayName"] or "—"),
                    str(param["count"]),
                    f"{param['pct']}%",
                    md_escape(" / ".join(param["groups"])),
                    compact_formula(param),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 参数组总览", "", "| 参数组 | 出现频次 | 占比 | 参数数量 | 参数名 |", "|---|---:|---:|---:|---|"])
    for group in result["groups"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    md_escape(group["name"]),
                    str(group["count"]),
                    f"{group['pct']}%",
                    str(len(group["paramNames"])),
                    md_escape(", ".join(group["paramNames"])),
                ]
            )
            + " |"
        )

    lines.extend(["", "## 样本概览", "", "| Case | 参数组数 | 分组参数数 | inputs 数 | 未分组 inputs 数 | 缺失引用数 |", "|---|---:|---:|---:|---:|---:|"])
    for case in result["cases"]:
        lines.append(
            f"| {md_escape(case['case'])} | {case['groupCount']} | {case['groupedParamCount']} | {case['inputCount']} | {case['ungroupedInputParamCount']} | {case['missingInputRefCount']} |"
        )

    lines.extend(["", "## 公式变体", ""])
    params_with_variants = [param for param in result["params"] if len(param.get("formulaVariants", [])) > 1]
    if not params_with_variants:
        lines.append("- 无")
    else:
        for param in params_with_variants:
            lines.append(f"### {md_escape(param['paramName'])} — {md_escape(param['displayName'] or '')}")
            lines.append("")
            lines.append("| 公式 | 出现次数 |")
            lines.append("|---|---:|")
            for variant in param["formulaVariants"]:
                lines.append(f"| {md_escape(variant['formula'])} | {variant['count']} |")
            lines.append("")

    lines.extend(["", "## 未分组 inputs", "", "| 参数名 | 出现频次 | Cases |", "|---|---:|---|"])
    if result["ungroupedInputParams"]:
        for item in result["ungroupedInputParams"]:
            lines.append(f"| {md_escape(item['paramName'])} | {item['count']} | {md_escape(', '.join(item['cases']))} |")
    else:
        lines.append("| — | 0 | — |")

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


def print_pretty(result: dict[str, Any]) -> None:
    total = result["total_cases"]
    print(f"Total cases: {total}")
    print("\n=== 参数统计表 ===")
    print(f"{'参数名':<18}{'中文名':<18}{'频次':<8}{'占比':<8}{'所属分组':<24}公式/典型值")
    print("─" * 120)
    for param in result["params"]:
        groups = " / ".join(param["groups"])
        sample_values = ", ".join(str(value) for value in param["sampleValues"][:4])
        extra = param["formula"] or (f"样本值: {sample_values}" if sample_values else "")
        print(
            f"{param['paramName']:<18}{param['displayName']:<18}{param['count']:<8}{str(param['pct']) + '%':<8}{groups:<24}{extra}"
        )

    print("\n=== 分组统计 ===")
    for group in result["groups"]:
        print(f"\n[{group['name']}]  出现在 {group['count']}/{total} 个案例 ({group['pct']}%)")
        print(f"  参数: {', '.join(group['paramNames'])}")

    if result["missingInputRefs"]:
        print("\n=== 缺失输入引用 ===")
        for ref in result["missingInputRefs"]:
            print(f"- {ref['case']} / {ref['groupName']} / {ref['paramName']}")
    if result["warnings"]:
        print("\n=== 警告 ===")
        for warning in result["warnings"]:
            print(f"- {warning}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze combo-cabinet custom parameters from temp/cases editorData files.")
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT), help=f"Cases root (default: {DEFAULT_CASES_ROOT})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help=f"Output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT), help=f"Output Markdown path (default: {DEFAULT_MD_OUTPUT})")
    parser.add_argument("--case", action="append", default=[], help="Analyze only this case BGID; can be repeated")
    parser.add_argument("--limit", type=int, help="Limit number of cases after discovery")
    parser.add_argument("--pretty", action="store_true", help="Print a human-readable summary")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on warnings or missing input references")
    return parser.parse_args()


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    cases_root = Path(args.cases_root).resolve()
    output_path = Path(args.output).resolve()
    md_output_path = Path(args.md_output).resolve()

    result, warnings = analyze_cases(cases_root, args.case, args.limit)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output_path.parent.mkdir(parents=True, exist_ok=True)
    md_output_path.write_text(render_markdown(result), encoding="utf-8")

    if args.pretty:
        print_pretty(result)
    else:
        print(
            json.dumps(
                {
                    "status": "success",
                    "output": str(output_path),
                    "mdOutput": str(md_output_path),
                    "total_cases": result["total_cases"],
                    "paramCount": len(result["params"]),
                    "groupCount": len(result["groups"]),
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
