"""
Compare bbox info between MCP get_scene_info result and abd.json.

Calls the parameditor MCP server's get_scene_info tool, converts the
returned min/max bbox into position/size representation, then compares
against abd.json entries matched by obsBrandGoodId. When the same
obsBrandGoodId appears multiple times, pairs are matched by order of
appearance in abd.json and scene_info respectively.

Position and size differences within 20 mm are ignored when deciding
identical vs different.

Usage:
    python compare_scene_bbox.py --abd tmp/input/abd.json
    python compare_scene_bbox.py --abd tmp/input/abd.json --parameditor-base-url http://localhost:7764
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

import requests


def _parse_sse_json(text: str) -> dict[str, Any]:
    """Extract the JSON-RPC response from an SSE / httpStream body.

    The body may contain multiple ``data: ...`` lines (e.g. an initial
    endpoint event followed by the actual JSON-RPC message).  We iterate
    through all of them and return the first one that is a valid JSON
    object with either ``result`` or ``error`` (i.e. a JSON-RPC response).
    """
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("data:"):
            continue
        payload = stripped[len("data:"):].strip()
        if not payload.startswith("{"):
            continue
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict) and ("result" in obj or "error" in obj or "jsonrpc" in obj):
                return obj
        except json.JSONDecodeError:
            continue
    return {}


def _jsonrpc(
    session: requests.Session,
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str],
) -> tuple[dict[str, Any], requests.Response]:
    resp = session.post(url, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    raw_text = resp.content.decode("utf-8", errors="replace")
    if not raw_text.strip():
        return {}, resp
    if raw_text.lstrip().startswith("{"):
        return json.loads(raw_text), resp
    parsed = _parse_sse_json(raw_text)
    if not parsed:
        raise RuntimeError(
            f"Failed to parse SSE response. Raw response (first 500 chars):\n"
            f"{raw_text[:500]}"
        )
    return parsed, resp


def call_get_scene_info(base_url: str) -> dict[str, Any]:
    """Call MCP get_scene_info via JSON-RPC over SSE."""
    url = f"{base_url}/sse"
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }
    session = requests.Session()

    init_res, init_http = _jsonrpc(
        session, url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "compare-scene-bbox", "version": "1.0.0"},
            },
        },
        headers,
    )
    if "error" in init_res:
        raise RuntimeError(f"initialize failed: {init_res['error']}")

    session_id = init_http.headers.get("mcp-session-id")
    if session_id:
        headers = dict(headers)
        headers["mcp-session-id"] = session_id

    _jsonrpc(
        session, url,
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        headers,
    )

    out, _ = _jsonrpc(
        session, url,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_scene_info", "arguments": {}},
        },
        headers,
    )
    if "error" in out:
        raise RuntimeError(f"tools/call get_scene_info failed: {out['error']}")

    return _extract_scene_info(out)


def _extract_scene_info(out: dict[str, Any]) -> dict[str, Any]:
    """Walk the JSON-RPC response and pull out the scene info dict.

    Handles two known shapes:
      1. Standard MCP: result.content[0].text  (may be multi-layer stringified)
      2. Direct dict:  result itself contains modelInstances
    """
    result = out.get("result", out)

    if isinstance(result, dict) and "modelInstances" in result:
        return result

    content = result.get("content", []) if isinstance(result, dict) else []
    if content:
        text = content[0].get("text", "") if isinstance(content[0], dict) else str(content[0])
    else:
        text = json.dumps(result) if isinstance(result, dict) else str(result)

    print(f"[debug] raw text (first 500): {text[:500]}", file=sys.stderr)

    parsed: Any = text
    for _ in range(5):
        if not isinstance(parsed, str) or not parsed.strip():
            break
        try:
            parsed = json.loads(parsed)
        except json.JSONDecodeError:
            # The string may have a human-readable prefix like "Scene info: {...}"
            if isinstance(parsed, str):
                brace = parsed.find("{")
                if brace >= 0:
                    try:
                        parsed = json.loads(parsed[brace:])
                    except json.JSONDecodeError:
                        pass
            break

    if isinstance(parsed, dict) and "modelInstances" in parsed:
        return parsed
    if isinstance(parsed, dict):
        return parsed

    raise ValueError(
        f"get_scene_info: cannot extract modelInstances. "
        f"Parsed type={type(parsed).__name__}, preview: {str(parsed)[:500]}"
    )


def minmax_to_position_size(bbox: dict) -> tuple[dict, dict]:
    """Convert {min: {x,y,z}, max: {x,y,z}} to (position, size).

    position = min corner (左后下点), consistent with abd.json convention.
    size = max - min.
    """
    mn, mx = bbox["min"], bbox["max"]
    position = {
        "x": mn["x"],
        "y": mn["y"],
        "z": mn["z"],
    }
    size = {
        "x": mx["x"] - mn["x"],
        "y": mx["y"] - mn["y"],
        "z": mx["z"] - mn["z"],
    }
    return position, size


def _unit_has_positive_size(unit: dict[str, Any]) -> bool:
    size = unit.get("size") or {}
    return all(float(size.get(axis, 0)) > 0 for axis in ("x", "y", "z"))


def _vec3_float(
    value: dict[str, Any] | None,
    *,
    default: float = 0.0,
) -> dict[str, float]:
    if not isinstance(value, dict):
        return {"x": default, "y": default, "z": default}
    return {
        axis: float(value.get(axis, default)) for axis in ("x", "y", "z")
    }


def _rotate_to_degrees(rotate: dict[str, Any] | None) -> tuple[float, float, float]:
    """Resolve abd rotate to degrees (template: degrees; assembly export may use radians)."""
    rot = _vec3_float(rotate)
    values = [rot["x"], rot["y"], rot["z"]]
    if any(abs(v) > 2 * math.pi for v in values):
        return rot["x"], rot["y"], rot["z"]
    return tuple(math.degrees(v) for v in values)


def _is_negligible_rotation(rotate: dict[str, Any] | None) -> bool:
    if not isinstance(rotate, dict):
        return True
    rx, ry, rz = _rotate_to_degrees(rotate)
    return all(abs(angle) < 1e-6 for angle in (rx, ry, rz))


def _rotation_matrix_xyz_deg(
    rx_deg: float,
    ry_deg: float,
    rz_deg: float,
) -> tuple[tuple[float, float, float], ...]:
    """Intrinsic XYZ Euler rotation matrix (column vectors), matching PMBuilder convention."""
    rx, ry, rz = map(math.radians, (rx_deg, ry_deg, rz_deg))
    cx, sx = math.cos(rx), math.sin(rx)
    cy, sy = math.cos(ry), math.sin(ry)
    cz, sz = math.cos(rz), math.sin(rz)

    # R = Rz * Ry * Rx
    return (
        (cy * cz, -cy * sz, sy),
        (sx * sy * cz + cx * sz, -sx * sy * sz + cx * cz, -sx * cy),
        (-cx * sy * cz + sx * sz, cx * sy * sz + sx * cz, cx * cy),
    )


def _mat_vec_mul(
    matrix: tuple[tuple[float, float, float], ...],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = vector
    return (
        matrix[0][0] * x + matrix[0][1] * y + matrix[0][2] * z,
        matrix[1][0] * x + matrix[1][1] * y + matrix[1][2] * z,
        matrix[2][0] * x + matrix[2][1] * y + matrix[2][2] * z,
    )


def _local_box_corner_offsets(
    size: dict[str, float],
    scale: dict[str, float],
) -> list[tuple[float, float, float]]:
    """Eight corners relative to abd origin (左后下 pivot).

    X/Z grow in +X/+Z; depth grows toward -Y (position.y is the front face).
    """
    sx = size["x"] * scale["x"]
    sy = size["y"] * scale["y"]
    sz = size["z"] * scale["z"]
    return [
        (dx * sx, -dy * sy, dz * sz)
        for dx in (0.0, 1.0)
        for dy in (0.0, 1.0)
        for dz in (0.0, 1.0)
    ]


def compute_abd_aabb_in_abd_frame(
    position: dict[str, Any],
    size: dict[str, Any],
    *,
    rotate: dict[str, Any] | None = None,
    scale: dict[str, Any] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Axis-aligned bbox of abd unit in combo-center frame, accounting for rotate/scale."""
    world_corners = _abd_world_corners(
        position, size, rotate=rotate, scale=scale,
    )
    mins = {axis: min(corner[i] for corner in world_corners) for i, axis in enumerate("xyz")}
    maxs = {axis: max(corner[i] for corner in world_corners) for i, axis in enumerate("xyz")}
    aabb_size = {axis: maxs[axis] - mins[axis] for axis in ("x", "y", "z")}
    return mins, aabb_size


