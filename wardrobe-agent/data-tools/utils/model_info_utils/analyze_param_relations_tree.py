#!/usr/bin/env python3
"""Render combo-to-unit parameter relations as a tree markdown report."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from analyze_param_relations import (
    DEFAULT_CASES_ROOT,
    DEFAULT_MANIFEST,
    DEFAULT_UNIT_ROOT,
    analyze,
    configure_output_encoding,
    md_escape,
)

DEFAULT_MD_OUTPUT = Path(__file__).resolve().parents[2] / "temp" / "paramRelation_tree.md"


def sort_slot(value: str | None) -> tuple[int, str]:
    if not value:
        return (10_000, "")
    if value.startswith("A") and value[1:].isdigit():
        return (int(value[1:]), value)
    return (10_000, value)


def group_by(items: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[str(item.get(key) or "")].append(item)
    return grouped


def append_tree_line(lines: list[str], depth: int, text: str) -> None:
    lines.append(f"{'  ' * depth}- {text}")


def render_template_rule_tree(lines: list[str], rules: list[dict[str, Any]]) -> None:
    lines.extend(["## 可复用模板规则树", ""])
    if not rules:
        lines.extend(["- 无", ""])
        return

    for index, rule in enumerate(rules[:80], start=1):
        append_tree_line(lines, 0, f"规则 {index}: `{md_escape(rule.get('sourceParamLabel', rule['sourceParam']))}`")
        append_tree_line(lines, 1, f"出现频次：{rule['frequency']} 个 case")
        append_tree_line(lines, 1, f"公式：`{md_escape(rule.get('sourceParamLabel', rule['sourceParam']))} = {md_escape(rule['expression'])}`")
        append_tree_line(lines, 1, f"依赖参数：{md_escape(', '.join(rule.get('dependsOnComboParamLabels', rule['dependsOnComboParams'])))}")
        append_tree_line(lines, 1, f"出现 case：{md_escape(', '.join(rule['cases']))}")
        append_tree_line(lines, 1, "槽位绑定")
        for binding in sorted(rule["slotBindings"], key=lambda item: (sort_slot(item.get("slot")), item.get("comboParam", ""), item.get("targetUnitParam", ""))):
            append_tree_line(
                lines,
                2,
                f"{md_escape(binding.get('comboParamLabel', binding['comboParam']))} -> slot {md_escape(binding.get('slot') or '—')} -> unit.{md_escape(binding.get('targetUnitParamLabel', binding['targetUnitParam']))}",
            )
        lines.append("")


def render_case_tree(lines: list[str], case: dict[str, Any]) -> None:
    lines.extend([f"### {md_escape(case['case'])} — {md_escape(case['comboName'])}", ""])
    append_tree_line(
        lines,
        0,
        f"统计：单元柜实例 {case['instanceCount']}；公式依赖边 {case['formulaEdgeCount']}；绑定边 {case['bindingEdgeCount']}；可追踪路径 {case['pathCount']}",
    )

    lines.append("")
    append_tree_line(lines, 0, "单元柜实例")
    for instance in case["instances"]:
        append_tree_line(
            lines,
            1,
            f"instance[{instance['instanceIndex']}] {md_escape(instance['name'])} — {md_escape(instance['unitBgid'])} / {md_escape(instance['unitName'])}",
        )

    lines.append("")
    append_tree_line(lines, 0, "参数关系树：组合柜公式参数 -> 依赖参数 -> 单元柜实例参数")
    formula_edges_by_from = group_by(case["formulaEdges"], "from")
    bindings_by_combo_param = group_by(case["bindingEdges"], "fromComboParam")

    if not formula_edges_by_from:
        append_tree_line(lines, 1, "无公式依赖")
    for source_param, edges in sorted(formula_edges_by_from.items()):
        first_edge = edges[0]
        append_tree_line(lines, 1, f"{md_escape(first_edge.get('fromLabel', source_param))}")
        append_tree_line(lines, 2, f"公式：`{md_escape(first_edge['expression'])}`")
        seen_refs: set[str] = set()
        for edge in edges:
            ref = edge["to"]
            if ref in seen_refs:
                continue
            seen_refs.add(ref)
            ref_bindings = sorted(
                bindings_by_combo_param.get(ref, []),
                key=lambda item: (sort_slot(item.get("slot")), item.get("instanceIndex", 0), item.get("toInstanceParam", "")),
            )
            append_tree_line(lines, 2, f"依赖 {md_escape(edge.get('toLabel', ref))}")
            if not ref_bindings:
                append_tree_line(lines, 3, "未发现直接绑定到单元柜实例参数")
                continue
            for binding in ref_bindings[:20]:
                append_tree_line(
                    lines,
                    3,
                    f"slot {md_escape(binding.get('slot') or '—')} -> instance[{binding['instanceIndex']}] {md_escape(binding['instanceName'])} / {md_escape(binding['unitBgid'])} -> {md_escape(binding.get('targetLabel', binding['toInstanceParam']))} = `{md_escape(binding['expression'])}`",
                )
            if len(ref_bindings) > 20:
                append_tree_line(lines, 3, f"还有 {len(ref_bindings) - 20} 条绑定未展开")

    lines.append("")
    append_tree_line(lines, 0, "槽位视角：槽位 -> 组合柜参数 -> 单元柜实例参数")
    slot_bindings: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for binding in case["bindingEdges"]:
        if binding.get("slot"):
            slot_bindings[str(binding["slot"])].append(binding)
    if not slot_bindings:
        append_tree_line(lines, 1, "无槽位绑定")
    for slot, bindings in sorted(slot_bindings.items(), key=lambda item: sort_slot(item[0])):
        append_tree_line(lines, 1, f"slot {md_escape(slot)}")
        bindings_by_param = group_by(bindings, "fromComboParam")
        for combo_param, param_bindings in sorted(bindings_by_param.items()):
            first_binding = param_bindings[0]
            append_tree_line(lines, 2, md_escape(first_binding.get("fromComboParamLabel", combo_param)))
            for binding in sorted(param_bindings, key=lambda item: (item.get("instanceIndex", 0), item.get("toInstanceParam", "")))[:30]:
                append_tree_line(
                    lines,
                    3,
                    f"instance[{binding['instanceIndex']}] {md_escape(binding['instanceName'])} / {md_escape(binding['unitBgid'])} -> {md_escape(binding.get('targetLabel', binding['toInstanceParam']))}",
                )
            if len(param_bindings) > 30:
                append_tree_line(lines, 3, f"还有 {len(param_bindings) - 30} 条绑定未展开")
    lines.append("")


def render_markdown_tree(result: dict[str, Any]) -> str:
    lines = [
        "# 组合柜与单元柜参数关系树状报告",
        "",
        f"> 数据来源：`{result['casesRoot']}`、`{result['unitRoot']}`、`{result['manifest']}`。",
        "> 关系解释：树状结构按“组合柜公式参数 -> 依赖参数 -> 单元柜实例参数”和“槽位 -> 组合柜参数 -> 单元柜实例参数”两种视角展开。",
        f"> 样本数：{result['totalCases']}；单元柜实例数：{result['totalInstances']}；公式依赖边：{result['totalFormulaEdges']}；绑定边：{result['totalBindingEdges']}；可追踪路径：{result['totalPaths']}；模板规则：{len(result['templateRules'])}；警告：{len(result['warnings'])}。",
        "",
        "## 阅读方式",
        "",
        "- 第一层是组合柜中的公式参数或槽位。",
        "- 第二层是公式依赖到的组合柜参数，或槽位下的具体组合柜参数。",
        "- 第三层是这些参数实际绑定到的单元柜实例参数。",
        "- 报告只展示引用关系，不对公式求值。",
        "",
    ]
    render_template_rule_tree(lines, result["templateRules"])
    lines.extend(["## 按组合柜展开", ""])
    for case in result["cases"]:
        render_case_tree(lines, case)

    lines.extend(["---", "", "## 数据校验与限制", ""])
    if result["warnings"]:
        for warning in result["warnings"]:
            lines.append(f"- {md_escape(warning)}")
    else:
        lines.append("- 无校验警告")
    lines.extend(
        [
            "- 本报告不修改 `analyze_param_relations.py`，只复用其分析结果并生成树状 Markdown。",
            "- 为避免单个 case 过长，部分绑定节点设置了展开数量上限。",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Render combo-to-unit parameter relations as a tree markdown report.")
    parser.add_argument("--cases-root", default=str(DEFAULT_CASES_ROOT), help=f"Cases root (default: {DEFAULT_CASES_ROOT})")
    parser.add_argument("--unit-root", default=str(DEFAULT_UNIT_ROOT), help=f"Unit root (default: {DEFAULT_UNIT_ROOT})")
    parser.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help=f"Manifest path (default: {DEFAULT_MANIFEST})")
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
    md_output_path = Path(args.md_output).resolve()
    md_output_path.parent.mkdir(parents=True, exist_ok=True)
    md_output_path.write_text(render_markdown_tree(result), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "success",
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
