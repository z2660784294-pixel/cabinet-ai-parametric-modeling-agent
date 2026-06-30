import argparse
import json
import sys
from pathlib import Path
from typing import Any

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from fetch_model_library.api import get_products_parameters


REPO_ROOT = Path(__file__).resolve().parents[3]
PARAM_MODEL_LIBRARY = REPO_ROOT / "workspace" / "data" / "param-model-library"
PARAMMODEL = PARAM_MODEL_LIBRARY / "parammodel.json"
PARAM_LIST = PARAM_MODEL_LIBRARY / "parammodel_param_list.json"


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_brand_good_ids(category_id: str, parammodel_path: Path) -> list[str]:
    data = load_json(parammodel_path)
    for item in data.get("categories", []):
        if item.get("categoryId") == category_id:
            return [
                p["obsBrandGoodId"]
                for p in item.get("products", [])
                if isinstance(p, dict) and isinstance(p.get("obsBrandGoodId"), str)
            ]
    raise ValueError(f"categoryId not found in {parammodel_path}: {category_id}")


def chunked(seq: list[str], size: int) -> list[list[str]]:
    return [seq[i : i + size] for i in range(0, len(seq), size)]


def normalize_models(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        payload = payload.get("models") or payload.get("result") or [payload]
    if not isinstance(payload, list):
        raise ValueError("get_products_parameters result must be a model object or array")
    models: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("each model item must be an object")
        if not isinstance(item.get("obsBrandGoodId"), str) or not item.get("obsBrandGoodId"):
            raise ValueError("each model item must contain non-empty string obsBrandGoodId")
        if not isinstance(item.get("inputs"), list):
            raise ValueError(f"model {item.get('obsBrandGoodId')} must contain inputs array")
        models.append(item)
    return models


def filter_model_inputs(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for model in models:
        inputs = model.get("inputs", [])
        model["inputs"] = [
            param
            for param in inputs
            if isinstance(param, dict)
            and param.get("paramName") != "LD"
        ]
    return models


def load_param_list(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"param_list": []}
    data = load_json(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    if "param_list" not in data:
        data["param_list"] = []
    if not isinstance(data["param_list"], list):
        raise ValueError(f"{path} field param_list must be an array")
    return data


def merge_category_models(target_data: dict[str, Any], category_id: str, models: list[dict[str, Any]]) -> bool:
    items = target_data["param_list"]
    for idx, item in enumerate(items):
        if isinstance(item, dict) and item.get("categoryId") == category_id:
            items[idx] = {"categoryId": category_id, "models": models}
            return True
    items.append({"categoryId": category_id, "models": models})
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch parameters by categoryId and write parammodel_param_list.json.")
    parser.add_argument("--category-id", required=True)
    parser.add_argument("--chunk-size", type=int, default=10)
    parser.add_argument("--parammodel", default=str(PARAMMODEL))
    parser.add_argument("--output", default=str(PARAM_LIST))
    parser.add_argument(
        "--output-temp",
        default=str(PARAM_MODEL_LIBRARY / "_tmp_feature3_models.json"),
    )
    args = parser.parse_args()

    ids = load_brand_good_ids(args.category_id, Path(args.parammodel))
    all_models: list[dict[str, Any]] = []
    for idx, group in enumerate(chunked(ids, args.chunk_size), start=1):
        models = get_products_parameters(group)
        print(f"chunk {idx}: fetched {len(models)} models")
        all_models.extend(models)

    all_models = normalize_models(all_models)
    all_models = filter_model_inputs(all_models)

    temp_path = Path(args.output_temp)
    dump_json(temp_path, all_models)
    print(f"wrote temp models file: {temp_path}")

    out_path = Path(args.output)
    data = load_param_list(out_path)
    replaced = merge_category_models(data, args.category_id, all_models)
    dump_json(out_path, data)
    print(
        f"Wrote categoryId={args.category_id} models={len(all_models)} to {out_path}; replaced={replaced}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