def transform_abd_point_to_scene(
    point: dict[str, float],
    transform: dict[str, float],
) -> dict[str, float]:
    """Map an abd-frame point into scene (parent left-back-bottom) coordinates."""
    return {
        "x": point["x"] - transform["origin_x"],
        "y": point["y"] - transform["abd_y_anchor"],
        "z": point["z"] - transform["origin_z"],
    }


def _abd_world_corners(
    position: dict[str, Any],
    size: dict[str, Any],
    *,
    rotate: dict[str, Any] | None = None,
    scale: dict[str, Any] | None = None,
) -> list[tuple[float, float, float]]:
    pos = _vec3_float(position)
    offsets = _local_box_corner_offsets(
        _vec3_float(size),
        _vec3_float(scale, default=1.0),
    )
    if _is_negligible_rotation(rotate):
        return [
            (pos["x"] + ox, pos["y"] + oy, pos["z"] + oz)
            for ox, oy, oz in offsets
        ]

    rx, ry, rz = _rotate_to_degrees(rotate)
    rot_mat = _rotation_matrix_xyz_deg(rx, ry, rz)
    return [
        (
            pos["x"] + rotated[0],
            pos["y"] + rotated[1],
            pos["z"] + rotated[2],
        )
        for rotated in (_mat_vec_mul(rot_mat, offset) for offset in offsets)
    ]


