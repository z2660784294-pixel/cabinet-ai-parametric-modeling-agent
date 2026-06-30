"""
Fetch design parameters from param-platform API.

This module provides functionality to fetch current parameter values from a design
by calling the param-platform APIs with zstd decompression support.
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# Add parent directories to path for imports
UTILS_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "data-tools" / "utils"
FETCH_FAVORITE_ASSEMBLY_DIR = UTILS_DIR / "fetch_favorite_assembly"

if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))
if str(FETCH_FAVORITE_ASSEMBLY_DIR) not in sys.path:
    sys.path.insert(0, str(FETCH_FAVORITE_ASSEMBLY_DIR))

try:
    from login import DEFAULT_STATUS_FILE, prepare_headers_from_status
    import fetch_common
    from crypt_zstd import decrypt_body_base64, encrypt_body_to_base64
    from param_value_normalize import brand_good_id_to_obs, format_param_value_for_export
except ImportError as e:
    # If running from test, provide a helpful error
    raise ImportError(
        f"Failed to import required modules: {e}. "
        "Make sure you're running from the workspace root and data-tools/utils is in the path."
    ) from e

# API endpoints
DESIGN_HOME_API = "https://param-platform-ui-prod.qunhequnhe.com/param-platform/api/site/design-info/home"
DESIGN_META_API = "https://param-platform-ui-prod.qunhequnhe.com/param-platform/api/site/design-info/meta"
DESIGN_CUSTOM_PACKETS_API = "https://param-platform-ui-prod.qunhequnhe.com/param-platform/api/site/design-info/custom-packets"


def _load_auth_headers(status_file: Path | None = None) -> dict[str, str]:
    """Load authentication headers from status file."""
    raw_headers = prepare_headers_from_status(status_file or DEFAULT_STATUS_FILE)
    fetch_common.warn_if_qunhe_jwt_stale(raw_headers)
    
    # Add Accept header for JSON responses
    raw_headers["Accept"] = "application/json, text/plain, */*"
    
    return raw_headers


def _make_api_request(
    url: str,
    headers: dict[str, str],
    timeout: float = 60.0,
    *,
    post_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Make HTTP request to API and decrypt zstd response.
    
    Args:
        url: The API URL to call
        headers: Request headers including authentication
        timeout: Request timeout in seconds
        post_data: Optional POST data (will be zstd-compressed if provided)
        
    Returns:
        Decrypted JSON response as dictionary
        
    Raises:
        ValueError: If request fails or response is invalid
    """
    try:
        if post_data is not None:
            # Use POST with zstd-compressed body
            json_bytes = json.dumps(post_data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            compressed_b64 = encrypt_body_to_base64(json_bytes)
            
            # Update headers for POST request
            headers = dict(headers)
            headers["Content-Type"] = "application/zstd;charset=UTF-8"
            headers["x-raw-data-length"] = str(len(json_bytes))
            headers["Accept"] = "application/zstd;charset=UTF-8"
            
            req = urllib.request.Request(url, data=compressed_b64.encode("utf-8"), headers=headers, method="POST")
        else:
            # Use GET request
            req = urllib.request.Request(url, headers=headers, method="GET")
        
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            
        # Try to decrypt as zstd
        try:
            decrypted_bytes = decrypt_body_base64(body.decode("utf-8"))
            response_text = decrypted_bytes.decode("utf-8")
        except Exception:
            # If zstd decryption fails, try as plain text
            response_text = body.decode("utf-8")
            
        response_data = json.loads(response_text)
        
        # Check API response format
        if not isinstance(response_data, dict):
            raise ValueError(f"Invalid response format: expected dict, got {type(response_data)}")
            
        if response_data.get("c") != "0":
            error_msg = response_data.get("m", "Unknown error")
            raise ValueError(f"API error: {error_msg}")
            
        return response_data.get("d", {})
        
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"HTTP {e.code}: {error_body[:200]}") from e
    except urllib.error.URLError as e:
        raise ValueError(f"Network error: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to parse JSON response: {e}") from e


