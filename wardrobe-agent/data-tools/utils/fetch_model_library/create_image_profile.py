import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))



REPO_ROOT = Path(__file__).resolve().parents[3]
PARAM_MODEL_LIBRARY = REPO_ROOT / "workspace" / "data" / "param-model-library"
PARAMMODEL = PARAM_MODEL_LIBRARY / "parammodel.json"
IMAGE_PROFILE = PARAM_MODEL_LIBRARY / "parammodel_image_profile.json"
TMP_ROOT = REPO_ROOT / "workspace" / "tmp"
ACCESSORY_TRIM_REMOVED_FIELDS = {
    "door_count",
    "bay_count",
    "drawer_count",
    "has_open_shelf",
    "handle_style",
    "layout_notes",
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_products_by_category(category_id: str, parammodel_path: Path) -> list[dict[str, str]]:
    data = load_json(parammodel_path)
    categories = data.get("categories", [])
    if not isinstance(categories, list):
        raise ValueError(f"{parammodel_path} field categories must be an array")

    for item in categories:
        if not isinstance(item, dict):
            continue
        if item.get("categoryId") != category_id:
            continue

        products = item.get("products", [])
        if not isinstance(products, list):
            raise ValueError(f"{parammodel_path} category {category_id} field products must be an array")

        result: list[dict[str, str]] = []
        for product in products:
            if not isinstance(product, dict):
                continue
            obs_brand_good_id = product.get("obsBrandGoodId")
            name = product.get("name")
            if isinstance(obs_brand_good_id, str) and isinstance(name, str):
                result.append(
                    {
                        "obsBrandGoodId": obs_brand_good_id,
                        "name": name,
                    }
                )
        return result

    raise ValueError(f"categoryId not found in {parammodel_path}: {category_id}")


def load_image_profile(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"schema_version": "1.0", "category_list": []}

    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")

    if "schema_version" not in data:
        data["schema_version"] = "1.0"
    if "category_list" not in data:
        data["category_list"] = []
    if not isinstance(data["category_list"], list):
        raise ValueError(f"{path} field category_list must be an array")
    _strip_preview_img_url_from_profile_list(data)
    return data


def _strip_preview_img_url_from_profile_list(image_profile_data: dict[str, Any]) -> None:
    """parammodel_image_profile.json must not persist previewImgUrl (use parammodel.json for previews)."""
    for cat in image_profile_data.get("category_list", []) or []:
        if not isinstance(cat, dict):
            continue
        for item in cat.get("profile_list", []) or []:
            if isinstance(item, dict):
                item.pop("previewImgUrl", None)


def _normalize_profile_input(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict) and isinstance(raw.get("profile_list"), list):
        items = raw["profile_list"]
    else:
        raise ValueError(
            "profile input must be an array, or an object with field 'profile_list' as an array"
        )

    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("each profile item must be an object")
        obs_brand_good_id = item.get("obsBrandGoodId")
        name = item.get("name")
        profile = item.get("profile")
        if not isinstance(obs_brand_good_id, str):
            raise ValueError("each profile item must contain string obsBrandGoodId")
        if not isinstance(name, str):
            raise ValueError(f"profile item {obs_brand_good_id} must contain string name")
        if not isinstance(profile, dict):
            raise ValueError(f"profile item {obs_brand_good_id} must contain object profile")
        normalized.append(
            {
                "obsBrandGoodId": obs_brand_good_id,
                "name": name,
                "profile": _normalize_profile(profile),
            }
        )
    return normalized


def _normalize_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Normalize profile payload before merging into cache."""
    role = profile.get("role")
    normalized_profile = dict(profile)
    if role == "accessory_trim":
        for field in ACCESSORY_TRIM_REMOVED_FIELDS:
            normalized_profile.pop(field, None)
    return normalized_profile


def _guess_image_extension(url: str, content_type: str | None) -> str:
    if content_type:
        content_type = content_type.split(";")[0].strip().lower()
        if content_type == "image/jpeg":
            return ".jpg"
        if content_type == "image/png":
            return ".png"
        if content_type == "image/webp":
            return ".webp"
        if content_type == "image/gif":
            return ".gif"

    parsed = urlparse(url)
    suffix = Path(parsed.path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}:
        return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def download_single_image(url: str, category_id: str, tmp_root: Path) -> Path | None:
    """Download a single image and return its local path. Returns None if download fails."""
    target_dir = tmp_root / f"{category_id}_images"
    target_dir.mkdir(parents=True, exist_ok=True)

    try:
        with urlopen(url, timeout=20) as resp:  # noqa: S310
            content = resp.read()
            content_type = resp.headers.get("Content-Type")
        if not content:
            print(f"[WARN] Empty content, skipped: {url}")
            return None

        file_hash = hashlib.md5(url.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]
        suffix = _guess_image_extension(url, content_type)
        out_path = target_dir / f"{file_hash}{suffix}"
        out_path.write_bytes(content)
        return out_path
    except Exception as exc:
        print(f"[WARN] Failed to download {url}: {exc}")
        return None


def export_products_with_images(
    category_id: str,
    parammodel_path: Path,
    tmp_root: Path,
) -> list[dict[str, Any]]:
    """
    Export products with local image paths.
    Returns list of {obsBrandGoodId, name, previewImgUrl, localImgPath}.
    """
    data = load_json(parammodel_path)
    categories = data.get("categories", [])
    if not isinstance(categories, list):
        raise ValueError(f"{parammodel_path} field categories must be an array")

    target_category = None
    for item in categories:
        if not isinstance(item, dict):
            continue
        if item.get("categoryId") == category_id:
            target_category = item
            break

    if target_category is None:
        raise ValueError(f"categoryId not found in {parammodel_path}: {category_id}")

    products = target_category.get("products", [])
    if not isinstance(products, list):
        raise ValueError(f"{parammodel_path} category {category_id} field products must be an array")

    result: list[dict[str, Any]] = []
    for product in products:
        if not isinstance(product, dict):
            continue
        obs_brand_good_id = product.get("obsBrandGoodId")
        name = product.get("name")
        raw_preview = product.get("previewImgUrl")
        if isinstance(raw_preview, str) and raw_preview.strip():
            preview_img_url = raw_preview.strip()
        else:
            preview_img_url = ""

        if not isinstance(obs_brand_good_id, str) or not isinstance(name, str):
            continue

        item: dict[str, Any] = {
            "obsBrandGoodId": obs_brand_good_id,
            "name": name,
            "previewImgUrl": preview_img_url,
        }

        if preview_img_url:
            local_path = download_single_image(preview_img_url, category_id, tmp_root)
            if local_path:
                item["localImgPath"] = str(local_path)
            else:
                item["localImgPath"] = None
        else:
            item["localImgPath"] = None

        result.append(item)

    return result


def merge_category_profile(
    image_profile_data: dict[str, Any],
    category_id: str,
    profile_items: list[dict[str, Any]],
) -> tuple[int, int]:
    category_list = image_profile_data["category_list"]
    category_entry: dict[str, Any] | None = None
    for item in category_list:
        if isinstance(item, dict) and item.get("categoryId") == category_id:
            category_entry = item
            break

    if category_entry is None:
        category_entry = {"categoryId": category_id, "profile_list": []}
        category_list.append(category_entry)

    if "profile_list" not in category_entry:
        category_entry["profile_list"] = []
    if not isinstance(category_entry["profile_list"], list):
        raise ValueError("target category profile_list field must be an array")

    existing = category_entry["profile_list"]
    existing_ids = {
        item.get("obsBrandGoodId")
        for item in existing
        if isinstance(item, dict) and isinstance(item.get("obsBrandGoodId"), str)
    }

    appended = 0
    skipped_existing = 0
    for item in profile_items:
        obs_brand_good_id = item["obsBrandGoodId"]
        if obs_brand_good_id in existing_ids:
            skipped_existing += 1
            continue
        existing.append(item)
        existing_ids.add(obs_brand_good_id)
        appended += 1
    return appended, skipped_existing


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create/merge image profile cache by categoryId. "
            "Use --export-with-images to output obsBrandGoodId/name/previewImgUrl/localImgPath and auto-download images; "
            "use --profile-input to merge generated profile into parammodel_image_profile.json."
        )
    )
    parser.add_argument("--category-id", required=True, help="Target categoryId")
    parser.add_argument(
        "--export-with-images",
        action="store_true",
        help=(
            "Export products with local image paths. Outputs JSON array with obsBrandGoodId, "
            "name, previewImgUrl, and localImgPath. Automatically downloads images to tmp directory."
        ),
    )
    parser.add_argument(
        "--profile-input",
        help=(
            "Path to generated profile JSON file. File format can be an array of "
            "{obsBrandGoodId,name,profile} or object with field 'profile_list' as that array."
        ),
    )
    args = parser.parse_args()

    category_id = args.category_id

    # Handle --export-with-images (new merged functionality)
    if args.export_with_images:
        products_with_images = export_products_with_images(
            category_id,
            PARAMMODEL,
            TMP_ROOT,
        )
        print(json.dumps(products_with_images, ensure_ascii=False, indent=2))
        # Count successful downloads
        downloaded = sum(1 for p in products_with_images if p.get("localImgPath"))
        failed = sum(1 for p in products_with_images if p.get("previewImgUrl") and not p.get("localImgPath"))
        print(
            f"\n# Exported {len(products_with_images)} products for categoryId={category_id}; "
            f"images downloaded={downloaded}, failed={failed}",
            file=sys.stderr,
        )
        return 0

    if not args.profile_input:
        return 0

    products = load_products_by_category(category_id, PARAMMODEL)
    profile_input_data = load_json(Path(args.profile_input))
    incoming_profile = _normalize_profile_input(profile_input_data)
    product_ids = {item["obsBrandGoodId"] for item in products}

    filtered_profile: list[dict[str, Any]] = []
    skipped_not_in_category = 0
    for item in incoming_profile:
        if item["obsBrandGoodId"] not in product_ids:
            skipped_not_in_category += 1
            continue
        filtered_profile.append(item)

    image_profile_data = load_image_profile(IMAGE_PROFILE)
    appended, skipped_existing = merge_category_profile(image_profile_data, category_id, filtered_profile)
    dump_json(IMAGE_PROFILE, image_profile_data)
    print(
        f"Wrote image profile for categoryId={category_id} to {IMAGE_PROFILE}; "
        f"appended={appended}, skipped_existing={skipped_existing}, skipped_not_in_category={skipped_not_in_category}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
