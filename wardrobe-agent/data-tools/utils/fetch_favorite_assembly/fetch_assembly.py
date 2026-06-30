"""
按 bgId 请求 assemblyattach（Zstd body），Cookie / 鉴权从 login/status.json 读取。

请求体由 crypt_zstd 压缩并 Base64，与前端 ParamModel 请求一致。
运行时勿依赖 fetch_attach.txt（该文件仅作实现时的接口参考）。
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

try:
    from crypt_zstd import decrypt_body_base64, encrypt_body_to_base64
except ImportError:  # pragma: no cover
    print(
        "缺少依赖：在本目录执行 pip install -r requirements.txt",
        file=sys.stderr,
    )
    raise SystemExit(2)

# 来自接口参考（fetch_attach.txt）；运行时不要求该文件存在。
_ASSEMBLY_ZSTD_BASE = (
    "https://yun-beta.kujiale.com/custom-model-task/api/encrypt/assemblyattach/zstd"
)
_ASSEMBLY_QUERY = {
    "compress": "1",
    "x_plugin": "custom",
    "x_bz": "BIM",
    "locale": "zh_CN",
}


def build_assembly_url() -> str:
    q = urllib.parse.urlencode(_ASSEMBLY_QUERY)
    return f"{_ASSEMBLY_ZSTD_BASE}?{q}"


def build_request_payload_bytes(bg_id: int) -> bytes:
    obj = {
        "bgId": bg_id,
        "useLatestReleaseAllLevel": True,
        "needResource": False,
        "zstdWithBase64": True,
    }
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def prepare_assembly_post_headers(
    base: dict[str, str],
    raw_json_len: int,
) -> dict[str, str]:
    """在已通过 prepare/enrich 的头之上补 assemblyattach POST 所需字段。"""
    h = dict(base)
    h["Accept"] = "text/plain,*/*,application/zstd;charset=UTF-8"
    h["Content-Type"] = "application/zstd"
    h["x-raw-data-length"] = str(raw_json_len)
    if fetch_common._find_header(h, "x-qh-locale")[0] is None:
        h["x-qh-locale"] = "zh_CN"
    if fetch_common._find_header(h, "x-tool-name")[0] is None:
        h["x-tool-name"] = "diy"
    if fetch_common._find_header(h, "x-plugin-resource-id")[0] is None:
        h["x-plugin-resource-id"] = "undefined"
    if fetch_common._find_header(h, "x-plugin-resource-version")[0] is None:
        h["x-plugin-resource-version"] = "undefined"
    return h


def decrypt_assembly_response(raw: bytes) -> str:
    """响应多为 Base64(Zstd) 文本；否则再按 H5 密文处理。"""
    text = raw.decode("utf-8", errors="replace").strip()
    if text.startswith("{") or text.startswith("["):
        return text
    try:
        out = decrypt_body_base64(text)
        return out.decode("utf-8")
    except Exception:
        pass
    return fetch_common.decrypt_response_body(raw)


def main() -> None:
    p = argparse.ArgumentParser(
        description="按 bgId 请求 assemblyattach（body 为 crypt_zstd 加密 JSON）",
    )
    p.add_argument("bg_id", type=int, help="商品/方案 bgId")
    p.add_argument(
        "--status-file",
        type=Path,
        default=DEFAULT_STATUS_FILE,
        help="登录状态 status.json 路径（默认 data-tools/utils/login/status.json）",
    )
    p.add_argument("--timeout", type=float, default=60.0)
    p.add_argument("-o", "--output", type=Path, help="解密后的 JSON 输出路径")
    p.add_argument("--raw-response", type=Path, help="保存原始响应体字节（调试）")
    p.add_argument(
        "-l",
        "--level",
        type=int,
        default=1,
        help="Zstd 等级，与 crypt_zstd / TS 默认一致为 1",
    )
    p.add_argument(
        "--referer",
        type=str,
        default=None,
        help="强制 Referer（默认由 fetch_common 按 dcs-search 场景补全）",
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
        help="不调整 Referer/Origin/Sec-Fetch-*（仅调试用）",
    )
    p.add_argument(
        "--jwt-bearer",
        action="store_true",
        help="把 Cookie 里的 qunhe-jwt 写入 Authorization: Bearer",
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

    payload = build_request_payload_bytes(args.bg_id)
    b64_body = encrypt_body_to_base64(payload, level=args.level)
    post_bytes = b64_body.encode("ascii")

    headers = fetch_common.prepare_bgcollections_headers(
        raw_headers,
        referer_override=args.referer,
        origin_override=args.origin,
        skip_augment=args.no_header_fix,
        attach_bearer=args.jwt_bearer,
    )

    headers = prepare_assembly_post_headers(headers, raw_json_len=len(payload))

    url = build_assembly_url()
    pu = urllib.parse.urlsplit(url)
    print(
        f"POST {pu.scheme}://{pu.netloc}{pu.path or '/'} ... bgId={args.bg_id}",
        file=sys.stderr,
    )

    status, resp_hdrs, body = fetch_common.fetch_body(
        url,
        "POST",
        headers,
        args.timeout,
        data=post_bytes,
    )

    if args.raw_response:
        args.raw_response.write_bytes(body)

    print(f"HTTP {status}", file=sys.stderr)
    print(f"Content-Type: {resp_hdrs.get('Content-Type', '')}", file=sys.stderr)

    if status >= 400:
        preview = body[:800].decode("utf-8", errors="replace")
        print(f"请求失败，原始响应前缀:\n{preview}", file=sys.stderr)
        sys.exit(1)

    try:
        plain = decrypt_assembly_response(body)
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
