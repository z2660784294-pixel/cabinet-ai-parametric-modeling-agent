import argparse
import json
import sys
from pathlib import Path
from typing import Any

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from fetch_model_library.api import get_products_by_categories


REPO_ROOT = Path(__file__).resolve().parents[3]
PARAM_MODEL_LIBRARY = REPO_ROOT / "workspace" / "data" / "param-model-library"
PARAMMODEL = PARAM_MODEL_LIBRARY / "parammodel.json"
TEMP_OUTPUT = PARAM_MODEL_LIBRARY / "_tmp_products_by_categories.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_parammodel(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"categories": []}
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if "categories" not in data:
        data["categories"] = []
    if not isinstance(data["categories"], list):
        raise ValueError(f"{path} field categories must be an array")
    return data


def merge_categories(parammodel: dict[str, Any], incoming: list[dict[str, Any]]) -> tuple[int, int, int]:
    categories = parammodel["categories"]
    index_by_id = {
        item.get("categoryId"): idx
        for idx, item in enumerate(categories)
        if isinstance(item, dict) and isinstance(item.get("categoryId"), str)
    }
    replaced = 0
    appended = 0
    skipped = 0
    for item in incoming:
        category_id = item.get("categoryId")
        if not isinstance(category_id, str) or not isinstance(item.get("products"), list):
            raise ValueError("incoming category item must contain categoryId and products")
        # 跳过空商品列表的数据
        products = item.get("products", [])
        if not products:
            skipped += 1
            continue
        if category_id in index_by_id:
            idx = index_by_id[category_id]
            existing = categories[idx]
            categories[idx] = {**existing, **item}
            replaced += 1
        else:
            categories.append(item)
            index_by_id[category_id] = len(categories) - 1
            appended += 1
    return replaced, appended, skipped


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch products by categoryId and merge into parammodel.json."
    )
    parser.add_argument("--category-id", required=True, help="Target categoryId.")
    parser.add_argument("--parammodel", default=str(PARAMMODEL))
    parser.add_argument("--output-temp", default=str(TEMP_OUTPUT))
    args = parser.parse_args()

    category_id = args.category_id
    incoming = get_products_by_categories([category_id])

    tmp = Path(args.output_temp)
    dump_json(tmp, incoming)
    print(f"wrote temp products file: {tmp}; categoryId={category_id}")

    target = Path(args.parammodel)
    parammodel = load_parammodel(target)
    replaced, appended, skipped = merge_categories(parammodel, incoming)
    dump_json(target, parammodel)
    product_count = sum(len(item["products"]) for item in incoming if item.get("products"))
    print(
        f"Wrote {len(incoming) - skipped} categories ({product_count} products) to {target}; "
        f"replaced={replaced}, appended={appended}, skipped={skipped}; categoryId={category_id}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
