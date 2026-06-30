"""
给定收藏夹 folderId 与 brandGoodId：
1. 用 bgcollections/v2 在该目录下定位商品，取得封面图 URL（优先 coverImgUrl；assemblyattach 响应通常不含该字段）。
2. 用 fetch_assembly 拉取装配 JSON，从 assemblyDataAndAttach.assemblyData.paramModels 抽取 abd 结构（含 obsCollectBrandGoodId、units[].id、units[].modelBrandGoodName）。
3. 将 abd.json、parammodel_param_list.json、assemblyattach 原始装配 JSON（assembly.json）与封面图写入指定输出目录。

依赖：同目录 fetch_common / fetch_bg_collections / fetch_assembly / crypt_zstd / crypt_num（见 requirements.txt）。
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

UTILS_DIR = Path(__file__).resolve().parent.parent
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))
REPO_ROOT = Path(__file__).resolve().parents[3]

from login import DEFAULT_STATUS_FILE, prepare_headers_from_status

import fetch_common
from crypt_zstd import encrypt_body_to_base64
from fetch_assembly import (
    build_assembly_url,
    build_request_payload_bytes,
    decrypt_assembly_response,
    prepare_assembly_post_headers,
)
from fetch_bg_collections import build_bg_collections_url
from crypt_num import LongCrypt

# abd 内导出 obsBrandGoodId（与示例一致：LongCrypt(71284230948672, 35).encrypt(bgId)）
_ABD_BRAND_GOOD_CRYPT = LongCrypt(71284230948672, 35)


def _load_auth_request_headers(status_file: Path | None) -> dict[str, str]:
    raw_headers = prepare_headers_from_status(status_file or DEFAULT_STATUS_FILE)
    fetch_common.warn_if_qunhe_jwt_stale(raw_headers)
    return raw_headers


def _normalize_asset_url(raw: str | None) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s.startswith("//"):
        return "https:" + s
    if s.startswith(("http://", "https://")):
        return s
    return None


def _pick_cover_image_url(row: dict[str, Any]) -> str | None:
    """收藏列表中的封面图 URL：优先 cover，再尝试其它展示图。"""
    for key in (
        "coverImgUrl",
        "frontImgUrl",
        "largeImgUrl",
        "topImgUrl",
        "previewImgUrl",
    ):
        u = _normalize_asset_url(row.get(key))
        if u:
            return u
    return None


def _vec3_from(obj: Any) -> dict[str, float] | None:
    """从 paramModel 节点读取 x/y/z；允许缺键，至少一键有效即返回。"""
    if not isinstance(obj, dict):
        return None
    out: dict[str, float] = {}
    for k in ("x", "y", "z"):
        if k not in obj:
            continue
        try:
            out[k] = float(obj[k])
        except (TypeError, ValueError):
            continue
    return out or None


def _coerce_brand_good_id(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _resolve_brand_good_id(v: int | str) -> int:
    """支持数字 brandGoodId/bgId，或加密后的 obsBrandGoodId。"""
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if not s:
        raise ValueError("bgId / obsBrandGoodId 不能为空")
    if s.isdecimal():
        return int(s)
    try:
        return _ABD_BRAND_GOOD_CRYPT.decrypt(s)
    except ValueError as e:
        raise ValueError(f"无法解析 bgId / obsBrandGoodId: {v}") from e


# parammodel_param_list.json：无品类信息时使用 categoryId
PARAMMODEL_PARAM_LIST_CATEGORY_UNKNOWN = "unknown"
DEFAULT_PARAMMODEL_PARAM_CURRENT_VALUE_PATH = (
    REPO_ROOT / "workspace" / "tmp" / "input" / "param_current.json"
)


def _resolve_assembly_data(assembly_root: dict[str, Any]) -> dict[str, Any]:
    ada = assembly_root.get("assemblyDataAndAttach")
    if not isinstance(ada, dict):
        raise ValueError("缺少 assemblyDataAndAttach")
    adata = ada.get("assemblyData")
    if not isinstance(adata, dict):
        raise ValueError("缺少 assemblyDataAndAttach.assemblyData")
    return adata


def _resolve_assembly_param_models(
    assembly_root: dict[str, Any],
) -> list[Any]:
    adata = _resolve_assembly_data(assembly_root)
    pms = adata.get("paramModels")
    if not isinstance(pms, list):
        raise ValueError("缺少 assemblyData.paramModels（或非数组）")
    return pms


def _resolve_assembly_param_model_groups(assembly_root: dict[str, Any]) -> list[Any]:
    adata = _resolve_assembly_data(assembly_root)
    groups = adata.get("paramModelGroups")
    return groups if isinstance(groups, list) else []


def _resolve_response_param_model_attacheds(assembly_root: dict[str, Any]) -> list[Any]:
    ada = assembly_root.get("assemblyDataAndAttach")
    if not isinstance(ada, dict):
        return []
    response_data = ada.get("responseData")
    if not isinstance(response_data, dict):
        return []
    attacheds = response_data.get("paramModelAttacheds")
    return attacheds if isinstance(attacheds, list) else []


_STYLE_BG_JSON_KEYS = ("bgId",)


def _double_escape_quotes_and_backslashes(s: str) -> str:
    """对已序列化的 JSON 文本做嵌入用二次转义：斜杠先、再双引号。"""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def _style_value_db_to_obs_and_serialize(val: Any) -> str:
    """
    style 参数的 value（JSON 对象或 JSON 字符串）：
    将 bgId 字段改为 obsBrandGoodId（值为 encrypt 后的密文），原键 bgId 不再保留；
    再序列化并对字符串内的双引号、斜杠做二次转义。
    """
    if val is None:
        return ""
    raw_obj: dict[str, Any] | None = None
    if isinstance(val, dict):
        raw_obj = dict(val)
    elif isinstance(val, str):
        stripped = val.strip()
        if not stripped:
            return ""
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return _double_escape_quotes_and_backslashes(stripped)
        if isinstance(parsed, dict):
            raw_obj = dict(parsed)
        else:
            inner = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
            return _double_escape_quotes_and_backslashes(inner)
    else:
        return str(val)

    bg_key = _STYLE_BG_JSON_KEYS[0]
    if bg_key in raw_obj:
        bg_raw = raw_obj.pop(bg_key)
        bg_int = _coerce_brand_good_id(bg_raw)
        enc = _ABD_BRAND_GOOD_CRYPT.encrypt(bg_int)
        if enc is not None:
            raw_obj["obsBrandGoodId"] = enc
        else:
            raw_obj[bg_key] = bg_raw

    inner_js = json.dumps(raw_obj, separators=(",", ":"), ensure_ascii=False)
    return _double_escape_quotes_and_backslashes(inner_js)


def _param_to_input_entry(p: dict[str, Any]) -> dict[str, Any]:
    vmax = p.get("max")
    vmin = p.get("min")
    val = p.get("value")
    raw_status = p.get("status")
    link = p.get("link")
    link_form = p.get("linkForm")
    formula = p.get("formula")
    formula_form = p.get("formulaForm")
    value_type_s = str(p.get("type") or "string")
    value_kind = value_type_s.lower()

    if val is None:
        value_out = ""
    elif value_kind == "material":
        enc = _ABD_BRAND_GOOD_CRYPT.encrypt(_coerce_brand_good_id(val))
        value_out = "" if enc is None else enc
    elif value_kind == "style":
        value_out = _style_value_db_to_obs_and_serialize(val)
    elif value_kind == "float3":
        val_str = str(val)
        if "," in val_str:
            parts = val_str.split(",")
            if len(parts) == 3:
                value_out = json.dumps({"x": parts[0], "y": parts[1], "z": parts[2]}, separators=(",", ":"))
            else:
                value_out = val_str
        else:
            value_out = val_str
    else:
        value_out = str(val)
    entry: dict[str, Any] = {
        "paramName": str(p.get("name") or ""),
        "value": value_out,
        "valueType": value_type_s,
        "status": str(raw_status) if raw_status is not None else "",
        "paramTypeId": p.get("paramTypeId", 0),
        "displayName": str(p.get("displayName") or ""),
    }
    min_value = "" if vmin is None else str(vmin)
    max_value = "" if vmax is None else str(vmax)
    if min_value != "":
        entry["min"] = min_value
    if max_value != "":
        entry["max"] = max_value
    if link_form is not None:
        entry["linkForm"] = link_form
    if formula_form is not None:
        entry["formulaForm"] = formula_form
    if link not in (None, ""):
        entry["link"] = link
    if formula not in (None, ""):
        entry["formula"] = formula

    return entry


def build_parammodel_param_list_payload(
    assembly_root: dict[str, Any],
) -> dict[str, Any]:
    """每个顶层 paramModel 对应 models 中一项，params → inputs。"""
    pms = _resolve_assembly_param_models(assembly_root)
    models: list[dict[str, Any]] = []
    for pm in pms:
        if not isinstance(pm, dict):
            continue
        bg_int = _coerce_brand_good_id(pm.get("brandGoodId"))
        obs = _ABD_BRAND_GOOD_CRYPT.encrypt(bg_int)
        if obs is None:
            continue
        inputs: list[dict[str, str]] = []
        raw_params = pm.get("params")
        if isinstance(raw_params, list):
            for pr in raw_params:
                if isinstance(pr, dict):
                    inputs.append(_param_to_input_entry(pr))
        entry: dict[str, Any] = {"obsBrandGoodId": obs}
        name = pm.get("name")
        if isinstance(name, str) and name.strip():
            entry["name"] = name.strip()
        pm_id = pm.get("id")
        if isinstance(pm_id, str) and pm_id.strip():
            entry["id"] = pm_id.strip()
        entry["inputs"] = inputs
        models.append(entry)

    return {
        "param_list": [
            {
                "categoryId": PARAMMODEL_PARAM_LIST_CATEGORY_UNKNOWN,
                "models": models,
            }
        ]
    }


def _vec3_add(a: dict[str, float] | None, b: dict[str, float] | None) -> dict[str, float] | None:
    if a is None:
        return b
    if b is None:
        return a
    return {k: a.get(k, 0.0) + b.get(k, 0.0) for k in ("x", "y", "z") if k in a or k in b}


def _vec3_multiply(a: dict[str, float] | None, b: dict[str, float] | None) -> dict[str, float] | None:
    if a is None:
        return b
    if b is None:
        return a
    return {k: a.get(k, 1.0) * b.get(k, 1.0) for k in ("x", "y", "z") if k in a or k in b}


def _vec3_scale(a: dict[str, float] | None, factor: float) -> dict[str, float] | None:
    if a is None:
        return None
    return {k: v * factor for k, v in a.items()}


def _node_position(node: dict[str, Any]) -> dict[str, float] | None:
    pos = node.get("position")
    if pos is None:
        pos = node.get("center")
    return _vec3_from(pos)


def _node_center(node: dict[str, Any]) -> dict[str, float] | None:
    return _vec3_from(node.get("center"))


def _node_insert_offset(node: dict[str, Any]) -> dict[str, float] | None:
    if node.get("invokeTypeId") != 0:
        return None
    bounding_box = node.get("boundingBox")
    if isinstance(bounding_box, dict):
        min_v = _vec3_from(bounding_box.get("min"))
        max_v = _vec3_from(bounding_box.get("max"))
        out: dict[str, float] = {}
        if min_v is not None:
            if "x" in min_v:
                out["x"] = min_v["x"]
            if "z" in min_v:
                out["z"] = min_v["z"]
        if max_v is not None and "y" in max_v:
            out["y"] = max_v["y"]
        if out:
            return out
    size = _vec3_from(node.get("size"))
    return _vec3_scale(size, -0.5)


def _param_model_attached_by_id(assembly_root: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        node.get("id"): node
        for node in _resolve_response_param_model_attacheds(assembly_root)
        if isinstance(node, dict) and isinstance(node.get("id"), str)
    }


def _merge_param_model_metadata(
    node: dict[str, Any],
    attached_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    node_id = node.get("id")
    attached = attached_by_id.get(node_id) if isinstance(node_id, str) else None
    if attached is None:
        return node
    merged = dict(attached)
    merged.update(node)
    return merged


def _accessory_main_id_by_id(assembly_root: dict[str, Any]) -> dict[str, str]:
    accessory_main_by_id: dict[str, str] = {}
    for group in _resolve_assembly_param_model_groups(assembly_root):
        if not isinstance(group, dict):
            continue
        main_id = group.get("mainId")
        accessory_ids = group.get("accessoryIds")
        if not isinstance(main_id, str) or not isinstance(accessory_ids, list):
            continue
        for accessory_id in accessory_ids:
            if isinstance(accessory_id, str):
                accessory_main_by_id[accessory_id] = main_id
    return accessory_main_by_id


def _model_name_from_editordata(obs_brand_good_id: str) -> str | None:
    """GET /editor/api/site/editordata → model.name（商品库名称）。"""
    try:
        from fetch_model_library.api import get_product_info_by_brand_good_id
    except ImportError:
        return None
    try:
        model = get_product_info_by_brand_good_id(obs_brand_good_id)
    except Exception:
        return None
    if not isinstance(model, dict):
        return None
    for key in ("name", "showName", "modelName"):
        raw = model.get(key)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def _resolve_model_brand_good_names(obs_ids: set[str]) -> dict[str, str]:
    """按 obsBrandGoodId 批量解析 modelBrandGoodName（去重后各请求一次 editordata）。"""
    out: dict[str, str] = {}
    for obs in sorted(obs_ids):
        name = _model_name_from_editordata(obs)
        if name:
            out[obs] = name
    return out


def _obs_collect_brand_good_id(
    collection_row: dict[str, Any] | None,
    brand_good_id: int | None,
) -> str | None:
    if collection_row:
        obs = collection_row.get("obsBrandGoodId")
        if isinstance(obs, str) and obs.strip():
            return obs.strip()
    if brand_good_id is not None:
        return _ABD_BRAND_GOOD_CRYPT.encrypt(brand_good_id)
    return None


def _transform_param_node(
    node: dict[str, Any],
    *,
    main_node: dict[str, Any] | None = None,
    unit_id: str | None = None,
    model_brand_good_name: str | None = None,
) -> dict[str, Any]:
    position = _node_position(node)
    rotate = _vec3_from(node.get("rotate"))
    scale = _vec3_from(node.get("scale"))
    if main_node is not None:
        position = _vec3_add(_node_center(main_node), position)
        rotate = _vec3_add(_vec3_from(main_node.get("rotate")), rotate)
        scale = _vec3_multiply(_vec3_from(main_node.get("scale")), scale)
        position = _vec3_add(position, _node_insert_offset(node))
    bg_int = _coerce_brand_good_id(node.get("brandGoodId"))
    obs = _ABD_BRAND_GOOD_CRYPT.encrypt(bg_int)
    out: dict[str, Any] = {"name": node.get("name")}
    if isinstance(unit_id, str) and unit_id.strip():
        out["id"] = unit_id.strip()
    if model_brand_good_name:
        out["modelBrandGoodName"] = model_brand_good_name
    out["obsBrandGoodId"] = obs
    out["position"] = position
    out["rotate"] = rotate
    out["size"] = _vec3_from(node.get("size"))
    if scale is not None:
        out["scale"] = scale
    return out


def _collect_goods_pages(
    status_file: Path | None,
    folder_id: str,
    *,
    foldertype: int,
    timeout: float,
    jwt_bearer: bool,
    referer: str | None,
    origin: str | None,
    no_header_fix: bool,
    page_size: int = 40,
) -> list[dict[str, Any]]:
    raw_headers = _load_auth_request_headers(status_file)
    headers = fetch_common.prepare_bgcollections_headers(
        raw_headers,
        referer_override=referer,
        origin_override=origin,
        skip_augment=no_header_fix,
        attach_bearer=jwt_bearer,
    )
    out: list[dict[str, Any]] = []
    start = 0
    total: int | None = None
    while True:
        url = build_bg_collections_url(
            folder_id, num=page_size, start=start, foldertype=foldertype
        )
        status, _rh, body = fetch_common.fetch_body(url, "GET", headers, timeout)
        if status >= 400:
            preview = body[:800].decode("utf-8", errors="replace")
            raise RuntimeError(f"bgcollections HTTP {status}，响应前缀:\n{preview}")
        plain = fetch_common.decrypt_response_body(body)
        obj = json.loads(plain)
        if total is None and "count" in obj:
            try:
                total = int(obj["count"])
            except (TypeError, ValueError):
                total = None
        batch = obj.get("data")
        if not isinstance(batch, list):
            batch = []
        for row in batch:
            if isinstance(row, dict):
                out.append(row)
        if len(batch) < page_size:
            break
        start += page_size
        if total is not None and start >= total:
            break
    return out


def _find_row_for_bg(rows: list[dict[str, Any]], bg_id: int) -> dict[str, Any] | None:
    for row in rows:
        cand = _coerce_brand_good_id(row.get("brandGoodId"))
        if cand == bg_id:
            return row
    return None


def _fetch_assembly_json(
    status_file: Path | None,
    bg_id: int,
    *,
    timeout: float,
    jwt_bearer: bool,
    zstd_level: int,
    referer: str | None,
    origin: str | None,
    no_header_fix: bool,
) -> dict[str, Any]:
    raw_headers = _load_auth_request_headers(status_file)
    payload = build_request_payload_bytes(bg_id)
    b64_body = encrypt_body_to_base64(payload, level=zstd_level)
    post_bytes = b64_body.encode("ascii")
    headers = fetch_common.prepare_bgcollections_headers(
        raw_headers,
        referer_override=referer,
        origin_override=origin,
        skip_augment=no_header_fix,
        attach_bearer=jwt_bearer,
    )
    headers = prepare_assembly_post_headers(headers, raw_json_len=len(payload))
    url = build_assembly_url()
    status, _rh, body = fetch_common.fetch_body(
        url, "POST", headers, timeout, data=post_bytes
    )
    if status >= 400:
        preview = body[:800].decode("utf-8", errors="replace")
        raise RuntimeError(f"assemblyattach HTTP {status}，响应前缀:\n{preview}")
    plain = decrypt_assembly_response(body)
    root = json.loads(plain)
    if not isinstance(root, dict):
        raise ValueError("assembly 解密结果应为 JSON 对象")
    return root


def export_parammodel_param_current_value_by_bgid(
    bg_id: int | str,
    output_path: Path | str | None = None,
    *,
    status_file: Path | str | None = None,
    timeout: float = 60.0,
    jwt_bearer: bool = False,
    zstd_level: int = 1,
    referer: str | None = None,
    origin: str | None = None,
    no_header_fix: bool = False,
) -> dict[str, Any]:
    """
    按组合柜 bgId/obsBrandGoodId 拉取 assemblyattach，并写出 current-value 参数 JSON。

    默认写入 workspace/tmp/input/param_current.json。
    返回 payload 与写入路径，便于 UI/脚本复用。
    """
    dest = Path(output_path) if output_path is not None else DEFAULT_PARAMMODEL_PARAM_CURRENT_VALUE_PATH
    status_path = Path(status_file) if status_file is not None else DEFAULT_STATUS_FILE
    brand_good_id = _resolve_brand_good_id(bg_id)
    asm_root = _fetch_assembly_json(
        status_path,
        brand_good_id,
        timeout=timeout,
        jwt_bearer=jwt_bearer,
        zstd_level=zstd_level,
        referer=referer,
        origin=origin,
        no_header_fix=no_header_fix,
    )
    payload = build_parammodel_param_list_payload(asm_root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return {
        "payload": payload,
        "output_path": str(dest.resolve()),
        "brand_good_id": brand_good_id,
    }


def _headers_for_image_get(base_headers: dict[str, str]) -> dict[str, str]:
    """尽量沿用登录 Cookie，避免 OSS 403。"""
    h: dict[str, str] = {"Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
    for key in ("Cookie", "User-Agent", "Referer", "Origin"):
        _nk, v = fetch_common._find_header(base_headers, key.lower())
        if v:
            h[key] = v
    if "Referer" not in h:
        h["Referer"] = fetch_common.DCS_SEARCH_FALLBACK_REFERER
    return h


def _suffix_from_response(url: str, content_type: str | None) -> str:
    url_path = url.split("?", 1)[0].lower()
    for suf in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        if url_path.endswith(suf):
            return suf
    if content_type:
        ext = mimetypes.guess_extension(content_type.split(";")[0].strip().lower())
        if ext == ".jpe":
            ext = ".jpg"
        if ext:
            return ext
    return ".png"


def download_cover_image_to_file(
    url: str,
    status_file: Path | None,
    dest_stem: Path,
    *,
    timeout: float,
    jwt_bearer: bool,
    referer: str | None,
    origin: str | None,
    no_header_fix: bool,
) -> Path:
    """下载封面图到 dest_stem + 推断后缀，返回写入的文件路径。"""
    raw_headers = _load_auth_request_headers(status_file)
    base = fetch_common.prepare_bgcollections_headers(
        raw_headers,
        referer_override=referer,
        origin_override=origin,
        skip_augment=no_header_fix,
        attach_bearer=jwt_bearer,
    )
    img_headers = _headers_for_image_get(base)
    status, rh, body = fetch_common.fetch_body(url, "GET", img_headers, timeout)
    if status >= 400:
        frag = body[:400].decode("utf-8", errors="replace")
        raise RuntimeError(f"封面图 GET HTTP {status}，前缀:\n{frag}")
    ct = rh.get("Content-Type") if rh else None
    suf = _suffix_from_response(url, ct)
    dest_path = dest_stem.with_suffix(suf)
    dest_path.write_bytes(body)
    return dest_path


def export_assembly_abd_bundle(
    status_file: Path,
    folder_id: str,
    brand_good_id: int,
    output_dir: Path,
    *,
    foldertype: int = 4,
    timeout: float = 60.0,
    jwt_bearer: bool = False,
    zstd_level: int = 1,
    referer: str | None = None,
    origin: str | None = None,
    no_header_fix: bool = False,
    skip_cover_download: bool = False,
    ignore_cover_download_errors: bool = False,
) -> dict[str, Any]:
    """
    使用 status.json 拉取 bgcollections + assemblyattach，写入 abd.json、parammodel_param_list.json、assembly.json；可选下载封面图。
    返回 abd 对象及各文件绝对路径字符串。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    fid = str(folder_id).strip()
    rows = _collect_goods_pages(
        status_file,
        fid,
        foldertype=foldertype,
        timeout=timeout,
        jwt_bearer=jwt_bearer,
        referer=referer,
        origin=origin,
        no_header_fix=no_header_fix,
    )
    coll_row = _find_row_for_bg(rows, brand_good_id)
    if coll_row is None:
        raise LookupError(
            f"在该目录下未找到 brandGoodId={brand_good_id}（共 {len(rows)} 条）。"
        )

    asm_root = _fetch_assembly_json(
        status_file,
        brand_good_id,
        timeout=timeout,
        jwt_bearer=jwt_bearer,
        zstd_level=zstd_level,
        referer=referer,
        origin=origin,
        no_header_fix=no_header_fix,
    )

    assembly_path = output_dir / "assembly.json"
    assembly_path.write_text(
        json.dumps(asm_root, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    abd = build_abd_payload(
        collection_row=coll_row,
        assembly_root=asm_root,
        brand_good_id=brand_good_id,
    )

    abd_path = output_dir / "abd.json"
    abd_path.write_text(
        json.dumps(abd, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    param_list_payload = build_parammodel_param_list_payload(asm_root)
    param_list_path = output_dir / "parammodel_param_list.json"
    param_list_path.write_text(
        json.dumps(param_list_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    cover_path_resolved: str | None = None
    cover_error: str | None = None
    cover_url = _pick_cover_image_url(coll_row)
    if (
        not skip_cover_download
        and isinstance(cover_url, str)
        and cover_url.strip()
    ):
        try:
            dest_file = download_cover_image_to_file(
                cover_url.strip(),
                status_file,
                output_dir / "cover",
                timeout=timeout,
                jwt_bearer=jwt_bearer,
                referer=referer,
                origin=origin,
                no_header_fix=no_header_fix,
            )
            cover_path_resolved = str(dest_file.resolve())
        except Exception as e:
            if not ignore_cover_download_errors:
                raise
            cover_error = str(e)

    out: dict[str, Any] = {
        "abd": abd,
        "output_dir": str(output_dir.resolve()),
        "abd_json_path": str(abd_path.resolve()),
        "parammodel_param_list_json_path": str(param_list_path.resolve()),
        "assembly_json_path": str(assembly_path.resolve()),
        "cover_image_path": cover_path_resolved,
    }
    if cover_error:
        out["cover_download_error"] = cover_error
    return out


def build_abd_payload(
    *,
    collection_row: dict[str, Any] | None,
    assembly_root: dict[str, Any],
    brand_good_id: int | None = None,
    resolve_unit_model_names: bool = True,
) -> dict[str, Any]:
    pms = _resolve_assembly_param_models(assembly_root)

    coll_name: str | None = None
    if collection_row:
        n = collection_row.get("name")
        if isinstance(n, str) and n.strip():
            coll_name = n.strip()

    attached_by_id = _param_model_attached_by_id(assembly_root)
    param_nodes = [_merge_param_model_metadata(pm, attached_by_id) for pm in pms if isinstance(pm, dict)]
    pm_by_id = {pm.get("id"): pm for pm in param_nodes if isinstance(pm.get("id"), str)}
    accessory_main_by_id = _accessory_main_id_by_id(assembly_root)

    obs_for_names: set[str] = set()
    for pm in param_nodes:
        obs = _ABD_BRAND_GOOD_CRYPT.encrypt(_coerce_brand_good_id(pm.get("brandGoodId")))
        if isinstance(obs, str) and obs:
            obs_for_names.add(obs)
    model_name_by_obs: dict[str, str] = (
        _resolve_model_brand_good_names(obs_for_names) if resolve_unit_model_names else {}
    )

    units = []
    for pm in param_nodes:
        pm_id = pm.get("id")
        main_node = None
        unit_id = pm_id if isinstance(pm_id, str) else None
        if isinstance(pm_id, str):
            main_node = pm_by_id.get(accessory_main_by_id.get(pm_id))
        obs = _ABD_BRAND_GOOD_CRYPT.encrypt(_coerce_brand_good_id(pm.get("brandGoodId")))
        model_name = model_name_by_obs.get(obs) if isinstance(obs, str) else None
        units.append(
            _transform_param_node(
                pm,
                main_node=main_node,
                unit_id=unit_id,
                model_brand_good_name=model_name,
            )
        )

    asm_name_s: str | None = None
    ada = assembly_root.get("assemblyDataAndAttach")
    if isinstance(ada, dict):
        adata = ada.get("assemblyData")
        if isinstance(adata, dict):
            asm_name = adata.get("name")
            asm_name_s = asm_name if isinstance(asm_name, str) else None

    payload: dict[str, Any] = {"name": asm_name_s or coll_name}
    obs_collect = _obs_collect_brand_good_id(collection_row, brand_good_id)
    if obs_collect:
        payload["obsCollectBrandGoodId"] = obs_collect
    payload["units"] = units
    return payload


def main() -> None:
    p = argparse.ArgumentParser(
        description="按 folderId + brandGoodId 生成 abd.json 并下载封面图",
    )
    p.add_argument("folder_id", help="收藏夹目录 ID（bgcollections folderid）")
    p.add_argument("brand_good_id", type=int, help="商品 brandGoodId（与 assembly 请求 bgId 一致）")
    p.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        required=True,
        help="输出目录（写入 abd.json、parammodel_param_list.json、assembly.json 与 cover.*）",
    )
    p.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_FILE,
        help="登录状态 status.json 路径（默认 data-tools/utils/login/status.json）",
    )
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("--foldertype", type=int, default=4)
    p.add_argument(
        "-l",
        "--level",
        type=int,
        default=1,
        help="assembly 请求体 Zstd 等级（默认 1）",
    )
    p.add_argument("--jwt-bearer", action="store_true")
    p.add_argument("--referer", type=str, default=None)
    p.add_argument("--origin", type=str, default=None)
    p.add_argument("--no-header-fix", action="store_true")
    p.add_argument(
        "--skip-cover-download",
        "--skip-preview-download",
        action="store_true",
        dest="skip_cover_download",
        help="仅写 abd.json，不下载封面图（--skip-preview-download 为兼容旧参数）",
    )
    args = p.parse_args()

    status_file: Path = args.status_file
    if not status_file.is_file():
        print(f"找不到登录状态文件: {status_file}", file=sys.stderr)
        sys.exit(2)

    out_dir: Path = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    folder_id = str(args.folder_id).strip()
    bg_id = int(args.brand_good_id)

    print(
        f"导出 folderid={folder_id} brandGoodId={bg_id} → {out_dir} （status={status_file}）…",
        file=sys.stderr,
    )
    try:
        result = export_assembly_abd_bundle(
            status_file,
            folder_id,
            bg_id,
            out_dir,
            foldertype=args.foldertype,
            timeout=args.timeout,
            jwt_bearer=args.jwt_bearer,
            zstd_level=args.level,
            referer=args.referer,
            origin=args.origin,
            no_header_fix=args.no_header_fix,
            skip_cover_download=args.skip_cover_download,
        )
    except LookupError as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"导出失败: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"已写入: {result['abd_json_path']}", file=sys.stderr)
    print(f"已写入: {result['assembly_json_path']}", file=sys.stderr)
    print(f"已写入: {result['parammodel_param_list_json_path']}", file=sys.stderr)
    if args.skip_cover_download:
        print("已跳过封面图下载（--skip-cover-download）", file=sys.stderr)
    elif not result.get("cover_image_path"):
        print("未找到封面图 URL，跳过下载", file=sys.stderr)
    else:
        print(f"已下载封面图: {result['cover_image_path']}", file=sys.stderr)


if __name__ == "__main__":
    main()
