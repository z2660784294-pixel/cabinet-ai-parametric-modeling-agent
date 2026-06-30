"""
CLI 工具：根据 obsBrandGoodId 查询产品参数。

Usage:
    python get_default_param.py <obsBrandGoodId>

Example:
    python get_default_param.py 3FO3G5WJ1XUF
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
WORKSPACE_ROOT = SCRIPT_DIR.parents[2]

# Add shared scripts to path
SHARED_SCRIPTS = SCRIPT_DIR.parents[1] / "shared" / "scripts"
if str(SHARED_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SHARED_SCRIPTS))

# Add fetch_model_library to path
UTILS_DIR = WORKSPACE_ROOT.parent / "data-tools" / "utils"
FETCH_MODEL_LIBRARY_DIR = UTILS_DIR / "fetch_model_library"
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))
if str(FETCH_MODEL_LIBRARY_DIR) not in sys.path:
    sys.path.insert(0, str(FETCH_MODEL_LIBRARY_DIR))

from api import get_products_parameters


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query product parameters by obsBrandGoodId"
    )
    parser.add_argument("obs_brand_good_id", help="The obsBrandGoodId to query")
    args = parser.parse_args()

    obs_id = args.obs_brand_good_id.strip()
    if not obs_id:
        print("error: obs_brand_good_id cannot be empty", file=sys.stderr)
        return 1

    results = get_products_parameters([obs_id])

    if not results:
        print(f"error: no results for {obs_id}", file=sys.stderr)
        return 1

    result = results[0]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())