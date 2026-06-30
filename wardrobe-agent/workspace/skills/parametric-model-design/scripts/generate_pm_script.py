"""
根据 abd.json（分析结果）与 design.json（布局设计）生成 PMBuilder 组合柜参数化 JS 脚本。

运行逻辑（main → generate_script）：

1. 加载输入
   - 读取 --abd / --design。
   - 调用 get_products_parameters 拉取默认参数（按 bgid），写出 tmp/output/param_default.json
     （在 preProcessDesignJson 之前，便于预处理钩子读取）。
   - 调用 preProcessDesignJson 预处理 design.json（见 pre_process_design_json.py）。
   - 校验 design 中各单元 obsBrandGoodId 是否与 abd 一致（不一致仅 warning）。

2. 拉取当前参数模板（generate_script 内）
   - 按 preprocess 后的 design.units[] 重新解析 instance_keys。
   - 调用 query_param_list 查询当前参数模板；若某实例无结果则回退到 obsBrandGoodId 查询。
   - 若存在 param_current.json，加载为「当前值」用于材质绑定判断。

3. 生成脚本 — 父级参数（PMBuilder.createParam）
   - 先写入 craft_parameters_specs.json 中的工艺参数；若 design 无 BGW 则跳过 ZBGYS/YBGYS。
   - 再写入 design.parentParams 中未与工艺表重名的项。
   - 系统保留参数（offset/location/material/style/float3 等）不得出现在 createParam 中。

4. 生成脚本 — 子单元（按 design.units[] 顺序）
   - createModelInstance(obsBrandGoodId) → setParam(name)（来自 abd 实例名）
   - setPosition / setRotation（弧度转角度）/ W、D、H
   - 遍历参数列表，按优先级 setParam：
     a. paramOverrides 直接覆盖；
     b. materialBrandGoodId：当前材质与父级 CZ 默认值一致时绑定 '#CZ'，否则写死值；
     c. 与子模型父参数同名且允许绑定的项 → '#父参数名'（复合参数附加 status:0）；
     d. 其余写 format_direct_value 字面量（style/float3 做格式转换）。
   - 若存在 BGW 且 label 为左/右边柜，functionName 绑定 '#ZBGYS' / '#YBGYS'。

5. 校验与输出
   - validate_script 检查是否误将系统保留参数提升为父级 createParam。
   - 通过则写入 -o 指定 JS 文件。

Usage:
    python generate_pm_script.py \\
        --abd tmp/input/abd.json \\
        --design tmp/output/design.json \\
        -o tmp/output/cabinet_script.js

design.json schema: see templates/designjson.example.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
WORKSPACE_ROOT = SCRIPT_DIR.parents[2]
CRAFT_PARAMETER_SPECS_PATH = SCRIPT_DIR / "craft_parameters_specs.json"
PARAM_DEFAULT_OUTPUT = WORKSPACE_ROOT / "tmp" / "output" / "param_default.json"
SHARED_SCRIPTS = SCRIPT_DIR.parents[1] / "shared" / "scripts"
sys.path.insert(0, str(SHARED_SCRIPTS))

UTILS_DIR = WORKSPACE_ROOT.parent / "data-tools" / "utils"
FETCH_MODEL_LIBRARY_DIR = UTILS_DIR / "fetch_model_library"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))
if str(FETCH_MODEL_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(FETCH_MODEL_LIBRARY_DIR))

from query_param_list import (  # noqa: E402
    AbdUnitIndex,
    CURRENT_VALUE_FILE,
    ParamListStore,
    get_param_inputs,
    query_param_list,
)
from api import get_products_parameters  # noqa: E402
from pre_process_design_json import preProcessDesignJson  # noqa: E402

SKIP_PARENT_TYPES = frozenset({"style", "float3"})
SKIP_PARENT_PARAM_NAMES = frozenset({
    "offset",
    "offsetGround",
    "offGround",
    "location",
})
SIZE_KEYS = frozenset({"W", "D", "H"})
TH_PARAM_NAME = "TH"
SHOUKOU_NAME_MARKER = "收口"
BGW_PARAM_NAME = "BGW"
FUNCTION_NAME_PARAM = "functionName"
MODEL_INSTANCE_NAME_PARAM = "name"
CZ_PARAM_NAME = "CZ"

# 子模型params中没有的参数
instance_specific_params_nams = frozenset({
    MODEL_INSTANCE_NAME_PARAM,
    FUNCTION_NAME_PARAM,
    "refName",
    "ignore",
})
MATERIAL_BRAND_GOOD_ID_PARAM = "materialBrandGoodId"
CRAFT_STYLE_BINDING_PARAMS = frozenset({"ZBGYS", "YBGYS"})


def parse_style(value: str) -> str:
    obj = json.loads(value.replace('\\"', '"'))
    return "'" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "'"


def parse_float3(value: str) -> str:
    """Convert param list float3 value (e.g. '0,0,0') to PMBuilder JSON object string."""
    raw = value.strip()
    if not raw:
        return "''"
    if raw.startswith("{"):
        return "'" + escape_js_string(raw) + "'"
    parts = [p.strip() for p in raw.split(",")]
    if len(parts) != 3:
        return "'" + escape_js_string(raw) + "'"
    obj = {"x": parts[0], "y": parts[1], "z": parts[2]}
    return "'" + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "'"


def should_skip_parent_param(param_name: str, value_type: str) -> bool:
    if param_name in SKIP_PARENT_PARAM_NAMES:
        return True
    # CZ binds via materialBrandGoodId → #CZ; other material params (e.g. GMCZ) bind normally.
    if param_name == CZ_PARAM_NAME:
        return True
    return value_type in SKIP_PARENT_TYPES


def is_shoukou_unit(unit_name: str | None, label: str) -> bool:
    for name in (unit_name, label):
        if isinstance(name, str) and SHOUKOU_NAME_MARKER in name:
            return True
    return False


def should_bind_to_parent_param(
    param_name: str,
    value_type: str,
    unit_name: str | None,
    label: str,
) -> bool:
    if should_skip_parent_param(param_name, value_type):
        return False
    if param_name == TH_PARAM_NAME and is_shoukou_unit(unit_name, label):
        return False
    return True


def format_direct_value(param: dict) -> str:
    value = param.get("value")
    if value is None:
        return "''"
    vt = param["valueType"]
    if vt == "style":
        return parse_style(value)
    if vt == "float3":
        return parse_float3(value)
    return f"'{value}'"


def is_composite_param_type(param: dict) -> bool:
    raw = param.get("paramTypeId")
    if raw in (None, ""):
        return False
    try:
        return int(raw) == 4
    except (TypeError, ValueError):
        return False


def format_set_param_options(param: dict, *, parent_ref_binding: bool = False) -> str:
    if parent_ref_binding and is_composite_param_type(param):
        return ", { status: 0 }"
    raw = param.get("status")
    if raw in (None, ""):
        return ""
    if isinstance(raw, bool):
        return f", {{ status: {str(raw).lower()} }}"
    if isinstance(raw, (int, float)):
        return f", {{ status: {raw} }}"
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return ""
        try:
            if "." in text:
                return f", {{ status: {float(text)} }}"
            return f", {{ status: {int(text)} }}"
        except ValueError:
            return f", {{ status: '{escape_js_string(text)}' }}"
    return ""


def build_set_param_line(
    var_name: str,
    param_name: str,
    value_expr: str,
    param: dict | None = None,
    *,
    parent_ref_binding: bool = False,
) -> str:
    pname = param_name if param_name.startswith("#") else f"#{param_name}"
    options = (
        format_set_param_options(param, parent_ref_binding=parent_ref_binding)
        if param
        else ""
    )
    return f"PMBuilder.setParam({var_name}, '{pname}', {value_expr}{options});"


def escape_js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def format_formula_for_js(formula: str) -> str:
    """design.json 用单引号字面量；PMBuilder 脚本里 formula 用外层单引号、内层双引号。"""
    converted = formula.replace("'", '"')
    escaped = converted.replace("\\", "\\\\").replace("'", "\\'")
    return escaped


def format_design_expr_for_js(value: str) -> str:
    """Embed a design.json expression/literal in a JS single-quoted argument."""
    if "'" in value:
        return format_formula_for_js(value)
    return escape_js_string(value)


def convert_radians_to_degrees(value: str) -> str:
    """Convert radian value to degrees only if the value is a pure number (not a parameter reference or formula)."""
    try:
        radians = float(value)
        degrees = radians * 180 / 3.141592653589793
        
        # Round to reasonable precision and handle common cases
        rounded = round(degrees, 6)
        
        # Check if it's essentially an integer
        if abs(rounded - round(rounded)) < 0.000001:
            return str(int(round(rounded)))
        
        # Remove trailing zeros and decimal point if not needed
        result = f"{rounded:.10g}".rstrip('0').rstrip('.')
        return result
    except (ValueError, TypeError):
        # If not a pure number (parameter reference, formula, etc.), return as-is
        return value


def load_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def find_param_value(inputs: list, param_name: str) -> str | None:
    for param in inputs:
        if not isinstance(param, dict):
            continue
        if param.get("paramName") != param_name:
            continue
        value = param.get("value")
        if value is None:
            return None
        return str(value)
    return None


def extract_material_obs_id(value: str) -> str | None:
    raw = value.strip()
    if not raw:
        return None
    if raw.startswith("{"):
        try:
            obj = json.loads(raw.replace('\\"', '"'))
            obs_id = obj.get("obsBrandGoodId")
            if obs_id is not None and str(obs_id).strip():
                return str(obs_id).strip()
        except json.JSONDecodeError:
            pass
    return raw


def material_values_equal(left: str | None, right: str | None) -> bool:
    if left is None or right is None:
        return False
    left_obs = extract_material_obs_id(left)
    right_obs = extract_material_obs_id(right)
    if left_obs and right_obs:
        return left_obs == right_obs
    return left.strip() == right.strip()


def should_bind_material_to_parent_cz(
    default_inputs: list,
    current_inputs: list,
    parent_param_names: set[str],
) -> bool:
    if CZ_PARAM_NAME not in parent_param_names:
        return False
    cz_default = find_param_value(default_inputs, MATERIAL_BRAND_GOOD_ID_PARAM)
    if cz_default is None:
        return False
    material_current = find_param_value(current_inputs, MATERIAL_BRAND_GOOD_ID_PARAM)
    if material_current is None:
        return False
    return material_values_equal(cz_default, material_current)


def load_current_param_store() -> ParamListStore | None:
    if not CURRENT_VALUE_FILE.exists():
        return None
    return ParamListStore(CURRENT_VALUE_FILE)


def get_current_inputs_for_unit(
    query_key: str,
    abd_index: AbdUnitIndex | None,
    current_store: ParamListStore | None,
) -> list:
    if current_store is None:
        return []
    model = current_store.find_model_for_query_key(query_key, abd_index, kind="instance")
    if model is None:
        return []
    return get_param_inputs(model)


def build_param_default_by_bgid(
    units: list[dict[str, Any]],
) -> dict[str, Any]:
    obs_ids: list[str] = []
    seen_obs: set[str] = set()
    for unit in units:
        obs_id = unit.get("obsBrandGoodId")
        if not isinstance(obs_id, str) or not obs_id.strip():
            continue
        obs_key = obs_id.strip()
        if obs_key in seen_obs:
            continue
        seen_obs.add(obs_key)
        obs_ids.append(obs_key)

    api_results = get_products_parameters(obs_ids)
    default_by_obs: dict[str, Any] = {}
    for result in api_results:
        bgid = result.get("obsBrandGoodId")
        if isinstance(bgid, str):
            result.pop("obsBrandGoodId", None)
            default_by_obs[bgid] = result

    return default_by_obs


def collect_instance_keys(
    abd: dict,
    units: list[dict[str, Any]],
) -> list[str]:
    abd_by_id, abd_by_obs = build_abd_unit_indexes(abd)
    consumed_abd_ids: set[str] = set()
    instance_keys: list[str] = []
    for unit in units:
        key = resolve_unit_query_key(unit, abd_by_id, abd_by_obs, consumed_abd_ids)
        instance_keys.append(key)
        if key in abd_by_id:
            consumed_abd_ids.add(key)
    return instance_keys


def fetch_and_write_param_default(design: dict) -> dict[str, Any]:
    units = design["units"]
    param_default_by_key = build_param_default_by_bgid(units)
    write_json(PARAM_DEFAULT_OUTPUT, param_default_by_key)
    return param_default_by_key


def lookup_param_default_entry(
    param_default_by_key: dict[str, Any],
    unit_cfg: dict[str, Any],
) -> dict[str, Any]:
    obs_id = unit_cfg.get("obsBrandGoodId")
    if not isinstance(obs_id, str) or not obs_id.strip():
        return {}
    obs_key = obs_id.strip()
    return param_default_by_key.get(obs_key, {})


def load_craft_parameter_specs() -> tuple[list[dict[str, Any]], frozenset[str]]:
    specs = load_json(CRAFT_PARAMETER_SPECS_PATH)
    if not isinstance(specs, list):
        raise ValueError(f"{CRAFT_PARAMETER_SPECS_PATH} must be a JSON array")
    names = frozenset(spec["name"] for spec in specs)
    return specs, names


def _style_default_value(obs_id: str) -> str:
    payload = json.dumps(
        {"obsBrandGoodId": obs_id, "versionId": 0},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return escape_js_string(payload)


def append_group_option(parts: list[str], spec: dict) -> None:
    group = spec.get("group")
    if group not in (None, ""):
        parts.append(f"group: '{escape_js_string(str(group))}'")


def craft_create_options(spec: dict) -> str:
    vt = spec["valueType"]
    pt = spec.get("paramTypeId")
    parts: list[str] = []
    # Only use link and linkForm when valueType is shape/material/style and paramTypeId is 2 or 4
    if vt in ("shape", "material", "style") and pt in (2, 4) and spec.get("link"):
        parts.append(f"link: '{spec['link']}', linkForm: '0'")
    elif vt in ("float", "int"):
        if spec.get("min") not in (None, ""):
            parts.append(f"min: '{spec['min']}'")
        if spec.get("max") not in (None, ""):
            parts.append(f"max: '{spec['max']}'")
    append_group_option(parts, spec)
    if not parts:
        return ", {}"
    return ", { " + ", ".join(parts) + " }"


def craft_create_value(spec: dict) -> str:
    vt = spec["valueType"]
    val = spec["value"]
    if vt == "style" and val:
        return _style_default_value(val)
    return escape_js_string(str(val))


def build_craft_param_line(spec: dict) -> str:
    pname = f"#{spec['name']}"
    return (
        f"PMBuilder.createParam('{pname}', '{craft_create_value(spec)}', "
        f"'{spec['valueType']}', '{escape_js_string(spec['displayName'])}', "
        f"{spec['paramTypeId']}{craft_create_options(spec)});"
    )


def parent_create_options(spec: dict) -> str:
    parts: list[str] = []
    vt = spec.get("valueType")
    pt = spec.get("paramTypeId")
    # Only use link and linkForm when valueType is shape/material/style and paramTypeId is 2 or 4
    if vt in ("shape", "material", "style") and pt in (2, 4) and spec.get("link"):
        link_form = spec.get("linkForm", "0")
        parts.append(f"link: '{spec['link']}', linkForm: '{link_form}'")
    mn, mx = spec.get("min"), spec.get("max")
    if mn not in (None, "") and mx not in (None, ""):
        parts.append(f"min: '{format_formula_for_js(str(mn))}'")
        parts.append(f"max: '{format_formula_for_js(str(mx))}'")
    if spec.get("formula"):
        formula = spec["formula"]
        # Handle formula as object (for formulaForm=1)
        if isinstance(formula, dict):
            formula_json = json.dumps(formula, ensure_ascii=False)
            parts.append(f"formula: {formula_json}")
        else:
            parts.append(f"formula: '{format_formula_for_js(formula)}'")
    # formulaForm is required for paramTypeId=4, default to 0 if not specified
    if pt == 4 and spec.get("formula"):
        formula_form = spec.get("formulaForm", 0)
        parts.append(f"formulaForm: {formula_form}")
    if spec.get("status") is not None:
        parts.append(f"status: {spec['status']}")
    opts = spec.get("editorOptions")
    if opts:
        enum_opts = ", ".join(
            f"{{ name: '{escape_js_string(o['name'])}', value: '{escape_js_string(str(o['value']))}' }}"
            for o in opts
        )
        parts.append(f"editorOptions: [{enum_opts}]")
    display_names = spec.get("valueDisplayNames")
    if display_names:
        names = ", ".join(
            f"'{escape_js_string(str(n))}'" for n in display_names
        )
        parts.append(f"valueDisplayNames: [{names}]")
    append_group_option(parts, spec)
    if not parts:
        return ", {}"
    return ", { " + ", ".join(parts) + " }"


def build_design_parent_param_line(spec: dict) -> str:
    name = spec["name"]
    pname = name if name.startswith("#") else f"#{name}"
    value = escape_js_string(str(spec.get("value", "")))
    return (
        f"PMBuilder.createParam('{pname}', '{value}', "
        f"'{spec['valueType']}', '{escape_js_string(spec['displayName'])}', "
        f"{spec.get('paramTypeId', 1)}{parent_create_options(spec)});"
    )


def normalize_param_name(name: str) -> str:
    return name.lstrip("#")


def has_bgw_parent_param(design: dict) -> bool:
    return any(
        normalize_param_name(spec["name"]) == BGW_PARAM_NAME
        for spec in design.get("parentParams", [])
    )


def build_abd_unit_indexes(
    abd: dict,
) -> tuple[dict[str, dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    """Index abd units by instance id and by obsBrandGoodId (supports duplicates)."""
    by_id: dict[str, dict[str, Any]] = {}
    by_obs: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in abd.get("units", []):
        if not isinstance(unit, dict):
            continue
        obs_id = unit.get("obsBrandGoodId")
        unit_id = unit.get("id")
        if isinstance(unit_id, str) and unit_id.strip():
            by_id[unit_id.strip()] = unit
        if isinstance(obs_id, str) and obs_id.strip():
            by_obs[obs_id.strip()].append(unit)
    return by_id, dict(by_obs)


def resolve_unit_query_key(
    unit_cfg: dict[str, Any],
    abd_by_id: dict[str, dict[str, Any]],
    abd_by_obs: dict[str, list[dict[str, Any]]],
    consumed_abd_ids: set[str],
) -> str:
    """
    Resolve the id passed to query_param_list.

    design.json may carry template placeholder ids; prefer abd.json instance ids
    so param_current.json (keyed by units[].id) is found.
    """
    obs_id = unit_cfg.get("obsBrandGoodId")
    obs_key = str(obs_id).strip() if obs_id is not None else ""
    unit_id = unit_cfg.get("id")
    if isinstance(unit_id, str) and unit_id.strip():
        key = unit_id.strip()
        if key in abd_by_id:
            return key

    candidates = [
        u
        for u in abd_by_obs.get(obs_key, [])
        if isinstance(u.get("id"), str) and u["id"].strip() not in consumed_abd_ids
    ]
    if len(candidates) == 1:
        return candidates[0]["id"].strip()

    label = unit_cfg.get("label", "")
    if isinstance(label, str) and label:
        for unit in candidates:
            name = unit.get("name")
            if isinstance(name, str) and name and name in label:
                return unit["id"].strip()

    if candidates:
        return candidates[0]["id"].strip()
    if isinstance(unit_id, str) and unit_id.strip():
        return unit_id.strip()
    return obs_key


def build_abd_unit_name_by_id(abd: dict) -> dict[str, str]:
    """Map abd units[].id → name for per-instance naming in generated scripts."""
    index: dict[str, str] = {}
    for unit in abd.get("units", []):
        if not isinstance(unit, dict):
            continue
        unit_id = unit.get("id")
        name = unit.get("name")
        if not isinstance(unit_id, str) or not unit_id.strip():
            continue
        if not isinstance(name, str) or not name.strip():
            continue
        index[unit_id.strip()] = name.strip()
    return index


def resolve_abd_unit_name(
    unit_cfg: dict,
    abd_name_by_id: dict[str, str],
) -> str | None:
    """Resolve instance name via design.json units[].id → abd.json units[].name."""
    unit_id = unit_cfg.get("id")
    if not isinstance(unit_id, str) or not unit_id.strip():
        return None
    return abd_name_by_id.get(unit_id.strip())


def side_cabinet_style_parent_ref(
    unit_cfg: dict,
    parent_param_names: set[str],
) -> str | None:
    """边柜 label 含「左」/「右」时，返回对应父级样式参数引用。

    仅当父模型已通过 createParam 创建对应参数（ZBGYS/YBGYS）时才返回引用，
    否则返回 None，避免 setParam 引用未定义的父参数。
    """
    label = unit_cfg.get("label", "")
    if "边" not in label or "柜" not in label:
        return None
    if "左" in label and "ZBGYS" in parent_param_names:
        return "#ZBGYS"
    if "右" in label and "YBGYS" in parent_param_names:
        return "#YBGYS"
    return None


def build_parent_param_lines(
    design: dict,
) -> tuple[list[str], set[str]]:
    """Create craft params from craft_parameters_specs.json, then design.json parentParams."""
    lines: list[str] = []
    parent_names: set[str] = set()
    has_bgw = has_bgw_parent_param(design)
    craft_parameter_specs, craft_param_names = load_craft_parameter_specs()

    for spec in craft_parameter_specs:
        name = spec["name"]
        if name in CRAFT_STYLE_BINDING_PARAMS and not has_bgw:
            continue
        parent_names.add(name)
        lines.append(build_craft_param_line(spec))

    for spec in design.get("parentParams", []):
        name = normalize_param_name(spec["name"])
        if name in craft_param_names:
            continue
        parent_names.add(name)
        lines.append(build_design_parent_param_line(spec))

    return lines, parent_names


def format_override_value(
    override_value: Any,
    param: dict | None = None,
) -> tuple[str, str]:
    """
    Format a paramOverrides value for setParam.

    Returns a tuple of (value_expr, options_str):
    - For simple strings: (quoted_value, "")
    - For objects: (quoted_value_field, options_object_str)

    Examples:
        "#CZ" -> ("'#CZ'", "")
        {"value": "1.0", "status": 1} -> ("'1.0'", "{ status: 1 }")
    """
    force_value_status = is_composite_param_type(param) if param else False

    if isinstance(override_value, dict):
        value = override_value.get("value", "")
        options = {}
        for key, val in override_value.items():
            if key not in ("value", "paramName"):
                options[key] = val
        if force_value_status:
            options["status"] = 0

        if isinstance(value, str):
            value_expr = f"'{escape_js_string(value)}'"
        elif isinstance(value, bool):
            value_expr = str(value).lower()
        elif isinstance(value, (int, float)):
            value_expr = str(value)
        else:
            value_expr = f"'{escape_js_string(str(value))}'"

        if options:
            options_parts = []
            for key, val in options.items():
                if isinstance(val, bool):
                    options_parts.append(f"{key}: {str(val).lower()}")
                elif isinstance(val, (int, float)):
                    options_parts.append(f"{key}: {val}")
                elif isinstance(val, str):
                    options_parts.append(f"{key}: '{escape_js_string(val)}'")
                else:
                    options_parts.append(f"{key}: '{escape_js_string(str(val))}'")
            options_str = "{ " + ", ".join(options_parts) + " }"
        else:
            options_str = ""

        return (value_expr, options_str)

    if isinstance(override_value, str):
        value_expr = f"'{escape_js_string(override_value)}'"
    elif isinstance(override_value, bool):
        value_expr = str(override_value).lower()
    elif isinstance(override_value, (int, float)):
        value_expr = str(override_value)
    else:
        value_expr = f"'{escape_js_string(str(override_value))}'"

    options_str = "{ status: 0 }" if force_value_status else ""
    return (value_expr, options_str)


def build_unit_lines(
    unit_cfg: dict,
    params: list,
    param_default: list,
    parent_param_names: set[str],
    has_bgw: bool,
    abd_name_by_id: dict[str, str],
    bind_material_to_cz: bool = False,
    instance_num: int = 1,
) -> list[str]:
    lines: list[str] = []
    var_name = f"inst{instance_num}"
    obs_id = unit_cfg["obsBrandGoodId"]
    label = unit_cfg.get("label", obs_id)
    overrides = unit_cfg.get("paramOverrides", {})
    abd_unit_name = resolve_abd_unit_name(unit_cfg, abd_name_by_id)

    lines.append(f"// ---- {label} ----")
    lines.append(f"const {var_name} = PMBuilder.createModelInstance('{obs_id}');")

    if abd_unit_name and MODEL_INSTANCE_NAME_PARAM not in overrides:
        name_literal = escape_js_string(abd_unit_name.lstrip("#"))
        lines.append(
            f"PMBuilder.setParam({var_name}, '#{MODEL_INSTANCE_NAME_PARAM}', "
            f"'{name_literal}');"
        )

    pos = unit_cfg["position"]
    rot = unit_cfg.get("rotation", ["0", "0", "0"])
    lines.append(
        f"PMBuilder.setPosition({var_name}, "
        f"'{format_design_expr_for_js(pos[0])}', "
        f"'{format_design_expr_for_js(pos[1])}', "
        f"'{format_design_expr_for_js(pos[2])}');"
    )
    # Convert rotation from radians to degrees
    rot_x = convert_radians_to_degrees(rot[0])
    rot_y = convert_radians_to_degrees(rot[1])
    rot_z = convert_radians_to_degrees(rot[2])
    lines.append(
        f"PMBuilder.setRotation({var_name}, "
        f"'{format_design_expr_for_js(rot_x)}', "
        f"'{format_design_expr_for_js(rot_y)}', "
        f"'{format_design_expr_for_js(rot_z)}');"
    )

    size = unit_cfg.get("size", {})
    for key in ("W", "D", "H"):
        if key in size:
            lines.append(
                f"PMBuilder.setParam({var_name}, '#{key}', "
                f"'{format_design_expr_for_js(size[key])}');"
            )

    for param in params:
        name = param["paramName"]
        if name in SIZE_KEYS:
            continue
        if (
            name == MODEL_INSTANCE_NAME_PARAM
            and abd_unit_name
            and MODEL_INSTANCE_NAME_PARAM not in overrides
        ):
            continue
        if name in overrides:
            override_value = overrides[name]
            value_expr, options_str = format_override_value(override_value, param)
            if options_str:
                lines.append(
                    f"PMBuilder.setParam({var_name}, '#{name}', {value_expr}, {options_str});"
                )
            else:
                lines.append(
                    f"PMBuilder.setParam({var_name}, '#{name}', {value_expr});"
                )
            continue
        if name == MATERIAL_BRAND_GOOD_ID_PARAM:
            if bind_material_to_cz:
                lines.append(
                    f"PMBuilder.setParam({var_name}, '#{name}', '#{CZ_PARAM_NAME}');"
                )
            else:
                lines.append(
                    build_set_param_line(
                        var_name, name, format_direct_value(param), param
                    )
                )
            continue
        if name in parent_param_names and should_bind_to_parent_param(
            name, param["valueType"], abd_unit_name, label
        ):
            lines.append(
                build_set_param_line(
                    var_name, name, f"'#{name}'", param, parent_ref_binding=True
                )
            )
            continue
        lines.append(
            build_set_param_line(var_name, name, format_direct_value(param), param)
        )

    # Process paramOverrides
    # Special parameters (name, functionName, refName, ignore) are always processed
    processed_param_names = {param["paramName"] for param in params if isinstance(param, dict)}
    param_default_by_name = {
        param["paramName"]: param
        for param in param_default
        if isinstance(param, dict) and isinstance(param.get("paramName"), str)
    }

    for override_name, override_value in overrides.items():
        # Skip parameters that were already handled in the main loop
        if override_name in processed_param_names:
            continue

        # Handle special parameters (name, functionName, refName, ignore)
        # These are always processed regardless of whether they're in params list
        if override_name in instance_specific_params_nams:
            value_expr, options_str = format_override_value(override_value)
            if options_str:
                lines.append(
                    f"PMBuilder.setParam({var_name}, '#{override_name}', {value_expr}, {options_str});"
                )
            else:
                lines.append(
                    f"PMBuilder.setParam({var_name}, '#{override_name}', {value_expr});"
                )
            continue

        # Regular parameters: only process if they exist in param_default list
        param_default = param_default_by_name.get(override_name)
        if param_default is None:
            continue

        value_expr, options_str = format_override_value(override_value, param_default)
        if options_str:
            lines.append(
                f"PMBuilder.setParam({var_name}, '#{override_name}', {value_expr}, {options_str});"
            )
        else:
            lines.append(
                f"PMBuilder.setParam({var_name}, '#{override_name}', {value_expr});"
            )

    if has_bgw and FUNCTION_NAME_PARAM not in overrides:
        style_ref = side_cabinet_style_parent_ref(unit_cfg, parent_param_names)
        if style_ref:
            lines.append(
                f"PMBuilder.setParam({var_name}, '#{FUNCTION_NAME_PARAM}', '{style_ref}');"
            )

    lines.append("")
    return lines


def validate_design_against_abd(design: dict, abd: dict) -> list[str]:
    warnings: list[str] = []
    abd_ids = {u["obsBrandGoodId"] for u in abd.get("units", [])}
    design_ids = {u["obsBrandGoodId"] for u in design.get("units", [])}
    missing_in_design = abd_ids - design_ids
    extra_in_design = design_ids - abd_ids
    if missing_in_design:
        warnings.append(f"design 缺少 abd 中的 obsBrandGoodId: {sorted(missing_in_design)}")
    if extra_in_design:
        warnings.append(f"design 包含 abd 中不存在的 obsBrandGoodId: {sorted(extra_in_design)}")
    return warnings

def validate_script(script: str) -> list[str]:
    """Ensure system-reserved params are not promoted to parent createParam."""
    errors: list[str] = []
    for name in SKIP_PARENT_PARAM_NAMES:
        if re.search(rf"createParam\(\s*'#{{0,1}}{re.escape(name)}'", script):
            errors.append(
                f"illegal createParam for system-reserved #{name} "
                f"(must only appear as child setParam with literal)"
            )
    return errors


def generate_script(
    abd: dict,
    design: dict,
    *,
    param_default_by_key: dict[str, Any],
) -> str:
    units = design["units"]

    abd_by_id, _ = build_abd_unit_indexes(abd)
    abd_index = AbdUnitIndex.from_abd(abd)
    instance_keys = collect_instance_keys(abd, units)

    current_store = load_current_param_store()

    use_instance_query = bool(abd_by_id) or any(
        isinstance(u.get("id"), str) and str(u.get("id")).strip() for u in units
    )
    if use_instance_query:
        params_by_key = query_param_list(instance_ids=instance_keys)
    else:
        params_by_key = query_param_list(obs_brand_good_ids=instance_keys)

    unit_params_list: list[list] = []
    for _, query_key in zip(units, instance_keys):
        params = get_param_inputs(params_by_key.get(query_key, {}))
        unit_params_list.append(params)

    lines: list[str] = []
    title = design.get("name") or abd.get("name") or "组合柜"
    lines.append(f"// {title}")
    lines.append("")

    has_bgw = has_bgw_parent_param(design)
    abd_name_by_id = build_abd_unit_name_by_id(abd)
    parent_lines, parent_param_names = build_parent_param_lines(design)
    lines.extend(parent_lines)
    lines.append("")

    for idx, (unit_cfg, params, query_key) in enumerate(zip(units, unit_params_list, instance_keys), start=1):
        default_inputs = get_param_inputs(
            lookup_param_default_entry(param_default_by_key, unit_cfg)
        )
        current_inputs = get_current_inputs_for_unit(query_key, abd_index, current_store)
        bind_material_to_cz = should_bind_material_to_parent_cz(
            default_inputs,
            current_inputs,
            parent_param_names,
        )
        lines.extend(
            build_unit_lines(
                unit_cfg,
                params,
                default_inputs,
                parent_param_names,
                has_bgw,
                abd_name_by_id,
                bind_material_to_cz,
                instance_num=idx,
            )
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate PMBuilder JS from abd.json + design.json"
    )
    parser.add_argument("--abd", required=True, type=Path, help="Path to abd.json")
    parser.add_argument(
        "--design",
        required=True,
        type=Path,
        help="Path to design.json",
    )
    parser.add_argument("-o", "--output", required=True, type=Path, help="Output JS file path")
    args = parser.parse_args()

    abd = load_json(args.abd)
    design = load_json(args.design)
    param_default_by_key = fetch_and_write_param_default(design)
    print(f"Wrote {PARAM_DEFAULT_OUTPUT}")

    design = preProcessDesignJson(design, abd, design_path=args.design)

    warnings = validate_design_against_abd(design, abd)
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)

    script = generate_script(abd, design, param_default_by_key=param_default_by_key)
    validation_errors = validate_script(script)
    if validation_errors:
        for err in validation_errors:
            print(f"error: {err}", file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(script, encoding="utf-8")

    line_count = script.count("\n") + (0 if script.endswith("\n") else 1)
    print(f"Wrote {args.output} ({line_count} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
