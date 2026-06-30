import argparse
import json
import sys
from pathlib import Path
from typing import Any

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from fetch_model_library.api import get_catalogue_tree


REPO_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_FILE = (
    REPO_ROOT / "workspace" / "data" / "param-model-library" / "product_categories.json"
)


def dump_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch catalogue tree and write product_categories.json.")
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    tree = get_catalogue_tree()
    out = Path(args.output)
    dump_json(out, tree)
    print(f"Wrote catalogue tree to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
