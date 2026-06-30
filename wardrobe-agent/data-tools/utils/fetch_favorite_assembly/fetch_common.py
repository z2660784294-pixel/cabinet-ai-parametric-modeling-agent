"""
共用：补全/修正请求头、发 HTTP、用 crypt_h5 按「完整包」解密响应。

供 fetch_favorite_folder.py、fetch_bg_collections.py 等同目录脚本使用。
"""

from __future__ import annotations

import json
import re
import sys
import time
import base64
import urllib.error
import urllib.request
from typing import Any

import crypt_h5

# dcs-search 与 dcscms 接口对「页面上下文」校验不同；Referer 不匹配容易导致 401
YUN_BETA_ORIGIN = "https://yun-beta.kujiale.com"
DCS_SEARCH_FALLBACK_REFERER = f"{YUN_BETA_ORIGIN}/cloud/tool/h5/bim"


def _find_header(headers: dict[str, str], name_lower: str) -> tuple[str | None, str | None]:
    for k, v in headers.items():
        if k.lower() == name_lower:
            return k, v
    return None, None


def augment_headers_for_dcs_search(
    headers: dict[str, str],
    *,
    referer_override: str | None = None,
    origin_override: str | None = None,
) -> dict[str, str]:
    """
    /dcs-search 等接口常与 /dcscms 请求的 Referer/Origin、Sec-Fetch-* 不一致时返回 401。
    - 若 Referer 指向 dcms 等业务路径且无 dcs-search，则改用工具页 Referer；
    - 若缺少 Origin，则补站点 Origin；
    - 若复制片段未带 Sec-Fetch-*，则按需补浏览器常见值。
    """
    h = dict(headers)

    origin_val = origin_override if origin_override is not None else YUN_BETA_ORIGIN
    ok, _ = _find_header(h, "origin")
    if ok is None:
        h["Origin"] = origin_val
    elif origin_override is not None:
        del h[ok]
        h["Origin"] = origin_override

    rk, rv = _find_header(h, "referer")

    def _apply_referer(new_val: str) -> None:
        nonlocal rk, rv
        if rk:
            del h[rk]
        rk, rv = None, None
        h["Referer"] = new_val

    if referer_override:
        _apply_referer(referer_override)
    elif rv and rv.strip():
        ref = rv.strip()
        if "/dcscms/" in ref and "/dcs-search" not in ref.lower():
            _apply_referer(DCS_SEARCH_FALLBACK_REFERER)
    else:
        _apply_referer(DCS_SEARCH_FALLBACK_REFERER)

    for name, default_val in (
        ("Sec-Fetch-Mode", "cors"),
        ("Sec-Fetch-Site", "same-origin"),
        ("Sec-Fetch-Dest", "empty"),
    ):
        nk, _ = _find_header(h, name.lower())
        if nk is None:
            h[name] = default_val

    return h


def _cookie_get(cookie_header: str, cookie_name_lower: str) -> str | None:
    for segment in cookie_header.split(";"):
        segment = segment.strip()
        if "=" not in segment:
            continue
        k, _, v = segment.partition("=")
        if k.strip().lower() != cookie_name_lower:
            continue
        return v.strip().strip('"').strip("'")
    return None


def _looks_like_jwt(value: str) -> bool:
    if not value or "." not in value:
        return False
    parts = value.split(".")
    return len(parts) >= 3 and all(len(p) > 0 for p in parts[:3])


def warn_if_qunhe_jwt_stale(headers: dict[str, str]) -> None:
    """
    Cookie 里 qunhe-jwt 的 exp 若为毫秒级（>1e12）则换算为秒，与网关行为对齐；
    已过期时在 stderr 提示刷新 status.json。
    """
    _, cookie = _find_header(headers, "cookie")
    if not cookie:
        return
    raw = _cookie_get(cookie, "qunhe-jwt")
    if not raw or not _looks_like_jwt(raw):
        return
    try:
        payload_b64 = raw.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError, IndexError, TypeError):
        return
    exp = payload.get("exp")
    if exp is None:
        return
    try:
        exp_s = float(exp)
    except (TypeError, ValueError):
        return
    if exp_s > 1e12:
        exp_s /= 1000.0
    if exp_s >= time.time():
        return
    print(
        "提示: Cookie 中 qunhe-jwt 已过期（空响应 401 多由此引起），请重新登录刷新 status.json。",
        file=sys.stderr,
    )


