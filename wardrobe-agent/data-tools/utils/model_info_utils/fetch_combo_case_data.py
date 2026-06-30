#!/usr/bin/env python3
"""Fetch combination-cabinet raw data via direct HTTP APIs into temp/cases."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from fetch_model_library.api import (
    ApiError,
    get_catalogue_tree,
    get_model_data,
    get_products_by_categories,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_ROOT = REPO_ROOT / "temp" / "cases"
ALLOWED_HOST_SUFFIXES = (".kujiale.com",)


def normalize_query(value: str) -> str:
    return value.replace("\\", "/").replace(" - ", "/").replace(" ", "").strip("/")


def library_descriptions(tree: Any) -> dict[str, str]:
    if not isinstance(tree, dict):
        return {}
    descs = tree.get("meta", {}).get("catalogueLibraryDescs", [])
    return {item.get("key", ""): item.get("desc", "") for item in descs if isinstance(item, dict)}


def iter_catalogue_entries(tree: Any):
    desc_by_key = library_descriptions(tree)
    if isinstance(tree, dict):
        for key, value in tree.items():
            if key == "meta" or not isinstance(value, list):
                continue
            root_name = desc_by_key.get(key, key)
            for node in value:
                yield from iter_node_entries(node, [root_name])
    elif isinstance(tree, list):
        for node in tree:
            yield from iter_node_entries(node, [])


def iter_node_entries(node: Any, parents: list[str]):
    if not isinstance(node, dict):
        return
    name = str(node.get("n", "")).strip()
    path = parents + ([name] if name else [])
    if node.get("id"):
        yield {"id": str(node["id"]), "name": name, "path": path}
    for child in node.get("kids", []) or []:
        yield from iter_node_entries(child, path)
    for child in node.get("children", []) or []:
        yield from iter_node_entries(child, path)


def collect_category_ids(tree: Any) -> list[str]:
    ids: list[str] = []
    seen = set()
    for entry in iter_catalogue_entries(tree):
        category_id = entry["id"].strip()
        if category_id and category_id not in seen:
            seen.add(category_id)
            ids.append(category_id)
    return ids


def resolve_category_id(category_name: str) -> str:
    tree = get_catalogue_tree()
    query = normalize_query(category_name)
    matches = []
    for entry in iter_catalogue_entries(tree):
        candidates = [
            entry["name"],
            "/".join(entry["path"]),
            " - ".join(entry["path"]),
            "/".join(entry["path"][1:]),
            " - ".join(entry["path"][1:]),
        ]
        if any(normalize_query(candidate) == query for candidate in candidates if candidate):
            matches.append(entry)
    if not matches:
        raise ApiError(f"Category not found: {category_name}")
    if len(matches) > 1:
        exact_with_root = [entry for entry in matches if normalize_query(" - ".join(entry["path"])) == query]
        matches = exact_with_root or matches
    if len(matches) > 1:
        options = [f'{entry["id"]}: {" / ".join(entry["path"])}' for entry in matches[:10]]
        raise ApiError("Category name is ambiguous:\n" + "\n".join(options))
    return matches[0]["id"]


def chunks(items: list[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def list_products_in_categories(category_ids: list[str], batch_size: int) -> list[dict[str, Any]]:
    products: list[dict[str, Any]] = []
    for batch in chunks(category_ids, batch_size):
        categories = get_products_by_categories(batch)
        for category in categories:
            category_id = category.get("categoryId")
            for product in category.get("products", []) or []:
                bgid = product.get("obsBrandGoodId")
                if not bgid:
                    continue
                products.append(
                    {
                        "bgid": bgid,
                        "name": product.get("name"),
                        "previewImgUrl": product.get("previewImgUrl"),
                        "categoryId": category_id,
                    }
                )
    return products


def find_product_by_bgid(bgid: str, category_id: str | None, batch_size: int) -> dict[str, Any]:
    if category_id:
        products = list_products_in_categories([category_id], batch_size)
    else:
        tree = get_catalogue_tree()
        products = list_products_in_categories(collect_category_ids(tree), batch_size)
    for product in products:
        if product["bgid"] == bgid:
            return product
    raise ApiError(f"BGID not found in catalogue products: {bgid}")


def normalize_url(url: str) -> str:
    if url.startswith("//"):
        return "https:" + url
    return url


def is_allowed_host(url: str) -> bool:
    try:
        host = urllib.parse.urlparse(url).hostname or ""
    except ValueError:
        return False
    host = host.lower()
    return any(host.endswith(suffix) for suffix in ALLOWED_HOST_SUFFIXES)


def download_preview(url: str, output: Path, overwrite: bool) -> dict[str, Any]:
    if output.exists() and not overwrite:
        return {"status": "skipped", "path": str(output), "sizeBytes": output.stat().st_size}
    url = normalize_url(url)
    if not is_allowed_host(url):
        raise ApiError(f"Refusing to download from non-whitelisted host: {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "fetch-combo-case-data/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = resp.read()
    except urllib.error.HTTPError as exc:
        raise ApiError(f"Image download HTTP {exc.code}: {url}") from exc
    except urllib.error.URLError as exc:
        raise ApiError(f"Image download failed: {exc}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(data)
    return {"status": "downloaded", "path": str(output), "sizeBytes": len(data), "url": url}


def _dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_model_data(bgid: str, case_dir: Path, overwrite: bool) -> dict[str, Any]:
    """Fetch editorData.json and paramModel.json for a BGID via direct HTTP API."""
    editor_path = case_dir / "editorData.json"
    param_path = case_dir / "paramModel.json"
    if editor_path.exists() and param_path.exists() and not overwrite:
        return {"status": "skipped", "files": [str(editor_path), str(param_path)]}

    case_dir.mkdir(parents=True, exist_ok=True)
    model_result = get_model_data(bgid, ("EditorData", "ParamModel"))

    errors = model_result.get("errors") or {}
    if errors:
        raise ApiError(f"get_model_data errors for {bgid}: {errors}")

    editor_data = model_result.get("EditorData")
    param_model = model_result.get("ParamModel")

    if editor_data is None:
        raise ApiError(f"get_model_data returned no EditorData for {bgid}")
    if param_model is None:
        raise ApiError(f"get_model_data returned no ParamModel for {bgid}")

    _dump_json(editor_path, editor_data)
    _dump_json(param_path, param_model)

    missing = [str(p) for p in (editor_path, param_path) if not p.exists()]
    if missing:
        raise ApiError(f"get_model_data did not create expected files for {bgid}: {missing}")

    return {"status": "fetched", "files": [str(editor_path), str(param_path)]}


def validate_case_files(case_dir: Path) -> dict[str, bool]:
    return {
        "editorData.json": (case_dir / "editorData.json").exists(),
        "paramModel.json": (case_dir / "paramModel.json").exists(),
        "previewImage.png": (case_dir / "previewImage.png").exists(),
    }


def fetch_one_case(
    product: dict[str, Any], output_root: Path, overwrite: bool
) -> dict[str, Any]:
    bgid = product["bgid"]
    case_dir = output_root / bgid
    row: dict[str, Any] = {
        "bgid": bgid,
        "name": product.get("name"),
        "categoryId": product.get("categoryId"),
        "outputDir": str(case_dir),
    }
    try:
        preview_url = product.get("previewImgUrl")
        if not preview_url:
            raise ApiError(f"Product has no previewImgUrl: {bgid}")
        row["modelData"] = fetch_model_data(bgid, case_dir, overwrite)
        row["previewImage"] = download_preview(preview_url, case_dir / "previewImage.png", overwrite)
        row["files"] = validate_case_files(case_dir)
        row["status"] = "success" if all(row["files"].values()) else "failed"
    except Exception as exc:
        row["status"] = "failed"
        row["error"] = str(exc)
        row["files"] = validate_case_files(case_dir)
    return row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch combo case editorData, paramModel, and preview image.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--bgid", help="Single obsBrandGoodId to fetch")
    mode.add_argument("--category-id", help="Catalogue categoryId to fetch")
    mode.add_argument("--category-name", help="Catalogue category display name or path to fetch")
    parser.add_argument("--lookup-category-id", help="Optional categoryId used to locate a --bgid product quickly")
    parser.add_argument(
        "--output-root",
        default=str(DEFAULT_OUTPUT_ROOT),
        help=f"Output root folder (default: {DEFAULT_OUTPUT_ROOT})",
    )
    parser.add_argument("--batch-size", type=int, default=20, help="Category query batch size")
    parser.add_argument("--limit", type=int, help="Limit number of products for smoke testing")
    parser.add_argument("--overwrite", action="store_true", help="Re-fetch files even if outputs already exist")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root).resolve()

    try:
        if args.bgid:
            product = find_product_by_bgid(args.bgid, args.lookup_category_id, args.batch_size)
            products = [product]
        else:
            category_id = args.category_id or resolve_category_id(args.category_name)
            products = list_products_in_categories([category_id], args.batch_size)
            if args.limit is not None:
                products = products[: args.limit]

        rows = [fetch_one_case(product, output_root, args.overwrite) for product in products]
        failed = [row for row in rows if row.get("status") != "success"]
        summary = {
            "status": "success" if not failed else "failed",
            "outputRoot": str(output_root),
            "total": len(rows),
            "succeeded": len(rows) - len(failed),
            "failed": len(failed),
            "failedBgids": [row["bgid"] for row in failed],
            "results": rows,
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if not failed else 1
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
