"""
模型库缓存覆盖前检查（model_cache_agent 通用纪律 §3）。

在 data-tools/ 下执行，stdout 为 JSON：
  python utils/fetch_model_library/util.py feature2 --category-id <categoryId>
  python utils/fetch_model_library/util.py feature3 --category-id <categoryId>
  python utils/fetch_model_library/util.py feature4 --category-id <categoryId>
  python utils/fetch_model_library/util.py feature4 --category-id <id> --obs-brand-good-id <bgid>

带 --overwrite-confirm "<用户原话>" 时校验覆盖授权用语。

退出码：0 = 可继续后续脚本；1 = 须确认覆盖或检查失败。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PARAM_MODEL_LIBRARY = REPO_ROOT / "workspace" / "data" / "param-model-library"
DEFAULT_PARAMMODEL = PARAM_MODEL_LIBRARY / "parammodel.json"
DEFAULT_PARAM_LIST = PARAM_MODEL_LIBRARY / "parammodel_param_list.json"
DEFAULT_IMAGE_PROFILE = PARAM_MODEL_LIBRARY / "parammodel_image_profile.json"

OVERWRITE_CONFIRM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"覆盖",
        r"确认更新",
        r"重新拉取并覆盖",
        r"确认覆盖",
    )
)


def _emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))


def is_overwrite_confirm_text(text: str | None) -> bool:
    if not text or not str(text).strip():
        return False
    normalized = str(text).strip()
    return any(p.search(normalized) for p in OVERWRITE_CONFIRM_PATTERNS)


def _load_json_object(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.is_file():
        return None, None
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        return None, f"无法解析 {path}: {e}"
    if not isinstance(data, dict):
        return None, f"{path} 顶层必须是 JSON 对象"
    return data, None


def _find_category_in_list(
    items: Any, category_id: str, *, id_field: str = "categoryId"
) -> dict[str, Any] | None:
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict) and item.get(id_field) == category_id:
            return item
    return None


def _finalize_overwrite_result(
    result: dict[str, Any],
    *,
    overwrite_confirm: str | None,
    exists: bool,
    exists_label: str,
    proceed_label: str,
    block_message: str,
) -> dict[str, Any]:
    if not exists:
        result.update(
            ok=True,
            can_proceed=True,
            needs_overwrite_confirm=False,
            message=(
                f"{exists_label}，可直接{proceed_label}，无需覆盖确认。"
            ),
        )
        return result

    result["needs_overwrite_confirm"] = True
    if is_overwrite_confirm_text(overwrite_confirm):
        result.update(
            ok=True,
            can_proceed=True,
            message=f"已确认覆盖，可{proceed_label}。",
        )
        return result

    result.update(
        ok=True,
        can_proceed=False,
        message=block_message,
    )
    return result


def check_feature2_overwrite(
    category_id: str,
    *,
    parammodel_path: Path = DEFAULT_PARAMMODEL,
    overwrite_confirm: str | None = None,
) -> dict[str, Any]:
    path = parammodel_path.resolve()
    result: dict[str, Any] = {
        "feature": 2,
        "category_id": category_id,
        "cache_file": str(path),
        "file_exists": path.is_file(),
        "category_exists": False,
        "needs_overwrite_confirm": False,
        "can_proceed": False,
        "existing_products_count": None,
    }

    if not path.is_file():
        return _finalize_overwrite_result(
            result,
            overwrite_confirm=overwrite_confirm,
            exists=False,
            exists_label=f"{path.name} 不存在",
            proceed_label="执行 fetch_products_by_categoryid.py",
            block_message="",
        )

    data, err = _load_json_object(path)
    if err:
        result.update(ok=False, error=err, message="缓存 JSON 损坏或不可读，请勿自动覆盖。")
        return result

    categories = data.get("categories") if data else None
    if categories is None:
        return _finalize_overwrite_result(
            result,
            overwrite_confirm=overwrite_confirm,
            exists=False,
            exists_label=f"{path.name} 存在但无 categories 字段",
            proceed_label="执行 fetch_products_by_categoryid.py",
            block_message="",
        )

    if not isinstance(categories, list):
        result.update(
            ok=False,
            error=f"{path} 字段 categories 必须是数组",
            message="缓存文件结构不合法，请勿自动覆盖。",
        )
        return result

    entry = _find_category_in_list(categories, category_id)
    if entry is None:
        return _finalize_overwrite_result(
            result,
            overwrite_confirm=overwrite_confirm,
            exists=False,
            exists_label=f"categories 中尚无 categoryId={category_id}",
            proceed_label="执行 fetch_products_by_categoryid.py",
            block_message="",
        )

    products = entry.get("products")
    product_count = len(products) if isinstance(products, list) else 0
    result["category_exists"] = True
    result["existing_products_count"] = product_count

    return _finalize_overwrite_result(
        result,
        overwrite_confirm=overwrite_confirm,
        exists=True,
        exists_label=(
            f"parammodel.json 的 categories 中已存在 "
            f"categoryId={category_id}（约 {product_count} 个商品）"
        ),
        proceed_label="执行 fetch_products_by_categoryid.py",
        block_message=(
            f"parammodel.json 的 categories 中已存在 "
            f"categoryId={category_id}（约 {product_count} 个商品）。"
            "执行拉取前须向用户说明并询问是否覆盖；"
            "仅在用户明确肯定后，使用 --overwrite-confirm 传入其原话再执行拉取。"
        ),
    )


def check_feature3_overwrite(
    category_id: str,
    *,
    param_list_path: Path = DEFAULT_PARAM_LIST,
    overwrite_confirm: str | None = None,
) -> dict[str, Any]:
    path = param_list_path.resolve()
    result: dict[str, Any] = {
        "feature": 3,
        "category_id": category_id,
        "cache_file": str(path),
        "file_exists": path.is_file(),
        "category_exists": False,
        "needs_overwrite_confirm": False,
        "can_proceed": False,
        "existing_models_count": None,
    }

    if not path.is_file():
        return _finalize_overwrite_result(
            result,
            overwrite_confirm=overwrite_confirm,
            exists=False,
            exists_label=f"{path.name} 不存在",
            proceed_label="执行 fetch_parameters_by_categoryid.py",
            block_message="",
        )

    data, err = _load_json_object(path)
    if err:
        result.update(ok=False, error=err, message="缓存 JSON 损坏或不可读，请勿自动覆盖。")
        return result

    param_list = data.get("param_list") if data else None
    if param_list is None:
        return _finalize_overwrite_result(
            result,
            overwrite_confirm=overwrite_confirm,
            exists=False,
            exists_label=f"{path.name} 存在但无 param_list 字段",
            proceed_label="执行 fetch_parameters_by_categoryid.py",
            block_message="",
        )

    if not isinstance(param_list, list):
        result.update(
            ok=False,
            error=f"{path} 字段 param_list 必须是数组",
            message="缓存文件结构不合法，请勿自动覆盖。",
        )
        return result

    entry = _find_category_in_list(param_list, category_id)
    if entry is None:
        return _finalize_overwrite_result(
            result,
            overwrite_confirm=overwrite_confirm,
            exists=False,
            exists_label=f"param_list 中尚无 categoryId={category_id}",
            proceed_label="执行 fetch_parameters_by_categoryid.py",
            block_message="",
        )

    models = entry.get("models")
    model_count = len(models) if isinstance(models, list) else 0
    result["category_exists"] = True
    result["existing_models_count"] = model_count

    return _finalize_overwrite_result(
        result,
        overwrite_confirm=overwrite_confirm,
        exists=True,
        exists_label=(
            f"parammodel_param_list.json 的 param_list 中已存在 "
            f"categoryId={category_id}（约 {model_count} 条 model）"
        ),
        proceed_label="执行 fetch_parameters_by_categoryid.py",
        block_message=(
            f"parammodel_param_list.json 的 param_list 中已存在 "
            f"categoryId={category_id}（约 {model_count} 条 model）。"
            "执行拉取前须向用户说明并询问是否覆盖；"
            "仅在用户明确肯定后，使用 --overwrite-confirm 传入其原话再执行拉取。"
        ),
    )


def _product_ids_from_parammodel(
    parammodel_path: Path, category_id: str
) -> tuple[list[str], str | None]:
    data, err = _load_json_object(parammodel_path)
    if err:
        return [], err
    if data is None:
        return [], None
    categories = data.get("categories")
    if not isinstance(categories, list):
        return [], f"{parammodel_path} 字段 categories 必须是数组"
    entry = _find_category_in_list(categories, category_id)
    if entry is None:
        return [], f"parammodel.json 中无 categoryId={category_id}，请先执行功能 2"
    products = entry.get("products")
    if not isinstance(products, list):
        return [], None
    ids: list[str] = []
    for p in products:
        if isinstance(p, dict) and isinstance(p.get("obsBrandGoodId"), str):
            bgid = p["obsBrandGoodId"]
            if bgid:
                ids.append(bgid)
    return ids, None


def _existing_profile_ids(
    image_profile_path: Path, category_id: str
) -> tuple[set[str], dict[str, Any] | None, str | None]:
    data, err = _load_json_object(image_profile_path)
    if err:
        return set(), None, err
    if data is None:
        return set(), None, None
    category_list = data.get("category_list")
    if not isinstance(category_list, list):
        return set(), None, f"{image_profile_path} 字段 category_list 必须是数组"
    entry = _find_category_in_list(category_list, category_id)
    if entry is None:
        return set(), None, None
    profile_list = entry.get("profile_list")
    if not isinstance(profile_list, list):
        return set(), entry, None
    ids = {
        item.get("obsBrandGoodId")
        for item in profile_list
        if isinstance(item, dict) and isinstance(item.get("obsBrandGoodId"), str)
    }
    return {i for i in ids if i}, entry, None


def check_feature4_overwrite(
    category_id: str,
    *,
    image_profile_path: Path = DEFAULT_IMAGE_PROFILE,
    parammodel_path: Path = DEFAULT_PARAMMODEL,
    obs_brand_good_ids: list[str] | None = None,
    overwrite_confirm: str | None = None,
) -> dict[str, Any]:
    profile_path = image_profile_path.resolve()
    result: dict[str, Any] = {
        "feature": 4,
        "category_id": category_id,
        "cache_file": str(profile_path),
        "parammodel_file": str(parammodel_path.resolve()),
        "file_exists": profile_path.is_file(),
        "category_exists": False,
        "needs_overwrite_confirm": False,
        "can_proceed": False,
        "obs_brand_good_ids_checked": [],
        "existing_profile_ids": [],
        "missing_profile_ids": [],
        "profile_exists": False,
    }

    target_ids = list(obs_brand_good_ids or [])
    if not target_ids:
        target_ids, param_err = _product_ids_from_parammodel(
            parammodel_path.resolve(), category_id
        )
        if param_err:
            result.update(ok=False, error=param_err, message=param_err)
            return result
        if not target_ids:
            result.update(
                ok=True,
                can_proceed=True,
                needs_overwrite_confirm=False,
                message=(
                    f"categoryId={category_id} 在 parammodel.json 中无商品，"
                    "无需 profile 覆盖确认。"
                ),
            )
            return result

    result["obs_brand_good_ids_checked"] = target_ids

    existing_ids, category_entry, load_err = _existing_profile_ids(
        profile_path, category_id
    )
    if load_err:
        result.update(ok=False, error=load_err, message="缓存 JSON 损坏或不可读，请勿自动覆盖。")
        return result

    if category_entry is not None:
        result["category_exists"] = True

    checked_existing = [bgid for bgid in target_ids if bgid in existing_ids]
    checked_missing = [bgid for bgid in target_ids if bgid not in existing_ids]
    result["existing_profile_ids"] = checked_existing
    result["missing_profile_ids"] = checked_missing

    # 未指定单个/多个商品 ID：目录级盘点，默认仅补齐缺失，不阻断
    if obs_brand_good_ids is None:
        result.update(
            ok=True,
            can_proceed=True,
            needs_overwrite_confirm=False,
            profile_exists=bool(checked_existing),
            message=(
                f"已检查 {len(target_ids)} 个商品："
                f"{len(checked_existing)} 个已有 profile（合并时将跳过），"
                f"{len(checked_missing)} 个缺失可补齐。"
            ),
        )
        return result

    # 指定了 obsBrandGoodId：任一已有 profile 且未授权覆盖则阻断
    if not checked_existing:
        result.update(
            ok=True,
            can_proceed=True,
            needs_overwrite_confirm=False,
            profile_exists=False,
            message=(
                f"obsBrandGoodId={', '.join(target_ids)} 均无已有 profile，"
                "可继续图像分析与合并写入。"
            ),
        )
        return result

    result["profile_exists"] = True
    ids_text = ", ".join(checked_existing)
    if is_overwrite_confirm_text(overwrite_confirm):
        result.update(
            ok=True,
            can_proceed=True,
            needs_overwrite_confirm=False,
            message=(
                f"已确认覆盖 obsBrandGoodId={ids_text} 的已有 profile，"
                "可重新分析并合并（须确保合并脚本策略允许覆盖）。"
            ),
        )
        return result

    result.update(
        ok=True,
        can_proceed=False,
        needs_overwrite_confirm=True,
        message=(
            f"categoryId={category_id} 下已有 obsBrandGoodId={ids_text} 的 profile。"
            "功能 4 默认不覆盖已有 profile；若需重新分析该商品，"
            "须向用户说明并询问，确认后使用 --overwrite-confirm 传入用户原话。"
            "若仅补齐其余缺失商品，勿传 --obs-brand-good-id，改用目录级检查。"
        ),
    )
    return result


def _exit_from_result(result: dict[str, Any]) -> int:
    _emit_json(result)
    if not result.get("ok"):
        return 1
    return 0 if result.get("can_proceed") else 1


def _find_node_by_id(nodes: list[dict[str, Any]], target_id: str) -> dict[str, Any] | None:
    """在节点列表中递归查找指定 ID 的节点"""
    for node in nodes:
        if node.get("id") == target_id:
            return node
        if "kids" in node:
            found = _find_node_by_id(node["kids"], target_id)
            if found:
                return found
    return None


def _collect_all_category_ids(
    nodes: list[dict[str, Any]],
    result: list[str],
) -> None:
    """递归收集所有目录的 categoryId（不包含商品检查）"""
    for node in nodes:
        category_id = node.get("id")
        if category_id:
            result.append(category_id)
        if "kids" in node:
            _collect_all_category_ids(node["kids"], result)


def _collect_category_ids_with_products(
    nodes: list[dict[str, Any]],
    parammodel_data: dict[str, Any] | None,
    result: list[str],
) -> None:
    """递归收集所有包含商品的 categoryId"""
    if not parammodel_data:
        return

    categories = parammodel_data.get("categories", [])
    existing_category_ids = {cat.get("categoryId") for cat in categories if isinstance(cat, dict)}

    for node in nodes:
        category_id = node.get("id")
        if category_id and category_id in existing_category_ids:
            result.append(category_id)
        if "kids" in node:
            _collect_category_ids_with_products(node["kids"], parammodel_data, result)

def get_category_ids_with_products(
    category_id: str,
    *,
    product_categories_path: Path = PARAM_MODEL_LIBRARY / "product_categories.json",
    parammodel_path: Path = DEFAULT_PARAMMODEL,
) -> dict[str, Any]:
    """
    获取指定 categoryId 及其所有子目录的 categoryId 列表
    注意：不再从 parammodel.json 查询是否包含商品，而是返回所有子目录

    Args:
        category_id: 根目录 ID
        product_categories_path: product_categories.json 路径
        parammodel_path: parammodel.json 路径（保留参数但不再使用）

    Returns:
        {
            "ok": true/false,
            "category_ids": ["id1", "id2", ...],
            "message": "描述信息"
        }
    """
    result: dict[str, Any] = {
        "ok": False,
        "category_ids": [],
        "message": "",
    }

    # 读取 product_categories.json
    if not product_categories_path.is_file():
        result.update(
            message=f"{product_categories_path.name} 不存在，请先执行功能 1 更新目录树"
        )
        return result

    try:
        with product_categories_path.open("r", encoding="utf-8") as f:
            product_categories = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        result.update(message=f"无法解析 {product_categories_path}: {e}")
        return result

    # 查找根节点
    root_node = None
    for key in product_categories:
        if key == "meta":
            continue
        if isinstance(product_categories[key], list):
            found = _find_node_by_id(product_categories[key], category_id)
            if found:
                root_node = found
                break

    if not root_node:
        result.update(message=f"未找到 categoryId={category_id} 的目录")
        return result

    # 收集所有子目录的 categoryId（不再检查 parammodel.json）
    category_ids: list[str] = []
    _collect_all_category_ids([root_node], category_ids)

    if not category_ids:
        result.update(
            message=f"categoryId={category_id} 及其子目录中无目录数据"
        )
        return result

    result.update(
        ok=True,
        category_ids=category_ids,
        message=f"找到 {len(category_ids)} 个目录（包含自身及所有子目录）"
    )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="参数化模型库缓存覆盖前检查（model_cache_agent §3）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_common_overwrite_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("--category-id", required=True, help="目标 categoryId")
        p.add_argument(
            "--overwrite-confirm",
            default=None,
            help="用户明确覆盖授权的原话（须含「覆盖」等关键字）",
        )

    f2 = sub.add_parser("feature2", help="功能 2：检查 parammodel.json categories")
    add_common_overwrite_args(f2)
    f2.add_argument(
        "--parammodel",
        default=str(DEFAULT_PARAMMODEL),
        help="parammodel.json 路径",
    )

    f3 = sub.add_parser("feature3", help="功能 3：检查 parammodel_param_list.json")
    add_common_overwrite_args(f3)
    f3.add_argument(
        "--param-list",
        default=str(DEFAULT_PARAM_LIST),
        help="parammodel_param_list.json 路径",
    )

    f4 = sub.add_parser("feature4", help="功能 4：检查 parammodel_image_profile.json")
    add_common_overwrite_args(f4)
    f4.add_argument(
        "--image-profile",
        default=str(DEFAULT_IMAGE_PROFILE),
        help="parammodel_image_profile.json 路径",
    )
    f4.add_argument(
        "--parammodel",
        default=str(DEFAULT_PARAMMODEL),
        help="parammodel.json 路径（目录级检查时用于枚举商品）",
    )
    f4.add_argument(
        "--obs-brand-good-id",
        action="append",
        dest="obs_brand_good_ids",
        default=None,
        metavar="BGID",
        help="指定商品 ID（可重复传入）；省略则对照 parammodel 枚举全目录",
    )

    # 新增：获取包含商品的 categoryId 列表
    list_cats = sub.add_parser(
        "list-categories-with-products",
        help="获取指定 categoryId 及其子目录中包含商品的 categoryId 列表"
    )
    list_cats.add_argument("--category-id", required=True, help="根目录 categoryId")
    list_cats.add_argument(
        "--product-categories",
        default=str(PARAM_MODEL_LIBRARY / "product_categories.json"),
        help="product_categories.json 路径",
    )
    list_cats.add_argument(
        "--parammodel",
        default=str(DEFAULT_PARAMMODEL),
        help="parammodel.json 路径（用于判断哪些目录包含商品）",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "feature2":
        return _exit_from_result(
            check_feature2_overwrite(
                args.category_id,
                parammodel_path=Path(args.parammodel),
                overwrite_confirm=args.overwrite_confirm,
            )
        )

    if args.command == "feature3":
        return _exit_from_result(
            check_feature3_overwrite(
                args.category_id,
                param_list_path=Path(args.param_list),
                overwrite_confirm=args.overwrite_confirm,
            )
        )

    if args.command == "feature4":
        return _exit_from_result(
            check_feature4_overwrite(
                args.category_id,
                image_profile_path=Path(args.image_profile),
                parammodel_path=Path(args.parammodel),
                obs_brand_good_ids=args.obs_brand_good_ids,
                overwrite_confirm=args.overwrite_confirm,
            )
        )

    if args.command == "list-categories-with-products":
        result = get_category_ids_with_products(
            args.category_id,
            product_categories_path=Path(args.product_categories),
            parammodel_path=Path(args.parammodel),
        )
        _emit_json(result)
        return 0 if result.get("ok") else 1

    build_parser().error(f"未知子命令: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
