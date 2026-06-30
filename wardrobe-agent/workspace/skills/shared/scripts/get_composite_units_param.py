"""
Fetch composite cabinet unit parameters and write param_current.json.

Usage (exactly one mode required):
    python skills/shared/scripts/get_composite_units_param.py --abd [ABD_PATH] [--output PATH]
    python skills/shared/scripts/get_composite_units_param.py --obs-collect-bgid BGID [--output PATH]
    python skills/shared/scripts/get_composite_units_param.py --design-id DESIGN_ID --id COMBINATION_ID [--output PATH]

Default output: workspace/tmp/input/param_current.json

--abd reads abd.json and auto-detects whether to use obsCollectBrandGoodId or designId.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[4]
UTILS_DIR = REPO_ROOT / "data-tools" / "utils"
FETCH_FAVORITE_ASSEMBLY_DIR = UTILS_DIR / "fetch_favorite_assembly"
SCRIPTS_DIR = Path(__file__).resolve().parent

WORKSPACE_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT_FILE = WORKSPACE_ROOT / "tmp" / "input" / "param_current.json"


def _ensure_fetch_favorite_assembly_importable() -> None:
    """generate_assembly_abd uses sibling imports (fetch_common, crypt_zstd, …)."""
    for path in (UTILS_DIR, FETCH_FAVORITE_ASSEMBLY_DIR):
        entry = str(path)
        if entry not in sys.path:
            sys.path.insert(0, entry)


def _ensure_scripts_importable() -> None:
    entry = str(SCRIPTS_DIR)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _resolve_output_path(output_path: Path | str | None) -> Path:
    if output_path is None:
        return DEFAULT_OUTPUT_FILE
    return Path(output_path)


def get_params_by_obs_collect_bgid(
    obs_collect_brand_good_id: str,
    output_path: Path | str | None = None,
    *,
    status_file: Path | str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Fetch unit parameters by obsCollectBrandGoodId and write param_current.json.

    Assembly API provides obsBrandGoodId (from brandGoodId) and id (paramModel id) per unit.
    """
    obs_collect_bgid = str(obs_collect_brand_good_id).strip()
    if not obs_collect_bgid:
        raise ValueError("obs_collect_brand_good_id must be a non-empty string")

    dest = _resolve_output_path(output_path)

    _ensure_fetch_favorite_assembly_importable()
    module = importlib.import_module("fetch_favorite_assembly.generate_assembly_abd")
    export_fn = getattr(module, "export_parammodel_param_current_value_by_bgid")

    return export_fn(
        obs_collect_bgid,
        output_path=dest,
        status_file=status_file,
        timeout=timeout,
    )


def get_params_by_design(
    design_id: str,
    combination_id: str,
    output_path: Path | str | None = None,
    *,
    abd_units: list[dict[str, Any]] | None = None,
    status_file: Path | str | None = None,
    timeout: float = 60.0,
) -> dict[str, Any]:
    """
    Fetch unit parameters by designId and combination id, write param_current.json.

    Design API provides brandGoodId + entityId per unit; mapped to obsBrandGoodId + id.
    Optional ``abd_units`` preserves abd.json unit ids via entityVersionMappings.
    """
    design_id_value = str(design_id).strip()
    combination_id_value = str(combination_id).strip()
    if not design_id_value:
        raise ValueError("design_id must be a non-empty string")
    if not combination_id_value:
        raise ValueError("combination_id must be a non-empty string")

    dest = _resolve_output_path(output_path)

    _ensure_scripts_importable()
    import fetch_design_params

    return fetch_design_params.export_parammodel_param_current_value_by_design(
        design_id_value,
        combination_id_value,
        output_path=dest,
        abd_units=abd_units,
        status_file=status_file,
        timeout=timeout,
    )


