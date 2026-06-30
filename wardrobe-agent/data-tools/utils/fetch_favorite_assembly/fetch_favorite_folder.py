"""
从 login/status.json 读取 Cookie / 头等，请求 favorite_folder API，并用 crypt_h5 解密响应体。

共享逻辑见 fetch_common.py。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from pathlib import Path

UTILS_DIR = Path(__file__).resolve().parent.parent
if str(UTILS_DIR) not in sys.path:
    sys.path.insert(0, str(UTILS_DIR))

from login import DEFAULT_STATUS_FILE, prepare_headers_from_status

import fetch_common

FAVORITE_FOLDER_URL = "https://yun-beta.kujiale.com/dcscms/api/c/favorite_folder"


def build_favorite_folder_url(*, foldertype: int = 4) -> str:
    q = urllib.parse.urlencode(
        {
            "foldertype": str(foldertype),
            "x_plugin": "custom",
            "x_bz": "BIM",
            "locale": "zh_CN",
        }
    )
    return f"{FAVORITE_FOLDER_URL}?{q}"


def main() -> None:
    parser = argparse.ArgumentParser(description="从 status.json 拉取收藏夹文件夹并解密响应")
    parser.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_FILE,
        help="登录状态 status.json 路径（默认 data-tools/utils/login/status.json）",
    )
    parser.add_argument("--foldertype", type=int, default=4, help="文件夹类型，默认 4")
    parser.add_argument("--timeout", type=float, default=60.0, help="请求超时秒数")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="解密后的 JSON 写入该文件（UTF-8）",
    )
    parser.add_argument(
        "--raw-response",
        type=Path,
        help="同时将原始响应体字节写入路径（调试）",
    )
    args = parser.parse_args()

    if not args.status_file.exists():
        print(f"找不到登录状态文件: {args.status_file}", file=sys.stderr)
        sys.exit(2)

    try:
        hdrs = prepare_headers_from_status(args.status_file)
    except ValueError as e:
        print(f"读取登录状态失败: {e}", file=sys.stderr)
        sys.exit(2)

    fetch_common.warn_if_qunhe_jwt_stale(hdrs)

    url = build_favorite_folder_url(foldertype=args.foldertype)
    method = "GET"
    pu = urllib.parse.urlsplit(url)
    print(f"{method} {pu.scheme}://{pu.netloc}{pu.path or '/'} ...", file=sys.stderr)

    status, resp_hdrs, body = fetch_common.fetch_body(url, method, hdrs, args.timeout)
    if args.raw_response:
        args.raw_response.write_bytes(body)

    print(f"HTTP {status}", file=sys.stderr)
    ctype = resp_hdrs.get("Content-Type") or ""
    print(f"Content-Type: {ctype}", file=sys.stderr)

    if status >= 400:
        preview = body[:500].decode("utf-8", errors="replace")
        print(f"请求失败，原始响应前缀:\n{preview}", file=sys.stderr)
        if status == 401 and len(body) == 0:
            print(
                "提示: 空响应体 401 常为鉴权失败；请查看上方是否提示 qunhe-jwt 过期，"
                "或重新登录刷新 status.json。",
                file=sys.stderr,
            )
        sys.exit(1)

    try:
        plain = fetch_common.decrypt_response_body(body)
    except Exception as e:
        print(f"解密失败: {e}", file=sys.stderr)
        sys.exit(1)

    json.loads(plain)

    if args.output:
        args.output.write_text(plain, encoding="utf-8")
        print(f"已写入: {args.output}", file=sys.stderr)
    else:
        sys.stdout.buffer.write(plain.encode("utf-8"))
        if not plain.endswith("\n"):
            sys.stdout.buffer.write(b"\n")


if __name__ == "__main__":
    main()