def get_design_level_id(
    design_id: str,
    status_file: Path | None = None,
    timeout: float = 60.0,
) -> str | None:
    """
    Get the first level ID for a design.
    
    Args:
        design_id: The design ID
        status_file: Path to status file for authentication
        timeout: Request timeout in seconds
        
    Returns:
        The first level ID, or None if not found
        
    Raises:
        ValueError: If API request fails
    """
    headers = _load_auth_headers(status_file)
    headers = fetch_common.augment_headers_for_dcs_search(headers)
    
    # Use GET request with URL parameters
    params = f"designId={design_id}&compress=0"
    url = f"{DESIGN_HOME_API}?{params}"
    
    # Add required headers for param-platform API
    headers["Accept"] = "application/zstd"
    headers["Content-Type"] = "application/zstd"
    headers["x-tool-gzip"] = "1"
    
    data = _make_api_request(url, headers, timeout)
    
    # Get first overground level
    overground_levels = data.get("overgroundLevels", [])
    if overground_levels and isinstance(overground_levels, list):
        return overground_levels[0]
    
    # Fallback to levelInfos
    level_infos = data.get("levelInfos", [])
    if level_infos and isinstance(level_infos, list):
        return level_infos[0].get("levelId")
    
    return None


def get_design_param_model_ids(
    design_id: str,
    level_id: str,
    combination_id: str,
    status_file: Path | None = None,
    timeout: float = 60.0,
) -> list[str]:
    """
    Get param model IDs for a combination in a design.
    
    Args:
        design_id: The design ID
        level_id: The level ID
        combination_id: The combination model ID (from abd.json)
        status_file: Path to status file for authentication
        timeout: Request timeout in seconds
        
    Returns:
        List of param model IDs for the combination
        
    Raises:
        ValueError: If API request fails or combination not found
    """
    headers = _load_auth_headers(status_file)
    headers = fetch_common.augment_headers_for_dcs_search(headers)
    
    # Use GET request with URL parameters
    params = f"designId={design_id}&toolType=1&levelId={level_id}&compress=0"
    url = f"{DESIGN_META_API}?{params}"
    
    # Add required headers for param-platform API
    headers["Accept"] = "application/zstd"
    headers["Content-Type"] = "application/zstd"
    headers["x-tool-gzip"] = "1"
    
    data = _make_api_request(url, headers, timeout)
    
    # Find the combination by ID
    home_design_data = data.get("homeDesignData", {})
    param_model_combinations = home_design_data.get("paramModelCombinations", [])
    
    for combo in param_model_combinations:
        if combo.get("id") == combination_id:
            param_model_ids = combo.get("paramModelIds", [])
            if isinstance(param_model_ids, list):
                return param_model_ids
    
    raise ValueError(f"Combination {combination_id} not found in design {design_id}")


