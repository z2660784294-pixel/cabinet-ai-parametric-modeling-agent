"""Fetch param model library data via direct HTTP APIs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import requests

from login import prepare_headers_from_status

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
_PARAMS_MAP_PATH = Path(__file__).resolve().parent / "params_map.json"
DEFAULT_BRAND_GOOD_STAGES = [0, 1, 2]
DEFAULT_PAGE_SIZE = 100

_PARAMS_MAP_CACHE: dict[str, str] | None = None


def _load_params_map() -> dict[str, str]:
    global _PARAMS_MAP_CACHE
    if _PARAMS_MAP_CACHE is not None:
        return _PARAMS_MAP_CACHE
    if _PARAMS_MAP_PATH.exists():
        with _PARAMS_MAP_PATH.open(encoding="utf-8") as f:
            _PARAMS_MAP_CACHE = json.load(f)
    else:
        _PARAMS_MAP_CACHE = {}
    return _PARAMS_MAP_CACHE


class ApiError(RuntimeError):
    pass


def load_config() -> dict[str, Any]:
    path = CONFIG_FILE
    if not path.is_file():
        raise FileNotFoundError(f"config file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _unwrap_response(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    if "c" in data or "code" in data:
        code = data.get("c", data.get("code"))
        if str(code) != "0":
            message = data.get("m") or data.get("message") or "API request failed"
            raise ApiError(str(message))
        return data.get("d", data.get("data"))
    return data


def _build_headers(config: dict[str, Any]) -> dict[str, str]:
    headers = prepare_headers_from_status()
    headers["Accept"] = "*/*"
    headers["x-qh-locale"] = str(config.get("locale") or "zh_CN")
    headers["editor-locale"] = str(config.get("locale") or "zh_CN")
    headers["x-qh-site"] = "kujiale"
    return headers


def _api_get(
    config: dict[str, Any],
    path: str,
    params: dict[str, Any] | None = None,
    *,
    session: requests.Session | None = None,
) -> Any:
    base_url = str(config.get("apiBaseUrl") or "https://yun-beta.kujiale.com").rstrip("/")
    url = f"{base_url}{path}"
    headers = _build_headers(config)
    client = session or requests
    try:
        resp = client.get(url, params=params, headers=headers, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ApiError(f"GET {path} failed: {exc}") from exc
    return _unwrap_response(resp.json())


def _obs_id_to_id(nodes: list[dict[str, Any]]) -> None:
    for item in nodes:
        children = item.get("children")
        if isinstance(children, list) and children:
            _obs_id_to_id(children)
        obs_id = item.get("obsId")
        if obs_id and not item.get("id"):
            item["id"] = obs_id


def _fetch_catalogue_tree_raw(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    tool_type_pos = config.get("toolTypePos")
    if tool_type_pos is None:
        raise ApiError("config.toolTypePos is required")

    tool_type_pos = int(tool_type_pos)
    library_id = config.get("libraryId") or None
    scene_id = config.get("sceneId")

    if tool_type_pos == 1:
        data = _api_get(config, "/bgs/businesscat", {"library": tool_type_pos})
        if not isinstance(data, list):
            raise ApiError("unexpected /bgs/businesscat response")
        _obs_id_to_id(data)
        return {"general_model": data}

    params: dict[str, Any] = {
        "newcat": "true",
        "pos": tool_type_pos,
    }
    if library_id:
        params["libraryId"] = library_id
    if scene_id is not None:
        params["sceneId"] = scene_id

    data = _api_get(config, "/editor/api/site/businesscat", params)
    if not isinstance(data, dict):
        raise ApiError("unexpected /editor/api/site/businesscat response")
    return data


def _filter_catalogue_node(node: dict[str, Any]) -> dict[str, Any]:
    filtered: dict[str, Any] = {
        "id": node.get("id") or node.get("obsId") or "",
        "n": node.get("name") or "",
    }
    children = node.get("children")
    if isinstance(children, list) and children:
        filtered["kids"] = [_filter_catalogue_node(child) for child in children if isinstance(child, dict)]
    return filtered


def get_catalogue_tree() -> dict[str, Any]:
    config = load_config()
    catalogue_data_map = _fetch_catalogue_tree_raw(config)
    position_descriptions = config.get("positionDescriptions") or {}

    filtered_result: dict[str, Any] = {
        "meta": {
            "catalogueLibraryDescs": [
                {
                    "key": key,
                    "desc": position_descriptions.get(key, key),
                }
                for key in catalogue_data_map
            ],
            "toolType": config.get("toolType"),
            "locale": config.get("locale") or "zh_CN",
        }
    }

    for key, nodes in catalogue_data_map.items():
        if not isinstance(nodes, list):
            continue
        filtered_result[key] = [
            _filter_catalogue_node(node) for node in nodes if isinstance(node, dict)
        ]

    return filtered_result


def _fetch_brand_goods_by_category(
    config: dict[str, Any],
    category_id: str,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    tool_type_pos = int(config["toolTypePos"])
    library_id = config.get("libraryId") or None
    stages = config.get("brandGoodStages") or DEFAULT_BRAND_GOOD_STAGES

    all_products: list[dict[str, Any]] = []
    start = 0
    has_more = True

    while has_more:
        params: dict[str, Any] = {
            "pos": tool_type_pos,
            "cat": category_id,
            "start": start,
            "num": DEFAULT_PAGE_SIZE,
        }
        if library_id:
            params["libraryId"] = library_id
        if stages:
            params["stage"] = stages

        data = _api_get(
            config,
            "/editor/api/site/brandgood",
            params,
            session=session,
        )
        if not isinstance(data, dict):
            raise ApiError("unexpected /editor/api/site/brandgood response")

        products = data.get("products") or []
        total_count = int(data.get("totalCount") or 0)
        if products:
            for product in products:
                if not isinstance(product, dict):
                    continue
                all_products.append(
                    {
                        "obsBrandGoodId": product.get("obsBrandGoodId"),
                        "name": product.get("name"),
                        "previewImgUrl": product.get("previewImgUrl"),
                    }
                )
            start += DEFAULT_PAGE_SIZE
            has_more = start < total_count
        else:
            has_more = False

    return all_products


def get_products_by_categories(category_ids: list[str]) -> list[dict[str, Any]]:
    if not category_ids:
        return []

    config = load_config()
    session = requests.Session()
    results: list[dict[str, Any]] = []
    for category_id in category_ids:
        products = _fetch_brand_goods_by_category(config, category_id, session=session)
        results.append({"categoryId": category_id, "products": products})
    return results


def _fetch_product_parameters(
    config: dict[str, Any],
    brand_good_id: str,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    tool_type = str(config.get("toolType") or "")
    if not tool_type:
        raise ApiError("config.toolType is required")

    params = {
        "obsbrandgoodid": brand_good_id,
        "doupdate": "false",
        "tooltype": tool_type,
    }
    try:
        data = _api_get(config, "/editor/api/site/editordata", params, session=session)
    except ApiError:
        return {"obsBrandGoodId": brand_good_id, "inputs": []}

    if not isinstance(data, dict):
        return {"obsBrandGoodId": brand_good_id, "inputs": []}

    editor_data = data.get("editorData") or {}
    inputs_raw = editor_data.get("inputs") or []
    inputs: list[dict[str, Any]] = []
    for item in inputs_raw:
        if not isinstance(item, dict):
            continue
        entry: dict[str, Any] = {
            "paramName": item.get("paramName"),
            "displayName": item.get("displayName"),
            "value": item.get("value"),
            "valueType": item.get("valueType"),
        }
        param_min = item.get("min")
        if param_min is not None and param_min != "":
            entry["min"] = param_min
        param_max = item.get("max")
        if param_max is not None and param_max != "":
            entry["max"] = param_max
        param_link = item.get("link")
        if param_link is not None and param_link != "":
            entry["link"] = param_link
        param_link_form = item.get("linkForm")
        if param_link_form is not None and param_link_form != "":
            entry["linkForm"] = param_link_form
        param_formula = item.get("formula")
        if param_formula is not None and param_formula != "":
            entry["formula"] = param_formula
        param_formula_form = item.get("formulaForm")
        if param_formula_form is not None and param_formula_form != "":
            entry["formulaForm"] = param_formula_form
        inputs.append(entry)
    return {"obsBrandGoodId": brand_good_id, "inputs": inputs}


def get_products_parameters(brand_good_ids: list[str]) -> list[dict[str, Any]]:
    if not brand_good_ids:
        return []

    config = load_config()
    session = requests.Session()
    results = [
        _fetch_product_parameters(config, brand_good_id, session=session)
        for brand_good_id in brand_good_ids
    ]
    params_map = _load_params_map()
    if params_map:
        for result in results:
            inputs = result.get("inputs")
            if isinstance(inputs, list):
                for param in inputs:
                    if isinstance(param, dict):
                        name = param.get("paramName")
                        if name in params_map:
                            param["paramName"] = params_map[name]
    return results

def get_product_info_by_brand_good_id(
    brand_good_id: str,
) -> dict[str, Any] | None:
    config = load_config()
    session = requests.Session()
    params = {
        "obsbrandgoodid": brand_good_id,
        "doupdate": "false",
        "tooltype": str(config.get("toolType") or ""),
    }
    data = _api_get(config, "/editor/api/site/editordata", params, session=session)
    if not isinstance(data, dict):
        return None
    model = data.get("model")
    if isinstance(model, dict):
        return model


def _api_post(
    config: dict[str, Any],
    path: str,
    json_body: Any,
    params: dict[str, Any] | None = None,
    *,
    session: requests.Session | None = None,
) -> Any:
    """POST with Content-Type: text/plain; charset=utf-8, body is JSON-serialised text."""
    base_url = str(config.get("apiBaseUrl") or "https://yun-beta.kujiale.com").rstrip("/")
    url = f"{base_url}{path}"
    headers = _build_headers(config)
    headers["Content-Type"] = "text/plain; charset=utf-8"
    client = session or requests
    body = json.dumps(json_body, ensure_ascii=False).encode("utf-8")
    try:
        resp = client.post(url, data=body, params=params, headers=headers, timeout=120)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise ApiError(f"POST {path} failed: {exc}") from exc
    return _unwrap_response(resp.json())


def _fetch_brand_good_root(
    config: dict[str, Any],
    brand_good_id: str,
    *,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    """GET /editor/api/site/editordata and return the unwrapped root dict.

    The returned dict contains at minimum: editorData, model, prodCatId.
    """
    tool_type = str(config.get("toolType") or "")
    if not tool_type:
        raise ApiError("config.toolType is required")
    params = {
        "obsbrandgoodid": brand_good_id,
        "doupdate": "false",
        "tooltype": tool_type,
    }
    data = _api_get(config, "/editor/api/site/editordata", params, session=session)
    if not isinstance(data, dict):
        raise ApiError(f"unexpected editordata response for {brand_good_id}")
    return data


def fetch_brand_good_root(brand_good_id: str) -> dict[str, Any]:
    """Public wrapper: GET editordata root dict (editorData, model, prodCatId)."""
    config = load_config()
    return _fetch_brand_good_root(config, brand_good_id)


def get_product_preview_img_url(brand_good_id: str) -> str | None:
    """Return model.previewImgUrl for a BGID via GET /editor/api/site/editordata."""
    root = fetch_brand_good_root(brand_good_id)
    model = root.get("model")
    if not isinstance(model, dict):
        return None
    url = model.get("previewImgUrl")
    return str(url) if url else None


_VALID_DATA_TYPES = frozenset({"EditorData", "ParamModel", "ParamModelAttached"})


def get_model_data(
    brand_good_id: str,
    data_types: tuple[str, ...] | list[str] = ("EditorData", "ParamModel"),
) -> dict[str, Any]:
    """Fetch model intermediate data for a BGID.

    data_types: subset of ("EditorData", "ParamModel", "ParamModelAttached").
    Returns dict with keys EditorData, ParamModel, ParamModelAttached (None when not requested),
    plus an "errors" dict for per-type failures (mirrors frontend behaviour: one failure does
    not block the others).

    API mapping (mirrors febu-parameditor mcp/tools/index.ts getModelData):
      EditorData        <- GET  /editor/api/site/editordata
      ParamModel        <- POST /editor/api/site/3d?prodcatid=<prodCatId>   body=editorData (text/plain)
      ParamModelAttached<- POST /editor/api/site/attach/flattened?prodcatid body=editorData (text/plain)
    """
    requested = list(data_types) if data_types else ["EditorData", "ParamModel"]
    for t in requested:
        if t not in _VALID_DATA_TYPES:
            raise ApiError(
                f"invalid data_type '{t}', must be one of: {sorted(_VALID_DATA_TYPES)}"
            )

    config = load_config()
    session = requests.Session()
    root = _fetch_brand_good_root(config, brand_good_id, session=session)
    editor_data = root.get("editorData")
    prod_cat_id = root.get("prodCatId")

    result: dict[str, Any] = {
        "EditorData": None,
        "ParamModel": None,
        "ParamModelAttached": None,
        "errors": {},
    }

    if "EditorData" in requested:
        result["EditorData"] = editor_data

    if "ParamModel" in requested:
        if editor_data is None or prod_cat_id is None:
            result["errors"]["ParamModel"] = "editorData or prodCatId missing from editordata response"
        else:
            try:
                result["ParamModel"] = _api_post(
                    config,
                    "/editor/api/site/3d",
                    editor_data,
                    {"prodcatid": prod_cat_id},
                    session=session,
                )
            except Exception as exc:
                result["errors"]["ParamModel"] = str(exc)

    if "ParamModelAttached" in requested:
        if editor_data is None or prod_cat_id is None:
            result["errors"]["ParamModelAttached"] = "editorData or prodCatId missing from editordata response"
        else:
            try:
                result["ParamModelAttached"] = _api_post(
                    config,
                    "/editor/api/site/attach/flattened",
                    editor_data,
                    {"prodcatid": prod_cat_id},
                    session=session,
                )
            except Exception as exc:
                result["errors"]["ParamModelAttached"] = str(exc)

    return result
