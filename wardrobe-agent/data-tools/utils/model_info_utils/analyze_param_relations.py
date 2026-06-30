#!/usr/bin/env python3
"""Analyze parameter relations between combo cabinets and visible unit instances."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CASES_ROOT = REPO_ROOT / "temp" / "cases"
DEFAULT_UNIT_ROOT = REPO_ROOT / "temp" / "unit-pool"
DEFAULT_MANIFEST = DEFAULT_UNIT_ROOT / "bgid-list.json"
DEFAULT_OUTPUT = REPO_ROOT / "temp" / "paramRelation.json"
DEFAULT_MD_OUTPUT = REPO_ROOT / "temp" / "paramRelation.md"
PARAM_REF_RE = re.compile(r"#([A-Za-z_][A-Za-z0-9_]*)")
SLOT_RE = re.compile(r"^Z_A(\d+)([A-Za-z0-9_]+)$")
FUNCTION_REFS = {"abs", "ceil", "floor", "getProductCustomAttr", "max", "mid", "min", "round", "strToNum"}
KEY_INSTANCE_PARAMS = {"W", "D", "H", "Z_NB1TH", "Z_NB2TH", "Z_NB3TH", "Z_NB4TH", "Z_JX"}


def configure_output_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def md_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    return text.replace("|", "\\|").replace("\n", "<br>")


def expression_from_param(param: dict[str, Any]) -> str | None:
    for key in ("formula", "value", "formulaForm"):
        value = param.get(key)
        if isinstance(value, str) and "#" in value:
            return value
    return None


def extract_refs(expression: str | None) -> list[str]:
    if not expression:
        return []
    seen: set[str] = set()
    refs: list[str] = []
    for match in PARAM_REF_RE.finditer(expression):
        ref = match.group(1)
        if ref in FUNCTION_REFS:
            continue
        if ref not in seen:
            refs.append(ref)
            seen.add(ref)
    return refs


def slot_from_combo_param(param_name: str) -> str | None:
    match = SLOT_RE.match(param_name)
    if not match:
        return None
    return f"A{match.group(1)}"


def param_label(param_name: str, display_name: str | None = None) -> str:
    if display_name:
        return f"{param_name}({display_name})"
    return param_name


def build_input_display_names(editor_data: dict[str, Any]) -> dict[str, str]:
    names: dict[str, str] = {}
    for input_item in editor_data.get("inputs", []) or []:
        if not isinstance(input_item, dict):
            continue
        param_name = input_item.get("paramName")
        display_name = input_item.get("displayName")
        if param_name and display_name:
            names[str(param_name)] = str(display_name)
    return names


def load_name(root: Path, bgid: str) -> str:
    editor_path = root / bgid / "editorData.json"
    try:
        editor_data = load_json(editor_path)
        instances = editor_data.get("modelInstances", []) if isinstance(editor_data, dict) else []
        if instances and isinstance(instances[0], dict):
            return str(instances[0].get("name") or instances[0].get("showName") or instances[0].get("modelName") or bgid)
    except Exception:
        pass
    return bgid


def discover_cases(cases_root: Path, selected_cases: list[str], manifest: dict[str, Any], limit: int | None) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    if selected_cases:
        case_ids = selected_cases
    else:
        manifest_cases = manifest.get("comboBgids") if isinstance(manifest, dict) else None
        if isinstance(manifest_cases, list) and manifest_cases:
            case_ids = [str(case_id) for case_id in manifest_cases]
        elif cases_root.exists():
            case_ids = sorted(path.name for path in cases_root.iterdir() if path.is_dir())
        else:
            return [], [f"cases root 不存在: {cases_root}"]
    if limit is not None:
        case_ids = case_ids[:limit]
    for case_id in case_ids:
        if not (cases_root / case_id / "editorData.json").exists():
            warnings.append(f"case {case_id} 缺少 editorData.json")
    return case_ids, warnings


def build_formula_edges(case_id: str, editor_data: dict[str, Any], combo_param_names: dict[str, str]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for input_item in editor_data.get("inputs", []) or []:
        if not isinstance(input_item, dict):
            continue
        param_name = input_item.get("paramName")
        if not param_name:
            continue
        expression = expression_from_param(input_item)
        refs = extract_refs(expression)
        for ref in refs:
            edges.append(
                {
                    "case": case_id,
                    "from": str(param_name),
                    "fromDisplayName": combo_param_names.get(str(param_name), ""),
                    "fromLabel": param_label(str(param_name), combo_param_names.get(str(param_name))),
                    "to": ref,
                    "toDisplayName": combo_param_names.get(ref, ""),
                    "toLabel": param_label(ref, combo_param_names.get(ref)),
                    "expression": expression,
                    "source": "combo.inputs",
                }
            )
    return edges


def build_binding_edges(
    case_id: str,
    editor_data: dict[str, Any],
    by_combo: list[str],
    unit_names: dict[str, str],
    combo_param_names: dict[str, str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    warnings: list[str] = []
    binding_edges: list[dict[str, Any]] = []
    instance_rows: list[dict[str, Any]] = []
    all_instances = [item for item in (editor_data.get("modelInstances", []) or []) if isinstance(item, dict)]
    by_combo_counts = Counter(by_combo)
    selected_instances = []
    for instance in all_instances:
        unit_bgid = str(instance.get("obsBrandGoodId") or "")
        if by_combo_counts.get(unit_bgid, 0) <= 0:
            continue
        selected_instances.append(instance)
        by_combo_counts[unit_bgid] -= 1
    missing_bgids = [bgid for bgid, count in by_combo_counts.items() for _ in range(count)]
    if missing_bgids:
        warnings.append(f"case {case_id} byCombo 中的 BGID 未在 editorData.modelInstances 找到: {', '.join(missing_bgids)}")
    for index, instance in enumerate(selected_instances, start=1):
        unit_bgid = str(instance.get("obsBrandGoodId") or "")
        instance_name = str(instance.get("name") or f"实例{index}")
        instance_id = instance.get("instanceId") or instance.get("uniqueId") or ""
        instance_rows.append(
            {
                "case": case_id,
                "instanceIndex": index,
                "instanceId": str(instance_id),
                "name": instance_name,
                "unitBgid": unit_bgid,
                "unitName": unit_names.get(unit_bgid, unit_bgid),
            }
        )
        for param in instance.get("parameters", []) or []:
            if not isinstance(param, dict):
                continue
            target_param = param.get("paramName") or param.get("simpleName")
            if not target_param:
                continue
            expression = expression_from_param(param)
            refs = extract_refs(expression)
            if not refs:
                continue
            for ref in refs:
                slot = slot_from_combo_param(ref)
                binding_edges.append(
                    {
                        "case": case_id,
                        "fromComboParam": ref,
                        "fromComboParamDisplayName": combo_param_names.get(ref, ""),
                        "fromComboParamLabel": param_label(ref, combo_param_names.get(ref)),
                        "slot": slot,
                        "toInstanceParam": str(target_param),
                        "targetDisplayName": str(param.get("displayName") or ""),
                        "targetLabel": param_label(str(target_param), str(param.get("displayName") or "")),
                        "unitBgid": unit_bgid,
                        "unitName": unit_names.get(unit_bgid, unit_bgid),
                        "instanceIndex": index,
                        "instanceId": str(instance_id),
                        "instanceName": instance_name,
                        "expression": expression,
                        "expressionRefs": refs,
                    }
                )
    return binding_edges, instance_rows, warnings


def build_paths(formula_edges: list[dict[str, Any]], binding_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bindings_by_param: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for edge in binding_edges:
        bindings_by_param[edge["fromComboParam"]].append(edge)
    paths: list[dict[str, Any]] = []
    for edge in formula_edges:
        for binding in bindings_by_param.get(edge["to"], []):
            paths.append(
                {
                    "case": edge["case"],
                    "fromComboParam": edge["from"],
                    "fromComboParamDisplayName": edge.get("fromDisplayName", ""),
                    "fromComboParamLabel": edge.get("fromLabel", edge["from"]),
                    "viaComboParam": edge["to"],
                    "viaComboParamDisplayName": edge.get("toDisplayName", ""),
                    "viaComboParamLabel": edge.get("toLabel", edge["to"]),
                    "toInstance": f"instance[{binding['instanceIndex']}].{binding['toInstanceParam']}",
                    "toInstanceParam": binding["toInstanceParam"],
                    "toInstanceParamDisplayName": binding.get("targetDisplayName", ""),
                    "toInstanceParamLabel": binding.get("targetLabel", binding["toInstanceParam"]),
                    "unitBgid": binding["unitBgid"],
                    "unitName": binding["unitName"],
                    "slot": binding["slot"],
                    "formulaExpression": edge["expression"],
                    "bindingExpression": binding["expression"],
                }
            )
    return paths


def build_template_rules(formula_edges: list[dict[str, Any]], binding_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    formula_by_case_param: dict[tuple[str, str], dict[str, Any]] = {}
    deps_by_case_param: dict[tuple[str, str], set[str]] = defaultdict(set)
    dep_labels_by_case_param: dict[tuple[str, str], dict[str, str]] = defaultdict(dict)
    for edge in formula_edges:
        key = (edge["case"], edge["from"])
        formula_by_case_param[key] = {"expression": edge["expression"], "sourceParamLabel": edge.get("fromLabel", edge["from"])}
        deps_by_case_param[key].add(edge["to"])
        dep_labels_by_case_param[key][edge["to"]] = edge.get("toLabel", edge["to"])

    bindings_by_case_param: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for edge in binding_edges:
        bindings_by_case_param[(edge["case"], edge["fromComboParam"])].append(
            {
                "comboParam": edge["fromComboParam"],
                "comboParamDisplayName": edge.get("fromComboParamDisplayName", ""),
                "comboParamLabel": edge.get("fromComboParamLabel", edge["fromComboParam"]),
                "slot": edge["slot"] or "",
                "targetUnitParam": edge["toInstanceParam"],
                "targetUnitParamDisplayName": edge.get("targetDisplayName", ""),
                "targetUnitParamLabel": edge.get("targetLabel", edge["toInstanceParam"]),
            }
        )

    grouped: dict[str, dict[str, Any]] = {}
    for key, formula in formula_by_case_param.items():
        case_id, source_param = key
        deps = sorted(deps_by_case_param[key])
        dep_labels = [dep_labels_by_case_param[key].get(dep, dep) for dep in deps]
        slot_bindings = []
        for dep in deps:
            for binding in bindings_by_case_param.get((case_id, dep), []):
                if not binding["slot"]:
                    continue
                if binding not in slot_bindings:
                    slot_bindings.append(binding)
        if not slot_bindings:
            continue
        rule_key = json.dumps(
            {
                "sourceParam": source_param,
                "sourceParamLabel": formula.get("sourceParamLabel", source_param),
                "expression": formula["expression"],
                "slotBindings": sorted(slot_bindings, key=lambda item: (item["comboParam"], item["slot"], item["targetUnitParam"])),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        if rule_key not in grouped:
            grouped[rule_key] = {
                "sourceParam": source_param,
                "sourceParamLabel": formula.get("sourceParamLabel", source_param),
                "expression": formula["expression"],
                "dependsOnComboParams": deps,
                "dependsOnComboParamLabels": dep_labels,
                "slotBindings": sorted(slot_bindings, key=lambda item: (item["comboParam"], item["slot"], item["targetUnitParam"])),
                "cases": [],
            }
        grouped[rule_key]["cases"].append(case_id)

    rules = []
    for rule in grouped.values():
        rule["cases"] = sorted(set(rule["cases"]))
        rule["frequency"] = len(rule["cases"])
        rules.append(rule)
    rules.sort(key=lambda item: (-item["frequency"], item["sourceParam"], item["expression"]))
    return rules


def pattern_summary(binding_edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for edge in binding_edges:
        key = (edge["fromComboParam"], edge["slot"] or "", edge["toInstanceParam"])
        if key not in grouped:
            grouped[key] = {
                "comboParam": edge["fromComboParam"],
                "comboParamDisplayName": edge.get("fromComboParamDisplayName", ""),
                "comboParamLabel": edge.get("fromComboParamLabel", edge["fromComboParam"]),
                "slot": edge["slot"],
                "targetUnitParam": edge["toInstanceParam"],
                "targetUnitParamDisplayName": edge.get("targetDisplayName", ""),
                "targetUnitParamLabel": edge.get("targetLabel", edge["toInstanceParam"]),
                "cases": set(),
                "instances": 0,
            }
        grouped[key]["cases"].add(edge["case"])
        grouped[key]["instances"] += 1
    result = []
    for item in grouped.values():
        result.append(
            {
                "comboParam": item["comboParam"],
                "comboParamDisplayName": item["comboParamDisplayName"],
                "comboParamLabel": item["comboParamLabel"],
                "slot": item["slot"],
                "targetUnitParam": item["targetUnitParam"],
                "targetUnitParamDisplayName": item["targetUnitParamDisplayName"],
                "targetUnitParamLabel": item["targetUnitParamLabel"],
                "caseCount": len(item["cases"]),
                "instanceCount": item["instances"],
                "cases": sorted(item["cases"]),
            }
        )
    result.sort(key=lambda item: (-item["instanceCount"], item["comboParam"], item["targetUnitParam"]))
    return result


def analyze(cases_root: Path, unit_root: Path, manifest_path: Path, selected_cases: list[str], limit: int | None) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    by_combo = manifest.get("byCombo", {}) if isinstance(manifest, dict) else {}
    warnings: list[str] = []
    case_ids, case_warnings = discover_cases(cases_root, selected_cases, manifest, limit)
    warnings.extend(case_warnings)

    unit_names = {bgid: load_name(unit_root, bgid) for bgid in manifest.get("unitBgids", [])}
    case_results: list[dict[str, Any]] = []
    all_formula_edges: list[dict[str, Any]] = []
    all_binding_edges: list[dict[str, Any]] = []
    all_instances: list[dict[str, Any]] = []

    for case_id in case_ids:
        editor_path = cases_root / case_id / "editorData.json"
        if not editor_path.exists():
            continue
        try:
            editor_data = load_json(editor_path)
        except Exception as exc:
            warnings.append(f"case {case_id} editorData.json 读取失败: {exc}")
            continue
        if not isinstance(editor_data, dict):
            warnings.append(f"case {case_id} editorData.json 不是 JSON object")
            continue
        combo_param_names = build_input_display_names(editor_data)
        formula_edges = build_formula_edges(case_id, editor_data, combo_param_names)
        binding_edges, instance_rows, binding_warnings = build_binding_edges(
            case_id, editor_data, [str(item) for item in by_combo.get(case_id, [])], unit_names, combo_param_names
        )
        warnings.extend(binding_warnings)
        paths = build_paths(formula_edges, binding_edges)
        case_results.append(
            {
                "case": case_id,
                "comboName": load_name(cases_root, case_id),
                "instanceCount": len(instance_rows),
                "formulaEdgeCount": len(formula_edges),
                "bindingEdgeCount": len(binding_edges),
                "pathCount": len(paths),
                "instances": instance_rows,
                "formulaEdges": formula_edges,
                "bindingEdges": binding_edges,
                "paths": paths,
            }
        )
        all_formula_edges.extend(formula_edges)
        all_binding_edges.extend(binding_edges)
        all_instances.extend(instance_rows)

    template_rules = build_template_rules(all_formula_edges, all_binding_edges)
    result = {
        "casesRoot": str(cases_root),
        "unitRoot": str(unit_root),
        "manifest": str(manifest_path),
        "totalCases": len(case_results),
        "totalInstances": len(all_instances),
        "totalFormulaEdges": len(all_formula_edges),
        "totalBindingEdges": len(all_binding_edges),
        "totalPaths": sum(len(case["paths"]) for case in case_results),
        "bindingPatterns": pattern_summary(all_binding_edges),
        "templateRules": template_rules,
        "cases": case_results,
        "warnings": warnings,
    }
    return result


def render_markdown(result: dict[str, Any]) -> str:
    lines = [
        "# 组合柜与单元柜参数关系报告",
        "",
        f"> 数据来源：`{result['casesRoot']}`、`{result['unitRoot']}`、`{result['manifest']}`。",
        "> 关系解释：当前样本中，组合柜公式通常不直接引用单元柜参数；可复用关系主要表现为“组合柜槽位参数”绑定到“可见单元柜实例参数”。",
        f"> 样本数：{result['totalCases']}；单元柜实例数：{result['totalInstances']}；公式依赖边：{result['totalFormulaEdges']}；绑定边：{result['totalBindingEdges']}；可追踪路径：{result['totalPaths']}；模板规则：{len(result['templateRules'])}；警告：{len(result['warnings'])}。",
        "",
        "## 表达形式",
        "",
        "- 公式原文：保留组合柜参数的原始表达式，例如 `Z_A2W = ... - #Z_A1W - #Z_A3W`。",
        "- DAG 边：将公式中的 `#Param` 拆成 `源参数 -> 依赖参数`，只表达依赖方向，不求值。",
        "- 单元柜绑定：将槽位参数落到具体单元柜实例，例如 `Z_A1W -> instance[1].W`。",
        "- 模板规则：将具体 BGID 抽象为槽位，例如 `Z_A1W -> slot A1 -> unit.W`，用于后续类似结构复用。",
        "",
        "## 参数绑定模式汇总",
        "",
        "| 槽位参数 | 槽位 | 单元柜参数 | 出现 case 数 | 实例次数 |",
        "|---|---|---|---:|---:|",
    ]
    for item in result["bindingPatterns"][:120]:
        lines.append(
            f"| {md_escape(item['comboParamLabel'])} | {md_escape(item['slot'] or '—')} | {md_escape(item['targetUnitParamLabel'])} | {item['caseCount']} | {item['instanceCount']} |"
        )

    lines.extend(["", "## 可复用模板规则", ""])
    if not result["templateRules"]:
        lines.append("- 无")
    for index, rule in enumerate(result["templateRules"][:80], start=1):
        lines.extend(
            [
                f"### 规则 {index}: {md_escape(rule.get('sourceParamLabel', rule['sourceParam']))}",
                "",
                f"- 出现频次：{rule['frequency']} 个 case",
                f"- 出现 case：{md_escape(', '.join(rule['cases']))}",
                f"- 公式原文：`{md_escape(rule.get('sourceParamLabel', rule['sourceParam']))} = {md_escape(rule['expression'])}`",
                f"- 依赖参数：{md_escape(', '.join(rule.get('dependsOnComboParamLabels', rule['dependsOnComboParams'])))}",
                "",
                "| 槽位参数 | 槽位 | 目标单元柜参数 |",
                "|---|---|---|",
            ]
        )
        for binding in rule["slotBindings"]:
            lines.append(
                f"| {md_escape(binding.get('comboParamLabel', binding['comboParam']))} | {md_escape(binding['slot'] or '—')} | unit.{md_escape(binding.get('targetUnitParamLabel', binding['targetUnitParam']))} |"
            )
        lines.append("")

    lines.extend(["", "## 按组合柜展开", ""])
    for case in result["cases"]:
        lines.extend(
            [
                f"### {md_escape(case['case'])} — {md_escape(case['comboName'])}",
                "",
                f"- 单元柜实例数：{case['instanceCount']}；公式依赖边：{case['formulaEdgeCount']}；绑定边：{case['bindingEdgeCount']}；可追踪路径：{case['pathCount']}。",
                "",
                "#### 单元柜实例",
                "",
                "| 序号 | 实例名 | 单元柜 BGID | 单元柜名称 |",
                "|---:|---|---|---|",
            ]
        )
        for instance in case["instances"]:
            lines.append(
                f"| {instance['instanceIndex']} | {md_escape(instance['name'])} | {md_escape(instance['unitBgid'])} | {md_escape(instance['unitName'])} |"
            )

        lines.extend(["", "#### 关键公式依赖", "", "| 源参数 | 依赖参数 | 公式原文 |", "|---|---|---|"])
        formula_edges = case["formulaEdges"][:80]
        if formula_edges:
            for edge in formula_edges:
                lines.append(f"| {md_escape(edge.get('fromLabel', edge['from']))} | {md_escape(edge.get('toLabel', edge['to']))} | `{md_escape(edge['expression'])}` |")
        else:
            lines.append("| — | — | — |")

        lines.extend(["", "#### 槽位参数到单元柜参数绑定", "", "| 槽位参数 | 槽位 | 实例 | 单元柜 | 目标参数 | 表达式 |", "|---|---|---|---|---|---|"])
        key_bindings = [edge for edge in case["bindingEdges"] if edge["toInstanceParam"] in KEY_INSTANCE_PARAMS or edge["slot"]]
        if key_bindings:
            for edge in key_bindings[:120]:
                lines.append(
                    f"| {md_escape(edge.get('fromComboParamLabel', edge['fromComboParam']))} | {md_escape(edge['slot'] or '—')} | {edge['instanceIndex']} {md_escape(edge['instanceName'])} | {md_escape(edge['unitBgid'])} | {md_escape(edge.get('targetLabel', edge['toInstanceParam']))} | `{md_escape(edge['expression'])}` |"
                )
        else:
            lines.append("| — | — | — | — | — | — |")

        lines.extend(["", "#### 可追踪路径示例", "", "| 组合柜参数 | 经由槽位参数 | 单元柜实例参数 | 单元柜 |", "|---|---|---|---|"])
        if case["paths"]:
            for path in case["paths"][:80]:
                lines.append(
                    f"| {md_escape(path.get('fromComboParamLabel', path['fromComboParam']))} | {md_escape(path.get('viaComboParamLabel', path['viaComboParam']))} ({md_escape(path['slot'] or '—')}) | instance[{path['toInstance'].split('].', 1)[0].removeprefix('instance[')}].{md_escape(path.get('toInstanceParamLabel', path['toInstanceParam']))} | {md_escape(path['unitBgid'])} |"
                )
        else:
            lines.append("| — | — | — | — |")
        lines.append("")

    lines.extend(["---", "", "## 数据校验与限制", ""])
    if result["warnings"]:
        for warning in result["warnings"]:
            lines.append(f"- {md_escape(warning)}")
    else:
        lines.append("- 无校验警告")
    lines.extend(
        [
            "- 本报告不做公式求值，只解析 `#ParamName` 形式的字符串引用。",
            "- 如果未来出现直接引用子实例命名空间的公式，需要扩展引用解析规则。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze combo-to-unit parameter relations.")
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT), help=f"Cases root (default: {DEFAULT_CASES_ROOT})")
    parser.add_argument("--unit-root", default=str(DEFAULT_UNIT_ROOT), help=f"Unit root (default: {DEFAULT_UNIT_ROOT})")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help=f"Manifest path (default: {DEFAULT_MANIFEST})")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help=f"Output JSON path (default: {DEFAULT_OUTPUT})")
    parser.add_argument("--md-output", default=str(DEFAULT_MD_OUTPUT), help=f"Output Markdown path (default: {DEFAULT_MD_OUTPUT})")
    parser.add_argument("--case", action="append", default=[], help="Analyze only this combo BGID; can be repeated")
    parser.add_argument("--limit", type=int, help="Limit number of cases after discovery")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero on validation warnings")
    return parser.parse_args()


def main() -> int:
    configure_output_encoding()
    args = parse_args()
    result = analyze(
        Path(args.cases_root).resolve(),
        Path(args.unit_root).resolve(),
        Path(args.manifest).resolve(),
        args.case,
        args.limit,
    )
    output_path = Path(args.output).resolve()
    md_output_path = Path(args.md_output).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    md_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_output_path.write_text(render_markdown(result), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "success",
                "output": str(output_path),
                "mdOutput": str(md_output_path),
                "totalCases": result["totalCases"],
                "totalInstances": result["totalInstances"],
                "formulaEdges": result["totalFormulaEdges"],
                "bindingEdges": result["totalBindingEdges"],
                "templateRules": len(result["templateRules"]),
                "warningCount": len(result["warnings"]),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if args.strict and result["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
