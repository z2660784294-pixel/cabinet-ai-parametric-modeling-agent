"""
拉取 bgcollections/v2（指定 folderid），Cookie 从 login/status.json 读取。

解密：crypt_h5.full_decrypt（--all）；失败则 auto_decrypt。
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

BG_COLLECTIONS_V2_URL = "https://yun-beta.kujiale.com/dcs-search/api/c/bgcollections/v2"


def build_bg_collections_url(
    folder_id: int | str,
    *,
    num: int = 40,
    start: int = 0,
    foldertype: int = 4,
) -> str:
    q = urllib.parse.urlencode(
        {
            "num": str(num),
            "start": str(start),
            "folderid": str(folder_id),
            "foldertype": str(foldertype),
            "needChannel": "true",
            "fetchValidation": "false",
            "compress": "1",
            "x_plugin": "custom",
            "x_bz": "BIM",
            "locale": "zh_CN",
        }
    )
    return f"{BG_COLLECTIONS_V2_URL}?{q}"


def main() -> None:
    p = argparse.ArgumentParser(description="按 folderId 请求 bgcollections/v2 并解密 JSON")
    p.add_argument(
        "folder_id",
        type=str,
        help="收藏夹文件夹 ID（对应 API 查询参数 folderid）",
    )
    p.add_argument(
        "--num",
        type=int,
        default=40,
        help="分页条数，默认 40",
    )
    p.add_argument(
        "--start",
        type=int,
        default=0,
        help="分页起点，默认 0",
    )
    p.add_argument(
        "--foldertype",
        type=int,
        default=4,
        help="文件夹类型，默认 4（与示例 URL 一致）",
    )
    p.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_FILE,
        help="登录状态 status.json 路径（默认 data-tools/utils/login/status.json）",
    )
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("-o", "--output", type=Path, help="解密后 JSON 输出路径")
    p.add_argument("--raw-response", type=Path, help="保存上游原始响应体（调试）")
    p.add_argument(
        "--referer",
        type=str,
        default=None,
        help="强制 Referer（默认：若 fetch 里指向 /dcscms/ 则改用工具页）",
    )
    p.add_argument(
        "--origin",
        type=str,
        default=None,
        help="强制 Origin（默认: https://yun-beta.kujiale.com）",
    )
    p.add_argument(
        "--no-header-fix",
        action="store_true",
        help="不调整 Referer/Origin/Sec-Fetch-*（仅调试用；易出现 401）",
    )
    p.add_argument(
        "--jwt-bearer",
        action="store_true",
        help="把 Cookie 里的 qunhe-jwt 额外写入 Authorization: Bearer（默认不加，与浏览器 fetch 一致）",
    )
    args = p.parse_args()

    if not args.status_file.exists():
        print(f"找不到登录状态文件: {args.status_file}", file=sys.stderr)
        sys.exit(2)

    try:
        raw_headers = prepare_headers_from_status(args.status_file)
    except ValueError as e:
        print(f"读取登录状态失败: {e}", file=sys.stderr)
        sys.exit(2)

    fetch_common.warn_if_qunhe_jwt_stale(raw_headers)

    had_auth = any(k.lower() == "authorization" for k in raw_headers)

    headers = fetch_common.prepare_bgcollections_headers(
        raw_headers,
        referer_override=args.referer,
        origin_override=args.origin,
        skip_augment=args.no_header_fix,
        attach_bearer=args.jwt_bearer,
    )

    has_auth = any(k.lower() == "authorization" for k in headers)
    if has_auth and not had_auth:
        print("已从 Cookie 注入 Authorization: Bearer <JWT>（--jwt-bearer）", file=sys.stderr)
    elif args.jwt_bearer and not has_auth:
        print(
            "提示: 使用了 --jwt-bearer 但未能设置 Authorization（Cookie 中可能无 qunhe-jwt）。",
            file=sys.stderr,
        )

    url = build_bg_collections_url(
        args.folder_id,
        num=args.num,
        start=args.start,
        foldertype=args.foldertype,
    )
    pu = urllib.parse.urlsplit(url)
    print(
        f"GET {pu.scheme}://{pu.netloc}{pu.path or '/'} ..."
        f" folderid={args.folder_id} start={args.start} num={args.num}",
        file=sys.stderr,
    )

    status, resp_hdrs, body = fetch_common.fetch_body(url, "GET", headers, args.timeout)
    if args.raw_response:
        args.raw_response.write_bytes(body)

    print(f"HTTP {status}", file=sys.stderr)
    print(f"Content-Type: {resp_hdrs.get('Content-Type', '')}", file=sys.stderr)
    www_auth = resp_hdrs.get("WWW-Authenticate") or resp_hdrs.get("www-authenticate")
    if www_auth:
        print(f"WWW-Authenticate: {www_auth}", file=sys.stderr)

    if status >= 400:
        preview = body[:500].decode("utf-8", errors="replace")
        print(f"请求失败，原始响应前缀:\n{preview}", file=sys.stderr)
        if status == 401:
            print(
                "提示: 401 多为鉴权/网关拒绝。脚本会按需补 Referer/Origin、Sec-Fetch-*（若导出无）、"
                "x-bz、X-Requested-With；Cookie 默认不另加 Bearer（与浏览器一致）。"
                "若 HTTP 401 且响应体为空，常见为 qunhe-jwt 已过期，请重新登录刷新 status.json。"
                "仍失败可：① --referer；② 试 --jwt-bearer。",
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
