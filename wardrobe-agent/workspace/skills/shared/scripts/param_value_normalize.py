"""
Normalize parameter values from design/assembly APIs for param list export.

Design custom-packets often return numeric brandGoodId for material/style;
PMBuilder and param templates expect obsBrandGoodId (e.g. 3FO3K9CLK3OO).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[4]
_FETCH_FAVORITE_ASSEMBLY_DIR = _REPO_ROOT / "data-tools" / "utils" / "fetch_favorite_assembly"


def _ensure_assembly_helpers_importable() -> None:
    entry = str(_FETCH_FAVORITE_ASSEMBLY_DIR)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def brand_good_id_to_obs(brand_good_id: Any) -> str | None:
    """Convert numeric brandGoodId from API to obsBrandGoodId."""
    if brand_good_id is None:
        return None
    _ensure_assembly_helpers_importable()
    from generate_assembly_abd import (  # noqa: WPS433
        _ABD_BRAND_GOOD_CRYPT,
        _coerce_brand_good_id,
    )

    bg_int = _coerce_brand_good_id(brand_good_id)
    if bg_int is None:
        return None
    enc = _ABD_BRAND_GOOD_CRYPT.encrypt(bg_int)
    return enc if enc is not None else None


def format_param_value_for_export(val: Any, value_type: str) -> str:
    """Convert API param value to the string form used in param list JSON."""
    if val is None:
        return ""

    value_kind = str(value_type or "string").lower()

    if value_kind == "material":
        _ensure_assembly_helpers_importable()
        from generate_assembly_abd import (  # noqa: WPS433
            _ABD_BRAND_GOOD_CRYPT,
            _coerce_brand_good_id,
        )

        bg_int = _coerce_brand_good_id(val)
        if bg_int is not None:
            enc = _ABD_BRAND_GOOD_CRYPT.encrypt(bg_int)
            if enc is not None:
                return enc
        return str(val)

    if value_kind == "style":
        _ensure_assembly_helpers_importable()
        from generate_assembly_abd import _style_value_db_to_obs_and_serialize  # noqa: WPS433

        return _style_value_db_to_obs_and_serialize(val)

    if value_kind == "float3":
        val_str = str(val)
        if "," in val_str:
            parts = val_str.split(",")
            if len(parts) == 3:
                return json.dumps(
                    {"x": parts[0], "y": parts[1], "z": parts[2]},
                    separators=(",", ":"),
                )
        return val_str

    return str(val)