def compute_abd_bbox_in_scene_frame(
    abd_pos: dict[str, Any],
    abd_size: dict[str, Any],
    transform: dict[str, float],
    *,
    rotate: dict[str, Any] | None = None,
    scale: dict[str, Any] | None = None,
) -> tuple[dict[str, float], dict[str, float]]:
    """Compute abd bbox in scene frame, including rotate/scale when present."""
    if _is_negligible_rotation(rotate) and _vec3_float(scale, default=1.0) == {
        "x": 1.0, "y": 1.0, "z": 1.0,
    }:
        return transform_abd_to_scene(abd_pos, abd_size, transform)

    scene_corners = [
        transform_abd_point_to_scene(
            {"x": cx, "y": cy, "z": cz},
            transform,
        )
        for cx, cy, cz in _abd_world_corners(
            abd_pos, abd_size, rotate=rotate, scale=scale,
        )
    ]
    scene_min = {
        axis: min(corner[axis] for corner in scene_corners)
        for axis in ("x", "y", "z")
    }
    scene_max = {
        axis: max(corner[axis] for corner in scene_corners)
        for axis in ("x", "y", "z")
    }
    scene_size = {
        axis: scene_max[axis] - scene_min[axis] for axis in ("x", "y", "z")
    }
    return scene_min, scene_size