def _enrich_with_abd_unit_ids(
    output_path: Path,
    abd_units: list[dict[str, Any]],
) -> bool:
    """Merge abd.json unit ids into param_current.json by obsBrandGoodId."""
    if not output_path.exists() or not abd_units:
        return False
    try:
        _ensure_scripts_importable()
        import fetch_design_params

        with output_path.open(encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            return False
        enriched = fetch_design_params.enrich_parammodel_param_current_value_with_abd_unit_ids(
            payload,
            abd_units,
            match_by_obs_and_name=True,
        )
        if enriched is None:
            return False
        with output_path.open("w", encoding="utf-8", newline="\n") as f:
            json.dump(enriched, f, ensure_ascii=False, indent=2)
            f.write("\n")
        return True
    except Exception as e:
        print(
            f"warning: failed to enrich {output_path.name} with abd unit ids: {e}",
            file=sys.stderr,
        )
        return False


def generate_current_value_file(
    abd_path: Path | str | None = None,
    output_path: Path | str | None = None,
) -> bool:
    """
    Generate param_current.json from abd.json.

    Tries obsCollectBrandGoodId first, then designId + id as fallback.

    Args:
        abd_path: Path to abd.json (default: workspace/tmp/input/abd.json).
        output_path: Output path (default: workspace/tmp/input/param_current.json).

    Returns:
        True if generation succeeded, False otherwise.
    """
    if abd_path is None:
        abd_path = WORKSPACE_ROOT / "tmp" / "input" / "abd.json"
    abd_path = Path(abd_path)

    dest = _resolve_output_path(output_path)

    # Load abd.json
    if not abd_path.exists():
        print(f"warning: {abd_path} not found", file=sys.stderr)
        return False
    try:
        with abd_path.open(encoding="utf-8") as f:
            abd_data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"warning: failed to read {abd_path}: {e}", file=sys.stderr)
        return False
    if not isinstance(abd_data, dict):
        return False

    abd_units = abd_data.get("units")
    if not isinstance(abd_units, list):
        abd_units = None

    # Try obsCollectBrandGoodId first
    obs_collect_bgid = abd_data.get("obsCollectBrandGoodId")
    if isinstance(obs_collect_bgid, str) and obs_collect_bgid.strip():
        obs_collect_bgid = obs_collect_bgid.strip()
        try:
            get_params_by_obs_collect_bgid(obs_collect_bgid, output_path=dest)
            if abd_units:
                _enrich_with_abd_unit_ids(dest, abd_units)
            print(
                f"info: generated {dest.name} from obsCollectBrandGoodId={obs_collect_bgid}",
                file=sys.stderr,
            )
            return True
        except Exception as e:
            print(
                f"warning: failed to generate {dest.name} "
                f"from obsCollectBrandGoodId={obs_collect_bgid}: {e}",
                file=sys.stderr,
            )

    # Try designId + id as fallback
    design_id = abd_data.get("designId") or abd_data.get("id")
    if isinstance(design_id, str) and design_id.strip():
        design_id = design_id.strip()
        combination_id = abd_data.get("id")
        if isinstance(combination_id, str) and combination_id.strip():
            combination_id = combination_id.strip()
            try:
                get_params_by_design(
                    design_id,
                    combination_id,
                    output_path=dest,
                    abd_units=abd_units,
                )
                print(
                    f"info: generated {dest.name} from "
                    f"designId={design_id}, combinationId={combination_id}",
                    file=sys.stderr,
                )
                return True
            except Exception as e:
                print(
                    f"warning: failed to generate {dest.name} "
                    f"from designId={design_id}: {e}",
                    file=sys.stderr,
                )

    return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch composite cabinet unit parameters and write param_current.json. "
            "Use --abd, --obs-collect-bgid, or --design-id with --id."
        ),
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--abd",
        dest="abd_path",
        nargs="?",
        const=str(DEFAULT_OUTPUT_FILE.parent / "abd.json"),
        default=None,
        metavar="ABD_PATH",
        help="Path to abd.json (default: tmp/input/abd.json); auto-detects obsCollectBrandGoodId or designId",
    )
    mode_group.add_argument(
        "--obs-collect-bgid",
        dest="obs_collect_brand_good_id",
        metavar="BGID",
        help="Combination cabinet obsCollectBrandGoodId",
    )
    mode_group.add_argument(
        "--design-id",
        dest="design_id",
        metavar="DESIGN_ID",
        help="Design ID",
    )
    parser.add_argument(
        "--id",
        dest="combination_id",
        metavar="COMBINATION_ID",
        help="Combination model id; required with --design-id",
    )
    parser.add_argument(
        "--output",
        dest="output_path",
        default=None,
        help=f"Output JSON path (default: {DEFAULT_OUTPUT_FILE})",
    )
    args = parser.parse_args()

    if args.design_id is not None and not args.combination_id:
        print("Error: --id is required when using --design-id", file=sys.stderr)
        return 1
    if args.obs_collect_brand_good_id is not None and args.combination_id:
        print(
            "Error: --id can only be used with --design-id, not --obs-collect-bgid",
            file=sys.stderr,
        )
        return 1
    if args.abd_path is not None and args.combination_id:
        print(
            "Error: --id can only be used with --design-id, not --abd",
            file=sys.stderr,
        )
        return 1

    try:
        if args.abd_path is not None:
            ok = generate_current_value_file(
                abd_path=args.abd_path,
                output_path=args.output_path,
            )
            if not ok:
                print("Error: failed to generate param_current.json from abd.json", file=sys.stderr)
                return 1
            result = {"output_path": str(_resolve_output_path(args.output_path))}
        elif args.obs_collect_brand_good_id is not None:
            result = get_params_by_obs_collect_bgid(
                args.obs_collect_brand_good_id,
                output_path=args.output_path,
            )
        else:
            result = get_params_by_design(
                args.design_id,
                args.combination_id,
                output_path=args.output_path,
            )
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    print(
        f"info: wrote unit parameters to {result.get('output_path', args.output_path)}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
