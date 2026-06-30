"""Validate abd.json layout cells against position/size."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

EPSILON = 1e-5
WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ABD_FILE = WORKSPACE_ROOT / "tmp" / "input" / "abd.json"


@dataclass
class ValidationMessage:
    code: str
    path: str
    message: str
    hint: str = ""

    def to_dict(self) -> dict[str, str]:
        data = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.hint:
            data["hint"] = self.hint
        return data


@dataclass
class BBox:
    x0: float
    x1: float
    z0: float
    z1: float
    depth: float
    depth_offset: float


@dataclass
class OccupiedCells:
    cells: list[tuple[int, int]]
    row_start: int
    row_end: int
    column_start: int
    column_end: int


def load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def read_vector(unit: dict[str, Any], field_name: str, unit_index: int, errors: list[ValidationMessage]) -> dict[str, float] | None:
    vector = unit.get(field_name)
    path = f"units[{unit_index}].{field_name}"
    if not isinstance(vector, dict):
        errors.append(ValidationMessage(
            "missing_vector",
            path,
            f"{path} 必填，且必须是包含 x/y/z 的对象。",
            "重新生成该 unit 的 position 和 size，格式示例：{'x': 0, 'y': 0, 'z': 0}。",
        ))
        return None
    out: dict[str, float] = {}
    for axis in ("x", "y", "z"):
        value = as_number(vector.get(axis))
        if value is None:
            errors.append(ValidationMessage(
                "invalid_vector_axis",
                f"{path}.{axis}",
                f"{path}.{axis} 必须是数值。",
                "重新生成时确保 position/size 的 x、y、z 都是数字。",
            ))
        else:
            out[axis] = value
    return out if len(out) == 3 else None


def unit_to_bbox(unit: dict[str, Any], unit_index: int, errors: list[ValidationMessage]) -> BBox | None:
    position = read_vector(unit, "position", unit_index, errors)
    size = read_vector(unit, "size", unit_index, errors)
    if position is None or size is None:
        return None
    for axis in ("x", "y", "z"):
        if size[axis] <= 0:
            errors.append(ValidationMessage(
                "invalid_size",
                f"units[{unit_index}].size.{axis}",
                f"units[{unit_index}].size.{axis} 必须 > 0。",
                "重新生成时确保每个 unit 的尺寸都是正数。",
            ))
    if any(size[axis] <= 0 for axis in ("x", "y", "z")):
        return None
    return BBox(
        x0=position["x"],
        x1=position["x"] + size["x"],
        z0=position["z"],
        z1=position["z"] + size["z"],
        depth=size["y"],
        depth_offset=position["y"],
    )


def parse_cell(cell: Any, unit_index: int, cell_index: int, errors: list[ValidationMessage]) -> tuple[int, int] | None:
    row_value = None
    column_value = None
    if isinstance(cell, dict):
        row_value = cell.get("row", cell.get("r"))
        column_value = cell.get("column", cell.get("col", cell.get("c")))
    elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
        row_value = cell[0]
        column_value = cell[1]
    row = as_number(row_value)
    column = as_number(column_value)
    if row is None or column is None or int(row) != row or int(column) != column or row < 1 or column < 1:
        errors.append(ValidationMessage(
            "invalid_cell",
            f"units[{unit_index}].cells[{cell_index}]",
            f"units[{unit_index}].cells[{cell_index}] 必须包含从 1 开始的整数 row 与 column。",
            "重新生成 cells 时使用 {'row': 1, 'column': 1} 这类对象，row/column 从 1 开始。",
        ))
        return None
    return int(row), int(column)


def normalize_occupied_cells(unit: dict[str, Any], unit_index: int, errors: list[ValidationMessage]) -> OccupiedCells | None:
    source_cells = unit.get("cells")
    if not isinstance(source_cells, list) or not source_cells:
        errors.append(ValidationMessage(
            "missing_cells",
            f"units[{unit_index}].cells",
            f"units[{unit_index}].cells 必填，且必须是非空数组。",
            "每个 unit 必须声明其占用的表格格子，例如 [{'row': 1, 'column': 1}]。",
        ))
        return None
    parsed = [parse_cell(cell, unit_index, idx, errors) for idx, cell in enumerate(source_cells)]
    if any(cell is None for cell in parsed):
        return None
    cells = [cell for cell in parsed if cell is not None]
    unique = set(cells)
    if len(unique) != len(cells):
        errors.append(ValidationMessage(
            "duplicate_cells",
            f"units[{unit_index}].cells",
            f"units[{unit_index}].cells 不能包含重复格子。",
            "删除重复的 row/column，或重新生成该 unit 的 cells。",
        ))
        return None
    rows = [row for row, _ in cells]
    columns = [column for _, column in cells]
    row_start = min(rows)
    row_end = max(rows)
    column_start = min(columns)
    column_end = max(columns)
    expected_count = (row_end - row_start + 1) * (column_end - column_start + 1)
    if expected_count != len(cells):
        errors.append(ValidationMessage(
            "non_rectangular_cells",
            f"units[{unit_index}].cells",
            f"units[{unit_index}].cells 必须组成连续矩形。",
            "如果一个 unit 横跨多行/多列，必须列出矩形范围内的所有格子，不能跳格。",
        ))
        return None
    for row in range(row_start, row_end + 1):
        for column in range(column_start, column_end + 1):
            if (row, column) not in unique:
                errors.append(ValidationMessage(
                    "non_rectangular_cells",
                    f"units[{unit_index}].cells",
                    f"units[{unit_index}].cells 缺少 row={row}, column={column}，无法组成连续矩形。",
                    "补齐矩形内缺失格子，或拆成多个 unit。",
                ))
                return None
    return OccupiedCells(cells, row_start, row_end, column_start, column_end)


def extract_cabinet_size(data: dict[str, Any], units: list[dict[str, Any]], boxes: list[BBox], errors: list[ValidationMessage]) -> dict[str, float] | None:
    for key in ("cabinetSize", "cabinetDimensions", "wardrobeSize", "outerSize", "cabinet"):
        candidate = data.get(key)
        if not isinstance(candidate, dict):
            continue
        width = as_number(candidate.get("width", candidate.get("w", candidate.get("W", candidate.get("x")))))
        height = as_number(candidate.get("height", candidate.get("h", candidate.get("H", candidate.get("z")))))
        if width is not None and width > 0 and height is not None and height > 0:
            return {"width": width, "height": height}
    if boxes and len(boxes) == len(units):
        return {
            "width": max(box.x1 for box in boxes) - min(box.x0 for box in boxes),
            "height": max(box.z1 for box in boxes) - min(box.z0 for box in boxes),
        }
    errors.append(ValidationMessage(
        "invalid_cabinet_size",
        "cabinetSize",
        "cabinetSize 必填，且 width/height 必须是大于 0 的数值。",
        "重新生成根节点 cabinetSize，例如 {'width': 4200, 'depth': 500, 'height': 3000}。",
    ))
    return None


def close_enough(a: float, b: float) -> bool:
    return abs(a - b) <= EPSILON


def fmt(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def validate_abd(data: Any) -> list[ValidationMessage]:
    errors: list[ValidationMessage] = []
    if not isinstance(data, dict):
        return [ValidationMessage("invalid_root", "$", "输入必须是 JSON object。", "重新生成完整 abd.json 对象。")]
    raw_units = data.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        return [ValidationMessage("invalid_units", "units", "units 必填，且必须是非空一维对象数组。", "重新生成 units 数组。")]
    if not all(isinstance(unit, dict) and not isinstance(unit, list) for unit in raw_units):
        return [ValidationMessage("invalid_units", "units", "units 必须是一维对象数组，不能包含嵌套数组或非对象。", "将每个单元柜作为 units 中的一个对象。")]
    units: list[dict[str, Any]] = raw_units

    boxes: list[BBox | None] = [unit_to_bbox(unit, idx, errors) for idx, unit in enumerate(units)]
    occupied_list: list[OccupiedCells | None] = [normalize_occupied_cells(unit, idx, errors) for idx, unit in enumerate(units)]
    valid_boxes = [box for box in boxes if box is not None]
    cabinet_size = extract_cabinet_size(data, units, valid_boxes, errors)
    if errors:
        return errors
    if cabinet_size is None:
        return errors

    boxes = [box for box in boxes if box is not None]
    occupied_list = [occupied for occupied in occupied_list if occupied is not None]
    origin_x = min(box.x0 for box in boxes)
    origin_z = min(box.z0 for box in boxes)
    cabinet_width = cabinet_size["width"]
    cabinet_height = cabinet_size["height"]

    occupied_by: dict[tuple[int, int], int] = {}
    for unit_index, occupied in enumerate(occupied_list):
        for cell in occupied.cells:
            if cell in occupied_by:
                errors.append(ValidationMessage(
                    "overlap_cells",
                    f"units[{unit_index}].cells",
                    f"units[{unit_index}].cells 与 units[{occupied_by[cell]}].cells 在 row={cell[0]}, column={cell[1]} 重叠。",
                    "重新生成 cells，确保每个表格格子只被一个 unit 占用。",
                ))
            occupied_by[cell] = unit_index

    for unit_index, box in enumerate(boxes):
        if (
            box.x0 < origin_x - EPSILON
            or box.z0 < origin_z - EPSILON
            or box.x1 > origin_x + cabinet_width + EPSILON
            or box.z1 > origin_z + cabinet_height + EPSILON
        ):
            errors.append(ValidationMessage(
                "bbox_out_of_cabinet",
                f"units[{unit_index}].position/size",
                f"units[{unit_index}] 的 position/size 超出 cabinetSize 范围。",
                f"当前柜体范围 x=[{fmt(origin_x)}, {fmt(origin_x + cabinet_width)}], z=[{fmt(origin_z)}, {fmt(origin_z + cabinet_height)}]；请调整该 unit 的 position/size 或 cabinetSize。",
            ))
    if errors:
        return errors

    max_row = max(occupied.row_end for occupied in occupied_list)
    max_column = max(occupied.column_end for occupied in occupied_list)
    column_edges: dict[int, list[tuple[int, str, float]]] = {0: [(-1, "柜体左边界", 0.0)], max_column: [(-1, "柜体右边界", 1.0)]}
    row_edges: dict[int, list[tuple[int, str, float]]] = {0: [(-1, "柜体下边界", 0.0)], max_row: [(-1, "柜体上边界", 1.0)]}

    for unit_index, (box, occupied) in enumerate(zip(boxes, occupied_list, strict=True)):
        x_start = (box.x0 - origin_x) / cabinet_width
        x_end = (box.x1 - origin_x) / cabinet_width
        z_start = (box.z0 - origin_z) / cabinet_height
        z_end = (box.z1 - origin_z) / cabinet_height
        column_edges.setdefault(occupied.column_start - 1, []).append((unit_index, f"column {occupied.column_start} 左边界", x_start))
        column_edges.setdefault(occupied.column_end, []).append((unit_index, f"column {occupied.column_end} 右边界", x_end))
        row_edges.setdefault(occupied.row_start - 1, []).append((unit_index, f"row {occupied.row_start} 下边界", z_start))
        row_edges.setdefault(occupied.row_end, []).append((unit_index, f"row {occupied.row_end} 上边界", z_end))

    errors.extend(validate_edge_groups(column_edges, "列", origin_x, cabinet_width))
    errors.extend(validate_edge_groups(row_edges, "行", origin_z, cabinet_height))
    return errors


def validate_edge_groups(
    edge_groups: dict[int, list[tuple[int, str, float]]],
    axis_name: str,
    origin: float,
    size: float,
) -> list[ValidationMessage]:
    errors: list[ValidationMessage] = []
    for edge_index, records in sorted(edge_groups.items()):
        if len(records) < 2:
            continue
        expected_unit, expected_label, expected = records[0]
        for unit_index, label, actual in records[1:]:
            if close_enough(expected, actual):
                continue
            expected_path = "cabinetSize" if expected_unit < 0 else f"units[{expected_unit}].position/size"
            actual_path = f"units[{unit_index}].cells + units[{unit_index}].position/size" if unit_index >= 0 else "cabinetSize"
            absolute_expected = origin + expected * size
            absolute_actual = origin + actual * size
            errors.append(ValidationMessage(
                "cells_bbox_mismatch",
                actual_path,
                f"第 {edge_index} 条{axis_name}边界不一致：{expected_label} 来自 {expected_path}，归一化坐标为 {fmt(expected)}；{label} 归一化坐标为 {fmt(actual)}。",
                f"该共享{axis_name}边界的绝对坐标应统一为 {fmt(absolute_expected)}，但当前为 {fmt(absolute_actual)}；重新生成时让相邻 unit 在同一条{axis_name}边界上对齐，或调整 cells 的 row/column 跨度。",
            ))
    return errors


def format_text(errors: list[ValidationMessage]) -> str:
    if not errors:
        return "ABD layout is valid: cells match position/size."
    lines = [f"ABD layout is invalid: {len(errors)} error(s)."]
    for index, error in enumerate(errors, 1):
        lines.append(f"{index}. [{error.code}] {error.path}: {error.message}")
        if error.hint:
            lines.append(f"   Hint: {error.hint}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate abd.json cells against position/size layout.")
    parser.add_argument("abd_file", nargs="?", default=str(DEFAULT_ABD_FILE), help="Path to abd.json; defaults to tmp/input/abd.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON result")
    args = parser.parse_args()

    path = Path(args.abd_file)
    if not path.is_absolute():
        path = WORKSPACE_ROOT / path
    try:
        data = load_json(path)
        errors = validate_abd(data)
    except FileNotFoundError:
        errors = [ValidationMessage("file_not_found", str(path), f"文件不存在：{path}", "请传入正确的 abd.json 路径。")]
    except json.JSONDecodeError as exc:
        errors = [ValidationMessage("invalid_json", str(path), f"JSON 解析失败：line {exc.lineno}, column {exc.colno}: {exc.msg}", "修复 JSON 语法后再重新校验。")]

    if args.json:
        print(json.dumps({"valid": not errors, "errors": [error.to_dict() for error in errors]}, ensure_ascii=False, indent=2))
    else:
        print(format_text(errors))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