def compute_abd_to_scene_transform(
    abd_units: list[dict[str, Any]],
) -> dict[str, float]:
    """Derive abd(center-origin) → scene(parent left-back-bottom) translation.

    abd.json uses the combo center as origin; PMBuilder scene bbox uses the
    parent's left-back-bottom (min corner, Y into negative depth).

    X/Z: shift by the left/back/bottom edges of all sized units.
    Y: scene_min_y = abd_y - size_y - abd_y_anchor (abd_y is a depth anchor).
    """
    valid = [u for u in abd_units if _unit_has_positive_size(u)]
    if not valid:
        raise ValueError("abd.json has no units with positive size for origin inference")

    origin_x = min(
        compute_abd_aabb_in_abd_frame(
            u["position"], u["size"],
            rotate=u.get("rotate"), scale=u.get("scale"),
        )[0]["x"]
        for u in valid
    )
    origin_z = min(
        compute_abd_aabb_in_abd_frame(
            u["position"], u["size"],
            rotate=u.get("rotate"), scale=u.get("scale"),
        )[0]["z"]
        for u in valid
    )

    y_values = [float(u["position"]["y"]) for u in valid]
    abd_y_anchor = max(set(y_values), key=y_values.count)

    return {
        "origin_x": origin_x,
        "origin_z": origin_z,
        "abd_y_anchor": abd_y_anchor,
    }


def transform_abd_to_scene(
    abd_pos: dict[str, Any],
    abd_size: dict[str, Any],
    transform: dict[str, float],
) -> tuple[dict[str, float], dict[str, float]]:
    """Map abd position/size into the same frame as get_scene_info bbox."""
    pos = {
        "x": float(abd_pos["x"]) - transform["origin_x"],
        "y": float(abd_pos["y"]) - float(abd_size["y"]) - transform["abd_y_anchor"],
        "z": float(abd_pos["z"]) - transform["origin_z"],
    }
    size = {axis: float(abd_size[axis]) for axis in ("x", "y", "z")}
    return pos, size


_ROUND_DIGITS = 4
_BBOX_COMPARE_TOLERANCE_MM = 20


def _is_significant_diff(diff: float) -> bool:
    """Return True if *diff* exceeds the bbox compare tolerance."""
    return abs(diff) > _BBOX_COMPARE_TOLERANCE_MM


def _vec_equivalent(a: dict, b: dict) -> bool:
    return all(
        not _is_significant_diff(a[ax] - b[ax]) for ax in ("x", "y", "z")
    )