def get_design_custom_packets(
    design_id: str,
    level_id: str,
    status_file: Path | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Get custom packets (parameters) for a design.
    
    Note: This API requires POST request with zstd-compressed body containing entityVersionMappings.
    
    Args:
        design_id: The design ID
        level_id: The level ID
        status_file: Path to status file for authentication
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary containing paramModels with their parameters, plus entityVersionMappings
        
    Raises:
        ValueError: If API request fails
    """
    headers = _load_auth_headers(status_file)
    headers = fetch_common.augment_headers_for_dcs_search(headers)
    
    # First, get the meta data to obtain entityVersionMappings
    meta_params = f"designId={design_id}&toolType=1&levelId={level_id}&compress=0"
    meta_url = f"{DESIGN_META_API}?{meta_params}"
    
    # Add required headers for param-platform API
    headers["Accept"] = "application/zstd"
    headers["Content-Type"] = "application/zstd"
    headers["x-tool-gzip"] = "1"
    
    # Get meta data
    meta_data = _make_api_request(meta_url, headers, timeout)
    
    # Extract entityVersionMappings from meta data
    home_design_data = meta_data.get("homeDesignData", {})
    entity_version_mappings = home_design_data.get("entityVersionMappings", [])
    
    if not entity_version_mappings:
        raise ValueError(f"No entityVersionMappings found for design {design_id}")
    
    # Now call custom-packets API with entityVersionMappings as body
    params = f"designId={design_id}&toolType=1&levelId={level_id}&compress=0"
    url = f"{DESIGN_CUSTOM_PACKETS_API}?{params}"
    
    # POST request with entityVersionMappings as body
    data = _make_api_request(url, headers, timeout, post_data=entity_version_mappings)
    
    # Include entityVersionMappings in the result for ID mapping
    data["_entityVersionMappings"] = entity_version_mappings
    
    return data


def _build_current_value_model_entry(
    obs_brand_good_id: str,
    inputs: list[dict[str, Any]],
    unit_id: str | None = None,
    *,
    name: str | None = None,
) -> dict[str, Any]:
    """Build a model entry with keys ordered: obsBrandGoodId, name, id, inputs."""
    entry: dict[str, Any] = {"obsBrandGoodId": obs_brand_good_id}
    if name:
        entry["name"] = name
    if unit_id:
        entry["id"] = unit_id
    entry["inputs"] = inputs
    return entry


def _abd_unit_ids_by_obs_ordered(abd_units: list[dict[str, Any]] | None) -> dict[str, list[str]]:
    """Map obsBrandGoodId to abd.json unit ids, preserving duplicate order."""
    groups: dict[str, list[str]] = {}
    if not abd_units:
        return groups
    for unit in abd_units:
        if not isinstance(unit, dict):
            continue
        obs_id = unit.get("obsBrandGoodId")
        unit_id = unit.get("id")
        if isinstance(obs_id, str) and obs_id and isinstance(unit_id, str) and unit_id:
            groups.setdefault(obs_id, []).append(unit_id)
    return groups


def _abd_unit_ids_by_obs_and_name_ordered(
    abd_units: list[dict[str, Any]] | None,
) -> dict[tuple[str, str], list[str]]:
    """Map (obsBrandGoodId, name) to abd.json unit ids, preserving duplicate order."""
    groups: dict[tuple[str, str], list[str]] = {}
    if not abd_units:
        return groups
    for unit in abd_units:
        if not isinstance(unit, dict):
            continue
        obs_id = unit.get("obsBrandGoodId")
        unit_id = unit.get("id")
        name = unit.get("name")
        if (
            isinstance(obs_id, str)
            and obs_id
            and isinstance(unit_id, str)
            and unit_id
            and isinstance(name, str)
            and name
        ):
            groups.setdefault((obs_id, name), []).append(unit_id)
    return groups


def _obs_to_unit_id_from_abd_units(abd_units: list[dict[str, Any]] | None) -> dict[str, str]:
    """Map obsBrandGoodId to the last abd.json unit id for that template.

    Deprecated for multi-instance designs; prefer ``_abd_unit_ids_by_obs_ordered``
    or ``entity_to_unit_id`` when exporting from a design.
    """
    mapping: dict[str, str] = {}
    for obs_id, unit_ids in _abd_unit_ids_by_obs_ordered(abd_units).items():
        if unit_ids:
            mapping[obs_id] = unit_ids[-1]
    return mapping


def _build_unit_id_to_obs_mapping(abd_units: list[dict[str, Any]] | None) -> dict[str, str]:
    """Map unit_id to obsBrandGoodId from abd.json units.
    
    This is the reverse mapping of _obs_to_unit_id_from_abd_units.
    """
    mapping: dict[str, str] = {}
    if not abd_units:
        return mapping
    for unit in abd_units:
        if not isinstance(unit, dict):
            continue
        obs_id = unit.get("obsBrandGoodId")
        unit_id = unit.get("id")
        if isinstance(obs_id, str) and obs_id and isinstance(unit_id, str) and unit_id:
            mapping[unit_id] = obs_id
    return mapping


def _param_current_unit_ids_already_match_abd(
    model_indices: list[int],
    models: list[Any],
    abd_unit_ids: list[str],
) -> bool:
    """True when each model index already has a distinct abd unit id in order."""
    if len(model_indices) != len(abd_unit_ids):
        return False
    seen: set[str] = set()
    for idx in model_indices:
        model = models[idx]
        if not isinstance(model, dict):
            return False
        unit_id = model.get("id")
        if not isinstance(unit_id, str) or not unit_id or unit_id not in abd_unit_ids:
            return False
        if unit_id in seen:
            return False
        seen.add(unit_id)
    return len(seen) == len(abd_unit_ids)


def enrich_parammodel_param_current_value_with_abd_unit_ids(
    payload: dict[str, Any],
    abd_units: list[dict[str, Any]] | None,
    *,
    match_by_obs_and_name: bool = False,
) -> dict[str, Any] | None:
    """Add abd.json unit ``id`` to each model entry.

    When the same ``obsBrandGoodId`` appears multiple times, models are paired with
    abd units by order of appearance in ``param_list`` and in ``abd_units``.

    Returns:
        Enriched payload if all models matched successfully.
        None if matching failed (数量不匹配 或 name 不匹配)，此时不应写入 param_current.json。
    """
    import sys
    from pathlib import Path as PathLib

    obs_to_unit_ids = _abd_unit_ids_by_obs_ordered(abd_units)
    if not obs_to_unit_ids:
        print(
            "warning: no units found in abd.json, cannot enrich param_current.json",
            file=sys.stderr,
        )
        return None
    obs_and_name_to_unit_ids = (
        _abd_unit_ids_by_obs_and_name_ordered(abd_units) if match_by_obs_and_name else {}
    )
    
    # Track matching failures
    failures: list[str] = []
    
    for category in payload.get("param_list", []):
        if not isinstance(category, dict):
            continue
        models = category.get("models", [])
        if not isinstance(models, list):
            continue
        models_by_obs: dict[str, list[int]] = {}
        for idx, model in enumerate(models):
            if not isinstance(model, dict):
                continue
            obs_id = model.get("obsBrandGoodId")
            if isinstance(obs_id, str) and obs_id in obs_to_unit_ids:
                models_by_obs.setdefault(obs_id, []).append(idx)
        for obs_id, model_indices in models_by_obs.items():
            abd_unit_ids = obs_to_unit_ids[obs_id]
            # Check if already matched
            if _param_current_unit_ids_already_match_abd(
                model_indices, models, abd_unit_ids
            ):
                continue
            # Check quantity mismatch
            if len(model_indices) != len(abd_unit_ids):
                failures.append(
                    f"obsBrandGoodId={obs_id}: param_current has {len(model_indices)} models, "
                    f"abd.json has {len(abd_unit_ids)} units"
                )
                continue
            used_unit_ids: set[str] = set()
            for i, model_idx in enumerate(model_indices):
                if i >= len(abd_unit_ids):
                    break
                model = models[model_idx]
                if not isinstance(model, dict):
                    continue
                inputs = model.get("inputs", [])
                if not isinstance(inputs, list):
                    inputs = []
                model_name = model.get("name")
                matched_unit_id: str | None = None
                if match_by_obs_and_name and isinstance(model_name, str) and model_name:
                    candidate_ids = obs_and_name_to_unit_ids.get((obs_id, model_name), [])
                    # Check if name can be matched
                    if not candidate_ids:
                        failures.append(
                            f"obsBrandGoodId={obs_id}: name '{model_name}' not found in abd.json"
                        )
                        continue
                    for candidate_id in candidate_ids:
                        if candidate_id not in used_unit_ids:
                            matched_unit_id = candidate_id
                            break
                    if matched_unit_id is None:
                        failures.append(
                            f"obsBrandGoodId={obs_id}: name '{model_name}' already matched"
                        )
                        continue
                if matched_unit_id is None:
                    matched_unit_id = abd_unit_ids[i]
                used_unit_ids.add(matched_unit_id)
                models[model_idx] = _build_current_value_model_entry(
                    obs_id,
                    inputs,
                    matched_unit_id,
                    name=model_name if isinstance(model_name, str) and model_name else None,
                )
    
    # If any failures, do not write param_current.json
    if failures:
        for fail_msg in failures:
            print(f"warning: param_current.json enrichment failed: {fail_msg}", file=sys.stderr)
        print(
            "warning: param_current.json not written due to enrichment failures",
            file=sys.stderr,
        )
        return None
    
    return payload


def build_parammodel_param_current_value(
    param_models_data: dict[str, Any],
    param_model_ids: list[str],
    *,
    entity_to_obs_id: dict[str, str] | None = None,
    obs_to_unit_id: dict[str, str] | None = None,
    entity_to_unit_id: dict[str, str] | None = None,
    entity_to_name: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Build param_current.json structure from API data.

    Args:
        param_models_data: The custom packets API response data (includes _entityVersionMappings)
        param_model_ids: List of param model IDs (entityIds from meta API) to include
        entity_to_obs_id: Optional mapping from entityId to the original obsBrandGoodId
                          (product template ID from abd.json). When provided, uses these
                          IDs instead of the entity UUIDs.
        obs_to_unit_id: Optional mapping from obsBrandGoodId to abd.json unit id.
                        DEPRECATED: Use entity_to_unit_id instead for proper multi-instance support.
        entity_to_unit_id: Optional mapping from entityId to abd.json unit id.
                          This is the preferred way to handle multiple instances of the same
                          product template (obsBrandGoodId).
        entity_to_name: Optional mapping from entityId to unit name from abd.json.

    Returns:
        Dictionary in param_current.json format
    """
    param_models_list = param_models_data.get("paramModels", [])
    entity_version_mappings = param_models_data.get("_entityVersionMappings", [])
    
    # Build mapping from entityId to revisionId
    # param_model_ids are entityIds from meta API
    # custom-packets API returns paramModels with revisionId as their id
    entity_to_revision = {evm["entityId"]: evm["revisionId"] for evm in entity_version_mappings}
    
    # Convert entityIds to revisionIds for matching
    target_revision_ids = {entity_to_revision.get(eid) for eid in param_model_ids}
    target_revision_ids.discard(None)  # Remove None values
    
    result = {"param_list": []}
    
    # Group by categoryId (use "unknown" if not available)
    category_map: dict[str, list[dict[str, Any]]] = {}
    
    for param_model in param_models_list:
        # param_model id is revisionId
        revision_id = param_model.get("id")
        if revision_id not in target_revision_ids:
            continue
            
        # Find the corresponding entityId for obsBrandGoodId
        entity_id = None
        for evm in entity_version_mappings:
            if evm["revisionId"] == revision_id:
                entity_id = evm["entityId"]
                break
        
        # Extract parameters from data.params
        data = param_model.get("data", {})
        params = data.get("params", [])
        inputs = []
        
        for param in params:
            param_name = param.get("name")
            param_value = param.get("value")
            param_type = param.get("type", "string")
            param_status = param.get("status", -1)
            param_paramTypeId = param.get("paramTypeId", "0")
            
            if param_name is None:
                continue
                
            # Map param types to valueType
            type_mapping = {
                "float": "float",
                "int": "int",
                "material": "material",
                "style": "style",
                "string": "string",
                "bool": "bool",
                "float3": "float3",
            }
            value_type = type_mapping.get(param_type, "string")
            
            # Convert value to export string (material/style: numeric bgId -> obsBrandGoodId)
            if param_value is not None:
                value_str = format_param_value_for_export(param_value, value_type)
            else:
                value_str = ""
            
            input_entry = {
                "paramName": param_name,
                "value": value_str,
                "valueType": value_type,
                "status": str(param_status),
                "paramTypeId": param_paramTypeId,
            }
            # Optionally include displayName, min, max when present in API response
            display_name = param.get("displayName")
            if display_name is not None:
                input_entry["displayName"] = display_name
            param_min = param.get("min")
            if param_min is not None and param_min != "":
                input_entry["min"] = param_min
            param_max = param.get("max")
            if param_max is not None and param_max != "":
                input_entry["max"] = param_max
            param_link = param.get("link")
            if param_link is not None and param_link != "":
                input_entry["link"] = param_link
            param_link_form = param.get("linkForm")
            if param_link_form is not None and param_link_form != "":
                input_entry["linkForm"] = param_link_form
            param_formula = param.get("formula")
            if param_formula is not None and param_formula != "":
                input_entry["formula"] = param_formula
            param_formula_form = param.get("formulaForm")
            if param_formula_form is not None and param_formula_form != "":
                input_entry["formulaForm"] = param_formula_form
            inputs.append(input_entry)
        
        if inputs:
            # Use "unknown" as categoryId since we don't have category info
            category_id = "unknown"
            if category_id not in category_map:
                category_map[category_id] = []
            
            # obsBrandGoodId: API brandGoodId (encrypted) > abd mapping > collectBrandGoodId > entityId
            if entity_to_obs_id and entity_id and entity_id in entity_to_obs_id:
                obs_brand_good_id = entity_to_obs_id[entity_id]
            else:
                obs_brand_good_id = (
                    brand_good_id_to_obs(data.get("brandGoodId"))
                    or data.get("collectBrandGoodId")
                    or entity_id
                    or revision_id
                )

            # id: entityId from entityVersionMappings (design instance UUID)
            if entity_to_unit_id and entity_id and entity_id in entity_to_unit_id:
                unit_id = entity_to_unit_id[entity_id]
            elif entity_id:
                unit_id = entity_id
            elif (
                obs_to_unit_id
                and isinstance(obs_brand_good_id, str)
                and obs_brand_good_id in obs_to_unit_id
            ):
                unit_id = obs_to_unit_id[obs_brand_good_id]
            else:
                unit_id = None
            
            # Resolve model name: prefer API data.name, then abd_units mapping
            model_name = data.get("name")
            if isinstance(model_name, str) and model_name.strip():
                model_name = model_name.strip()
            else:
                model_name = None
            if model_name is None and entity_to_name and entity_id and entity_id in entity_to_name:
                model_name = entity_to_name[entity_id]

            category_map[category_id].append(
                _build_current_value_model_entry(
                    str(obs_brand_good_id),
                    inputs,
                    unit_id,
                    name=model_name,
                )
            )
    
    # Build result structure
    for category_id, models in category_map.items():
        result["param_list"].append({
            "categoryId": category_id,
            "models": models,
        })
    
    return result


def export_parammodel_param_current_value_by_design(
    design_id: str,
    combination_id: str,
    output_path: Path | str | None = None,
    *,
    abd_units: list[dict[str, Any]] | None = None,
    status_file: Path | str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Export current parameter values for a design to param_current.json.
    
    This function:
    1. Gets the first level ID for the design
    2. Gets param model IDs for the specified combination
    3. Fetches custom packets (parameters) for the design
    4. Builds and writes the param_current.json file
    
    Args:
        design_id: The design ID (from abd.json)
        combination_id: The combination model ID (from abd.json)
        output_path: Output file path (default: workspace/tmp/input/param_current.json)
        abd_units: Optional list of unit dicts from abd.json (each with "obsBrandGoodId" and "id").
                   Used to map entity IDs back to product template IDs and preserve unit ids.
        status_file: Path to status file for authentication
        timeout: Request timeout in seconds
        
    Returns:
        Dictionary with payload, output_path, and metadata
        
    Raises:
        ValueError: If any step fails
    """
    # Step 1: Get level ID
    level_id = get_design_level_id(design_id, status_file, timeout)
    if level_id is None:
        raise ValueError(f"No level ID found for design {design_id}")
    
    # Step 2: Get param model IDs for the combination
    param_model_ids = get_design_param_model_ids(
        design_id, level_id, combination_id, status_file, timeout
    )
    
    if not param_model_ids:
        raise ValueError(f"No param model IDs found for combination {combination_id}")
    
    # Step 3: Get custom packets
    custom_packets = get_design_custom_packets(design_id, level_id, status_file, timeout)
    
    # Step 4: Build entity_id -> obsBrandGoodId and entity_id -> unit_id mappings from abd_units
    # IMPORTANT: param_model_ids and abd_units may NOT be in the same order!
    # We use entityVersionMappings to establish the correct mapping.
    # The entityId in entityVersionMappings matches the unit.id in abd_units.
    entity_to_obs_id: dict[str, str] | None = None
    entity_to_unit_id: dict[str, str] | None = None
    entity_to_name: dict[str, str] | None = None
    if abd_units:
        entity_to_obs_id = {}
        entity_to_unit_id = {}
        entity_to_name = {}
        # Build mapping from unit.id to unit
        unit_id_to_unit = {unit.get("id"): unit for unit in abd_units if unit.get("id")}
        # Use entityVersionMappings to get the correct entity IDs
        entity_version_mappings = custom_packets.get("_entityVersionMappings", [])
        for mapping in entity_version_mappings:
            entity_id = mapping.get("entityId")
            unit = unit_id_to_unit.get(entity_id)
            if unit:
                obs_id = unit.get("obsBrandGoodId")
                unit_id = unit.get("id")
                name = unit.get("name")
                if obs_id:
                    entity_to_obs_id[entity_id] = obs_id
                if unit_id:
                    entity_to_unit_id[entity_id] = unit_id
                if name:
                    entity_to_name[entity_id] = name
    
    # Step 5: Build the result structure
    # Note: obs_to_unit_id is deprecated but kept for backward compatibility
    obs_to_unit_id = _obs_to_unit_id_from_abd_units(abd_units)
    payload = build_parammodel_param_current_value(
        custom_packets,
        param_model_ids,
        entity_to_obs_id=entity_to_obs_id,
        obs_to_unit_id=obs_to_unit_id or None,
        entity_to_unit_id=entity_to_unit_id or None,
        entity_to_name=entity_to_name,
    )
    
    # Step 6: Write to file
    if output_path is None:
        workspace_root = Path(__file__).resolve().parents[3]
        output_path = workspace_root / "tmp" / "input" / "param_current.json"
    
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with output_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    
    return {
        "payload": payload,
        "output_path": str(output_path.resolve()),
        "design_id": design_id,
        "combination_id": combination_id,
        "level_id": level_id,
        "param_model_ids": param_model_ids,
    }