def enrich_bgcollections_auth_headers(
    headers: dict[str, str], *, attach_bearer: bool = False
) -> dict[str, str]:
    """
    bgcollections 等与浏览器请求对齐时通常仅 Cookie（含 qunhe-jwt），不再额外加 Bearer，避免双轨鉴权被网关拒。
    attach_bearer=True 时：从 Cookie 抽取 JWT 写入 Authorization: Bearer（少数环境需要）。
    并补 x-bz、x-plugin-name、X-Requested-With 等与查询参数常见一致的业务头。
    """
    h = dict(headers)

    _, cookie = _find_header(h, "cookie")
    if attach_bearer and cookie:
        ak, _ = _find_header(h, "authorization")
        if ak is None:
            for cand in ("qunhe-jwt", "jwt-qunhequnhesso-test"):
                raw = _cookie_get(cookie, cand)
                if not raw:
                    continue
                if _looks_like_jwt(raw):
                    h["Authorization"] = f"Bearer {raw}"
                    break

    if _find_header(h, "x-bz")[0] is None:
        h["x-bz"] = "BIM"
    if _find_header(h, "x-plugin-name")[0] is None:
        h["x-plugin-name"] = "custom"

    nk, _ = _find_header(h, "x-requested-with")
    if nk is None:
        h["X-Requested-With"] = "XMLHttpRequest"

    return h


def prepare_bgcollections_headers(
    headers: dict[str, str],
    *,
    referer_override: str | None = None,
    origin_override: str | None = None,
    skip_augment: bool = False,
    skip_enrich: bool = False,
    attach_bearer: bool = False,
) -> dict[str, str]:
    """bgcollections/v2：Referer/Origin + x-bz 等；Bearer 默认不加，需时传 attach_bearer=True。"""
    if skip_augment:
        h = dict(headers)
    else:
        h = augment_headers_for_dcs_search(
            headers,
            referer_override=referer_override,
            origin_override=origin_override,
        )
    if skip_enrich:
        return h
    return enrich_bgcollections_auth_headers(h, attach_bearer=attach_bearer)


def _canonical_header_dict(h: dict[str, str]) -> dict[str, str]:
    return {lk: lv for lk, lv in ((k.lower(), v) for k, v in h.items())}


def fetch_body(
    url: str,
    method: str,
    headers: dict[str, str],
    timeout_s: float,
    *,
    data: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    hdrs = _canonical_header_dict(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            body = resp.read()
            hd = dict(resp.headers.items())
            return resp.status, hd, body
    except urllib.error.HTTPError as e:
        raw = e.read()
        hd = dict(e.headers.items()) if e.headers else {}
        return e.code, hd, raw


def decrypt_response_body(raw: bytes) -> str:
    """先识别明文 JSON；再 full_decrypt（--all）；最后 auto_decrypt。"""
    charset = None
    m = re.search(rb"charset=([\w\-]+)", raw[:200])
    if m:
        charset = m.group(1).decode("ascii")
    encoding = charset or "utf-8"

    text = raw.decode(encoding, errors="replace").strip()
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff").strip()

    head = text[:200].lstrip().lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        raise ValueError(
            "响应为 HTML 页面而非 favorite_folder 密文，常见原因：登录态失效、"
            "status.json 中登录态失效、Referer 与当前环境不一致，或被重定向到登录页。"
            f" 响应前缀: {text[:300]!r}"
        )

    if text.startswith("{") or text.startswith("["):
        return text

    try:
        return crypt_h5.full_decrypt(text)
    except ValueError:
        pass
    try:
        return crypt_h5.auto_decrypt(text)
    except ValueError as e:
        preview = text[:120].replace("\n", " ")
        raise ValueError(
            f"{e}。响应前缀（供排查）: {preview!r}。"
            " 请重新登录刷新 status.json，或加 --raw-response 保存原始响应比对。"
        ) from e
