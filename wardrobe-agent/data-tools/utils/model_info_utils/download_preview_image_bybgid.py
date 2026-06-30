#!/usr/bin/env python3
"""Download a parametric product preview image by BGID via direct HTTP API."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

UTILS_DIR = Path(__file__).resolve().parents[1]
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from fetch_model_library.api import ApiError, get_product_preview_img_url
from fetch_combo_case_data import download_preview


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download previewImage for a BGID by querying the API directly."
    )
    parser.add_argument("bgid", help="obsBrandGoodId, e.g. 3FO3JCVO58AE")
    parser.add_argument("output_dir", help="Folder to write the image into")
    parser.add_argument("--output-name", default="previewImage.png", help="Output filename")
    parser.add_argument("--overwrite", action="store_true", help="Re-fetch image even if output already exists")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_path = Path(args.output_dir).resolve() / args.output_name

    try:
        preview_url = get_product_preview_img_url(args.bgid)
        if not preview_url:
            raise ApiError(f"Product has no previewImgUrl: {args.bgid}")

        preview_result = download_preview(preview_url, output_path, args.overwrite)

        print(
            json.dumps(
                {
                    "status": "success",
                    "bgid": args.bgid,
                    "previewImgUrl": preview_url,
                    "output": str(output_path),
                    "previewImage": preview_result,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        print(json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