def _group_by_id_preserve_order(
    items: list[dict[str, Any]],
    id_field: str,
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        bgid = item[id_field]
        groups.setdefault(bgid, []).append(item)
    return groups


def _ordered_union_ids(
    abd_units: list[dict[str, Any]],
    scene_instances: list[dict[str, Any]],
) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in abd_units:
        bgid = item["obsBrandGoodId"]
        if bgid not in seen:
            seen.add(bgid)
            ordered.append(bgid)
    for item in scene_instances:
        bgid = item["obsBrandGoodId"]
        if bgid not in seen:
            seen.add(bgid)
            ordered.append(bgid)
    return ordered


def _compare_one_pair(
    bgid: str,
    abd_unit: dict[str, Any],
    scene_inst: dict[str, Any],
    *,
    match_index: int,
    abd_transform: dict[str, float],
) -> dict[str, Any]:
    scene_pos, scene_size = minmax_to_position_size(scene_inst["bbox"])
    abd_pos_raw = abd_unit["position"]
    abd_size_raw = abd_unit["size"]
    abd_rotate_raw = abd_unit.get("rotate")
    abd_scale_raw = abd_unit.get("scale")
    abd_pos, abd_size = compute_abd_bbox_in_scene_frame(
        abd_pos_raw,
        abd_size_raw,
        abd_transform,
        rotate=abd_rotate_raw,
        scale=abd_scale_raw,
    )

    pos_diff = {
        axis: round(scene_pos[axis] - abd_pos[axis], _ROUND_DIGITS)
        for axis in ("x", "y", "z")
    }
    size_diff = {
        axis: round(scene_size[axis] - abd_size[axis], _ROUND_DIGITS)
        for axis in ("x", "y", "z")
    }

    return {
        "obsBrandGoodId": bgid,
        "matchIndex": match_index,
        "name": scene_inst.get("name", abd_unit.get("name", "")),
        "scene_bbox": {"position": scene_pos, "size": scene_size},
        "abd_bbox": {"position": abd_pos, "size": abd_size},
        "abd_bbox_raw": {
            "position": dict(abd_pos_raw),
            "size": dict(abd_size_raw),
            "rotate": dict(abd_rotate_raw) if isinstance(abd_rotate_raw, dict) else None,
            "scale": dict(abd_scale_raw) if isinstance(abd_scale_raw, dict) else None,
        },
        "pos_diff": pos_diff,
        "size_diff": size_diff,
    }


def compare_bbox(
    scene_info: dict[str, Any],
    abd_data: dict[str, Any],
) -> list[dict[str, Any]]:
    """Compare bbox per obsBrandGoodId.

    Duplicate obsBrandGoodId entries are paired by order of appearance in
    abd.json and scene_info (1st with 1st, 2nd with 2nd, ...). Unpaired
    extras are reported as only_in_abd / only_in_scene.

    After per-model comparison, applies a global-offset check:
    if ALL matched models have zero size diff and the SAME position diff,
    the difference is just a coordinate-system translation and every
    model is marked ``identical``.
    """
    abd_units = abd_data.get("units", [])
    scene_instances = scene_info.get("modelInstances", [])

    abd_transform = compute_abd_to_scene_transform(abd_units)

    abd_groups = _group_by_id_preserve_order(abd_units, "obsBrandGoodId")
    scene_groups = _group_by_id_preserve_order(scene_instances, "obsBrandGoodId")
    all_ids = _ordered_union_ids(abd_units, scene_instances)

    matched_entries: list[dict[str, Any]] = []
    unmatched_entries: list[dict[str, Any]] = []

    for bgid in all_ids:
        abd_list = abd_groups.get(bgid, [])
        scene_list = scene_groups.get(bgid, [])
        pair_count = max(len(abd_list), len(scene_list))

        for i in range(pair_count):
            abd_unit = abd_list[i] if i < len(abd_list) else None
            scene_inst = scene_list[i] if i < len(scene_list) else None

            if abd_unit is None:
                unmatched_entries.append({
                    "obsBrandGoodId": bgid,
                    "matchIndex": i,
                    "name": scene_inst["name"] if scene_inst else "",
                    "status": "only_in_scene",
                    "message": "仅存在于 scene_info 中，abd.json 中无对应序号实例",
                })
                continue

            if scene_inst is None:
                unmatched_entries.append({
                    "obsBrandGoodId": bgid,
                    "matchIndex": i,
                    "name": abd_unit.get("name", ""),
                    "status": "only_in_abd",
                    "message": "仅存在于 abd.json 中，scene_info 中无对应序号实例",
                })
                continue

            matched_entries.append(_compare_one_pair(
                bgid, abd_unit, scene_inst, match_index=i,
                abd_transform=abd_transform,
            ))

    # --- global-offset detection ---
    # If every matched model has zero size diff and the same position diff,
    # the offset is just a coordinate-system translation → treat as identical.
    is_global_offset = False
    global_offset: dict[str, float] | None = None

    if matched_entries:
        all_size_zero = all(
            all(
                not _is_significant_diff(e["size_diff"][axis])
                for axis in ("x", "y", "z")
            )
            for e in matched_entries
        )
        if all_size_zero:
            first_pos_diff = matched_entries[0]["pos_diff"]
            all_pos_same = all(
                _vec_equivalent(e["pos_diff"], first_pos_diff)
                for e in matched_entries
            )
            if all_pos_same:
                is_global_offset = True
                global_offset = first_pos_diff

    # --- build final results ---
    results: list[dict[str, Any]] = []
    for e in matched_entries:
        compare_axes = ("x", "y", "z")

        has_size_diff = any(
            _is_significant_diff(e["size_diff"][axis])
            for axis in compare_axes
        )

        if is_global_offset:
            has_real_diff = False
        else:
            has_pos_diff = any(
                _is_significant_diff(e["pos_diff"][axis])
                for axis in compare_axes
            )
            has_real_diff = has_pos_diff or has_size_diff

        entry: dict[str, Any] = {
            "obsBrandGoodId": e["obsBrandGoodId"],
            "matchIndex": e["matchIndex"],
            "name": e["name"],
            "status": "different" if has_real_diff else "identical",
            "scene_bbox": e["scene_bbox"],
            "abd_bbox": e["abd_bbox"],
            "abd_bbox_raw": e["abd_bbox_raw"],
        }
        if has_real_diff:
            diff_detail: dict[str, Any] = {}
            if not is_global_offset:
                pos_diff_filtered = {
                    axis: e["pos_diff"][axis]
                    for axis in compare_axes
                    if _is_significant_diff(e["pos_diff"][axis])
                }
                if pos_diff_filtered:
                    diff_detail["position"] = pos_diff_filtered
            if has_size_diff:
                diff_detail["size"] = {
                    axis: e["size_diff"][axis]
                    for axis in compare_axes
                    if _is_significant_diff(e["size_diff"][axis])
                }
            entry["diff"] = diff_detail
        results.append(entry)

    results.extend(unmatched_entries)

    if is_global_offset and global_offset:
        for r in results:
            r.setdefault("note", f"坐标系整体偏移 {global_offset}，已忽略")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compare scene bbox (from MCP get_scene_info) with abd.json."
    )
    parser.add_argument(
        "--abd", required=True,
        help="Path to abd.json",
    )
    parser.add_argument(
        "--parameditor-base-url", default="http://localhost:7764",
        help="Base URL of the parameditor MCP server (default: http://localhost:7764)",
    )
    parser.add_argument(
        "-o", "--output",
        help="Optional output JSON file path. If omitted, prints to stdout.",
    )
    args = parser.parse_args()

    abd_path = Path(args.abd)
    if not abd_path.exists():
        print(f"Error: abd.json not found: {abd_path}", file=sys.stderr)
        return 1

    with abd_path.open("r", encoding="utf-8") as f:
        abd_data = json.load(f)

    print(f"Calling get_scene_info from {args.parameditor_base_url} ...")
    scene_info = call_get_scene_info(args.parameditor_base_url)

    scene_count = len(scene_info.get("modelInstances", []))
    abd_count = len(abd_data.get("units", []))
    print(f"Scene instances: {scene_count}, ABD units: {abd_count}")

    abd_transform = compute_abd_to_scene_transform(abd_data.get("units", []))
    results = compare_bbox(scene_info, abd_data)

    output = {
        "coordinate_transform": {
            "description": (
                "abd(center-origin) → scene(left-back-bottom); "
                "abd_bbox 已变换后与 scene 比较（含 rotate/scale 时的世界 AABB）"
            ),
            "compare_tolerance_mm": _BBOX_COMPARE_TOLERANCE_MM,
            "origin_x": abd_transform["origin_x"],
            "origin_z": abd_transform["origin_z"],
            "abd_y_anchor": abd_transform["abd_y_anchor"],
            "formulas": {
                "x": "abd_x - origin_x",
                "y": "abd_y - size_y - abd_y_anchor",
                "z": "abd_z - origin_z",
            },
        },
        "summary": {
            "total_compared": len(results),
            "identical": sum(1 for r in results if r.get("status") == "identical"),
            "different": sum(1 for r in results if r.get("status") == "different"),
            "only_in_scene": sum(1 for r in results if r.get("status") == "only_in_scene"),
            "only_in_abd": sum(1 for r in results if r.get("status") == "only_in_abd"),
        },
        "details": results,
    }

    formatted = json.dumps(output, ensure_ascii=False, indent=2)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(formatted + "\n", encoding="utf-8")
        print(f"Result written to {out_path}")
    else:
        print(formatted)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
