"""
根据 obsBrandGoodId 查询商品历史版本（versionId）。

API: GET /editor/api/site/editordata/version
    params: obsbrandgoodid, current=false

Usage:
    python fetch_brandgood_version_id.py <obsBrandGoodId>
    python fetch_brandgood_version_id.py <obsBrandGoodId> --latest
    python fetch_brandgood_version_id.py <obsBrandGoodId> --list
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[2]

UTILS_DIR = WORKSPACE_ROOT.parent / "data-tools" / "utils"
FETCH_MODEL_LIBRARY_DIR = UTILS_DIR / "fetch_model_library"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))
if str(FETCH_MODEL_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(FETCH_MODEL_LIBRARY_DIR))

from api import ApiError, _api_get, load_config


def fetch_version_data(obs_brand_good_id: str) -> dict[str, Any]:
    """Fetch version history for a product.

    Returns:
        ``{"historyVersions": [...]}`` as returned by the API.
    """
    obs_id = obs_brand_good_id.strip()
    if not obs_id:
        raise ValueError("obs_brand_good_id cannot be empty")

    config = load_config()
    data = _api_get(
        config,
        "/editor/api/site/editordata/version",
        {
            "obsbrandgoodid": obs_id,
            "current": "false",
        },
    )
    if not isinstance(data, dict):
        raise ApiError(f"unexpected version response for {obs_id}")
    return data


def get_version_ids(obs_brand_good_id: str) -> list[int]:
    """Return all versionId values for a product (newest first, as from API)."""
    data = fetch_version_data(obs_brand_good_id)
    history = data.get("historyVersions") or []
    version_ids: list[int] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        version_id = item.get("versionId")
        if isinstance(version_id, int):
            version_ids.append(version_id)
        elif isinstance(version_id, str) and version_id.isdigit():
            version_ids.append(int(version_id))
    return version_ids


def get_latest_version_id(obs_brand_good_id: str) -> int:
    """Return the latest (highest) versionId for a product."""
    version_ids = get_version_ids(obs_brand_good_id)
    if not version_ids:
        raise ApiError(f"no versionId found for {obs_brand_good_id}")
    return max(version_ids)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query product versionId by obsBrandGoodId"
    )
    parser.add_argument("obs_brand_good_id", help="The obsBrandGoodId to query")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--latest",
        action="store_true",
        help="Print only the latest versionId",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="Print all versionId values as a JSON array",
    )
    args = parser.parse_args()

    obs_id = args.obs_brand_good_id.strip()
    if not obs_id:
        print("error: obs_brand_good_id cannot be empty", file=sys.stderr)
        return 1

    try:
        if args.latest:
            print(get_latest_version_id(obs_id))
        elif args.list:
            print(json.dumps(get_version_ids(obs_id), ensure_ascii=False))
        else:
            print(json.dumps(fetch_version_data(obs_id), ensure_ascii=False, indent=2))
    except (ApiError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
