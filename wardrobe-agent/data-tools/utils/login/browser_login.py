"""
浏览器登录模块

通过 Playwright 打开浏览器，由用户手动登录后导出 Cookie 并写入 status.json。

不读取、不填写账号密码；仅等待 Cookie 中出现 qunhe-jwt 后更新鉴权片段。
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

if __name__ == "__main__":
    _utils_dir = Path(__file__).resolve().parent.parent
    if str(_utils_dir) not in sys.path:
        sys.path.insert(0, str(_utils_dir))

try:
    from login.status_manager import (
        DEFAULT_STATUS_FILE,
        JWT_COOKIE_NAME,
        check_login_status,
        patch_user_profile,
        save_status,
    )
except ImportError:
    from .status_manager import (
        DEFAULT_STATUS_FILE,
        JWT_COOKIE_NAME,
        check_login_status,
        patch_user_profile,
        save_status,
    )

DEFAULT_LOGIN_URL = "https://yun-beta.kujiale.com/cloud/tool/h5/bim"

_LOGIN_URL_MAP = {
    "beta": "https://yun-beta.kujiale.com/cloud/tool/h5/bim",
    "prod": "https://yun.kujiale.com/cloud/tool/h5/bim",
}


def _log(msg: str) -> None:
    print(f"[browser_login] {msg}", file=sys.stderr, flush=True)


def _looks_like_jwt(value: str) -> bool:
    """检查字符串是否像 JWT 格式"""
    if not value or "." not in value:
        return False
    parts = value.split(".")
    return len(parts) >= 3 and all(len(p) > 0 for p in parts[:3])


def _qunhe_jwt_not_expired(jwt: str) -> bool:
    """有 exp 时须未过期；无法解析 exp 时视为可用。"""
    if not _looks_like_jwt(jwt):
        return False
    try:
        import base64
        import json
        
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    except (ValueError, json.JSONDecodeError, IndexError, TypeError):
        return True
    exp = payload.get("exp")
    if exp is None:
        return True
    try:
        exp_s = float(exp)
    except (TypeError, ValueError):
        return True
    if exp_s > 1e12:
        exp_s /= 1000.0
    return exp_s >= time.time()


def _cookies_for_kujiale(cookies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """过滤出 kujiale.com 域名的 Cookie"""
    out: list[dict[str, Any]] = []
    for c in cookies:
        domain = (c.get("domain") or "").lower()
        if "kujiale.com" in domain or domain.endswith("kujiale.com"):
            out.append(c)
    return out


def cookies_to_header(cookies: list[dict[str, Any]]) -> str:
    """Playwright cookie 列表 → Cookie 请求头字符串。"""
    parts: list[str] = []
    seen: set[str] = set()
    for c in cookies:
        name = c.get("name")
        if not name or name in seen:
            continue
        seen.add(name)
        value = c.get("value")
        if value is None:
            continue
        parts.append(f"{name}={value}")
    return "; ".join(parts)


def _cookie_value(cookies: list[dict[str, Any]], name: str) -> str | None:
    """从 Cookie 列表中获取指定名称的值"""
    for c in cookies:
        if c.get("name") == name:
            v = c.get("value")
            return str(v) if v is not None else None
    return None


def _session_ready(cookies: list[dict[str, Any]]) -> bool:
    """仅当存在未过期的 qunhe-jwt（真 JWT）时视为已登录。"""
    raw = _cookie_value(cookies, JWT_COOKIE_NAME)
    if not raw:
        return False
    return _qunhe_jwt_not_expired(raw)


def _merge_user_profile(
    base: dict[str, str | None], new: dict[str, str | None]
) -> dict[str, str | None]:
    out = dict(base)
    for key in ("userId", "userName"):
        value = new.get(key)
        if value:
            out[key] = value
    return out


def _extract_user_profile_from_page(page: Any) -> dict[str, str | None]:
    """从云图页面全局变量读取用户名等信息（如 g_accountName）。"""
    if page is None:
        return {}
    try:
        if page.is_closed():
            return {}
    except Exception:
        return {}
    try:
        raw = page.evaluate(
            """() => {
                const profile = {};
                if (window.g_accountName) {
                    profile.userName = String(window.g_accountName).trim();
                }
                const uid =
                    window.g_userId ||
                    window.g_UserId ||
                    window.g_dontUseWillBeRemovedUserId;
                if (uid) profile.userId = String(uid).trim();
                for (const key of ["global_user", "maas_g_user"]) {
                    try {
                        const raw = window[key];
                        if (!raw) continue;
                        const obj = typeof raw === "string" ? JSON.parse(raw) : raw;
                        if (obj.userId && !profile.userId) {
                            profile.userId = String(obj.userId).trim();
                        }
                    } catch (e) {}
                }
                return profile;
            }"""
        )
    except Exception as exc:
        _log(f"Failed to extract user profile from page: {exc}")
        return {}
    if not isinstance(raw, dict):
        return {}
    return {
        "userId": (str(raw["userId"]).strip() if raw.get("userId") else None),
        "userName": (str(raw["userName"]).strip() if raw.get("userName") else None),
    }


def _cookie_header_to_playwright_cookies(cookie_header: str) -> list[dict[str, Any]]:
    cookies: list[dict[str, Any]] = []
    for segment in cookie_header.split(";"):
        segment = segment.strip()
        if "=" not in segment:
            continue
        name, _, value = segment.partition("=")
        name = name.strip()
        if not name:
            continue
        cookies.append(
            {
                "name": name,
                "value": value.strip(),
                "domain": ".kujiale.com",
                "path": "/",
            }
        )
    return cookies


def backfill_user_profile(
    status_file: Path | None = None,
    *,
    page_url: str | None = None,
    wait_ms: int = 5000,
) -> dict[str, Any]:
    """
    对已有 status.json 用无头浏览器访问云图页，补全 userName / userId。

    适用于旧版登录文件未写入用户名的场景。
    """
    if status_file is None:
        status_file = DEFAULT_STATUS_FILE
    status_file = status_file.resolve()

    login_status = check_login_status(status_file)
    if not login_status.get("ok"):
        raise RuntimeError(login_status.get("message") or "Login status is invalid")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "未安装 playwright。请执行: pip install playwright && playwright install chromium"
        ) from e

    try:
        from login.status_manager import load_status
    except ImportError:
        from .status_manager import load_status

    status = load_status(status_file)
    target_url = page_url or status.get("referer") or DEFAULT_LOGIN_URL
    cookies = _cookie_header_to_playwright_cookies(status["cookie"])

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="zh-CN")
        if cookies:
            context.add_cookies(cookies)
        page = context.new_page()
        try:
            page.goto(target_url, wait_until="domcontentloaded", timeout=120_000)
            page.wait_for_timeout(wait_ms)
            profile = _extract_user_profile_from_page(page)
        finally:
            browser.close()

    if profile.get("userId") or profile.get("userName"):
        patch_user_profile(
            status_file,
            user_id=profile.get("userId"),
            user_name=profile.get("userName"),
        )
        _log(
            "Backfilled user profile: "
            f"userName={profile.get('userName')!r}, userId={profile.get('userId')!r}"
        )
    return {
        "ok": True,
        "userId": profile.get("userId"),
        "userName": profile.get("userName"),
        "pageUrl": target_url,
    }


def _all_pages_closed(context: Any, browser: Any) -> bool:
    """检查浏览器所有页面是否已关闭"""
    if not browser.is_connected():
        return True
    pages = context.pages
    if not pages:
        return True
    return all(p.is_closed() for p in pages)


def _snapshot_session(
    context: Any, page: Any, login_url: str, user_agent: str
) -> tuple[bool, list[dict[str, Any]] | None, str, str, dict[str, str | None]]:
    """用 context 全部 Cookie 判断登录（避免域名字段过滤漏掉 qunhe-jwt）。"""
    referer = login_url
    user_profile: dict[str, str | None] = {}
    all_cookies = context.cookies()
    ready = _session_ready(all_cookies)
    saved = _cookies_for_kujiale(all_cookies) if ready else None
    if ready and not saved:
        saved = list(all_cookies)
    if ready:
        try:
            if page is not None and not page.is_closed():
                host = urlparse(page.url).netloc.lower()
                if "kujiale.com" in host:
                    referer = page.url
                user_agent = page.evaluate("() => navigator.userAgent")
                user_profile = _extract_user_profile_from_page(page)
        except Exception:
            pass
    return ready, saved, referer, user_agent, user_profile


def refresh_status_via_browser(
    status_file: Path | None = None,
    *,
    login_url: str | None = None,
    login_env: str | None = None,
    wait_timeout_s: float = 600.0,
    poll_interval_s: float = 1.5,
) -> dict[str, Any]:
    """
    打开 Chromium（有界面），等待用户手动登录，检测到 JWT Cookie 后写入 status.json。

    Args:
        status_file: 登录状态文件路径，默认为 DEFAULT_STATUS_FILE
        login_url: 登录页面 URL（优先级低于 login_env）
        login_env: 登录环境 "beta" 或 "prod"
        wait_timeout_s: 等待登录超时时间（秒）
        poll_interval_s: 轮询 Cookie 间隔（秒）

    Returns:
        包含操作结果的字典：
        - statusPath: str, 状态文件路径
        - elapsedSeconds: float, 用时（秒）
        - referer: str, Referer
        - loginUrl: str, 登录 URL
        - message: str, 操作消息

    Raises:
        RuntimeError: 未安装 playwright 或登录失败
        TimeoutError: 超时未完成登录
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "未安装 playwright。请执行: pip install playwright && playwright install chromium"
        ) from e

    if status_file is None:
        status_file = DEFAULT_STATUS_FILE

    # Resolve login URL: login_env > login_url > DEFAULT
    if login_env and login_env in _LOGIN_URL_MAP:
        login_url = _LOGIN_URL_MAP[login_env]
    if not login_url:
        login_url = DEFAULT_LOGIN_URL

    status_file = status_file.resolve()
    started = time.time()
    referer = login_url
    user_agent = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        session_ready = False
        saved_cookies: list[dict[str, Any]] | None = None
        user_profile: dict[str, str | None] = {}
        user_closed = False
        try:
            # Derive sign-in host from login_url:
            #   yun-beta.kujiale.com → beta.kujiale.com
            #   yun.kujiale.com      → www.kujiale.com
            parsed = urlparse(login_url)
            host = (parsed.hostname or "").lower()
            if host.startswith("yun-beta."):
                sign_in_host = host[len("yun-"):]  # beta.kujiale.com
            elif host.startswith("yun."):
                sign_in_host = "www." + host.split(".", 1)[1]  # www.kujiale.com
            else:
                sign_in_host = host
            sign_in_url = f"https://{sign_in_host}/signin?redir={login_url}"
            page.goto(sign_in_url, wait_until="domcontentloaded", timeout=120_000)

            deadline = time.time() + wait_timeout_s
            title_hinted = False
            # 用户关窗后 Playwright 进程可能仍 is_connected；须检测「所有页面已关闭」
            while time.time() < deadline:
                if _all_pages_closed(context, browser):
                    user_closed = True
                    _log("Detected browser window/page closed")
                    break

                try:
                    ready, saved, referer, user_agent, profile = _snapshot_session(
                        context, page, login_url, user_agent
                    )
                    if ready:
                        session_ready = True
                        saved_cookies = saved
                        user_profile = _merge_user_profile(user_profile, profile)
                        if not title_hinted:
                            title_hinted = True
                            _log("已检测到有效 qunhe-jwt，可关闭窗口保存 status.json")
                            try:
                                page.evaluate(
                                    """() => {
                                      document.title =
                                        '[已登录] 请关闭此窗口，将自动保存 status.json';
                                    }"""
                                )
                            except Exception:
                                pass
                except Exception as e:
                    _log(f"Cookie polling exception (will treat as window closed): {e}")
                    user_closed = True
                    break

                time.sleep(poll_interval_s)

            # 关窗后再取一次 Cookie（此时 context 往往仍可读）
            if user_closed or _all_pages_closed(context, browser):
                user_closed = True
                try:
                    ready, saved, referer, user_agent, profile = _snapshot_session(
                        context, page, login_url, user_agent
                    )
                    if ready:
                        session_ready = True
                        saved_cookies = saved
                        user_profile = _merge_user_profile(user_profile, profile)
                        _log("Post-close snapshot: Login cookies obtained")
                except Exception as e:
                    _log(f"Failed to read cookies after window closed: {e}")

            if not session_ready:
                if user_closed:
                    names = [c.get("name") for c in (context.cookies() if browser.is_connected() else [])]
                    _log(f"Cookie name list at window close: {names}")
                    raise RuntimeError(
                        "Browser closed, but no valid qunhe-jwt detected."
                        " Please confirm you have opened a project in the cloud tool and completed login,"
                        " then close the window after seeing the tab title '[已登录]'."
                    )
                raise TimeoutError(
                    f"在 {int(wait_timeout_s)} 秒内未完成登录。"
                    " 请登录并关闭浏览器窗口，或检查是否误关过早。"
                )

            if saved_cookies is None:
                saved_cookies = []

            cookie_header = cookies_to_header(saved_cookies)
            if not cookie_header.strip():
                raise RuntimeError("Login state detected, but failed to assemble Cookie header")
            _log(f"Writing to status.json, approximately {len(saved_cookies)} cookie items")
        finally:
            try:
                if browser.is_connected():
                    browser.close()
            except Exception:
                pass

    # 使用 status_manager 模块保存登录状态
    save_status(
        cookie_header,
        referer,
        user_agent,
        status_file,
        user_id=user_profile.get("userId"),
        user_name=user_profile.get("userName"),
    )
    if user_profile.get("userName"):
        _log(
            "Saved user profile: "
            f"userName={user_profile.get('userName')!r}, "
            f"userId={user_profile.get('userId')!r}"
        )

    elapsed = round(time.time() - started, 1)
    return {
        "statusPath": str(status_file),
        "elapsedSeconds": elapsed,
        "referer": referer,
        "loginUrl": login_url,
        "userId": user_profile.get("userId"),
        "userName": user_profile.get("userName"),
        "message": f"Updated login status ({elapsed}s)",
    }


def _resolve_status_file(path: str | None) -> Path:
    if path:
        return Path(path).expanduser().resolve()
    return DEFAULT_STATUS_FILE.resolve()


def _emit_json(data: dict[str, Any]) -> None:
    print(json.dumps(data, ensure_ascii=False))


def run_check_login(status_file: Path | None = None) -> int:
    """
    检查登录状态并打印 JSON 到 stdout。

    Returns:
        0 表示 ok，1 表示无效或检查失败。
    """
    path = (status_file or DEFAULT_STATUS_FILE).resolve()
    result = check_login_status(path)
    _emit_json(result)
    return 0 if result.get("ok") else 1


def run_browser_login(
    status_file: Path | None = None,
    *,
    login_url: str = DEFAULT_LOGIN_URL,
    wait_timeout_s: float = 600.0,
    poll_interval_s: float = 1.5,
) -> int:
    """
    打开浏览器登录并打印结果 JSON 到 stdout。

    Returns:
        0 成功，1 失败。
    """
    path = (status_file or DEFAULT_STATUS_FILE).resolve()
    try:
        result = refresh_status_via_browser(
            path,
            login_url=login_url,
            wait_timeout_s=wait_timeout_s,
            poll_interval_s=poll_interval_s,
        )
    except Exception as e:
        _emit_json({"ok": False, "error": str(e)})
        return 1
    out = {"ok": True, **result}
    _emit_json(out)
    return 0


def run_ensure_login(
    status_file: Path | None = None,
    *,
    login_url: str = DEFAULT_LOGIN_URL,
    wait_timeout_s: float = 600.0,
    poll_interval_s: float = 1.5,
) -> int:
    """
    确保登录状态，未登录时自动触发浏览器登录流程。

    成功时向 stdout 打印 ``Login successful``；失败时向 stdout 打印 JSON 错误。

    Returns:
        0 表示已登录或登录成功，1 表示登录失败。
    """
    path = (status_file or DEFAULT_STATUS_FILE).resolve()

    status = check_login_status(path)

    if status.get("ok"):
        print("Login successful")
        return 0

    # Not logged in, execute login process
    _log("Not logged in, starting browser login...")
    try:
        refresh_status_via_browser(
            path,
            login_url=login_url,
            wait_timeout_s=wait_timeout_s,
            poll_interval_s=poll_interval_s,
        )
        _log("Login process completed, checking login status again...")

        status = check_login_status(path)
        if status.get("ok"):
            print("Login successful")
            return 0
        _log("Post-login status check failed")
        _emit_json({"ok": False, "error": "Post-login status check failed"})
        return 1
    except Exception as e:
        _log(f"Login process error: {e}")
        _emit_json({"ok": False, "error": str(e)})
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="检查或刷新 utils/login/status.json（浏览器手动登录）",
    )
    parser.add_argument(
        "--status-file",
        default=None,
        help=f"登录状态文件路径（默认 {DEFAULT_STATUS_FILE}）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="检查 status.json 是否存在且 Cookie 未过期")

    login_p = sub.add_parser(
        "login",
        help="弹出 Chromium，手动登录后关窗写入 status.json",
    )
    login_p.add_argument(
        "--login-url",
        default=DEFAULT_LOGIN_URL,
        help="登录页 URL",
    )
    login_p.add_argument(
        "--wait-timeout",
        type=float,
        default=600.0,
        help="等待登录超时（秒，默认 600）",
    )
    login_p.add_argument(
        "--poll-interval",
        type=float,
        default=1.5,
        help="轮询 Cookie 间隔（秒，默认 1.5）",
    )

    ensure_p = sub.add_parser(
        "ensure",
        help="确保登录状态，未登录时自动触发浏览器登录流程",
    )
    ensure_p.add_argument(
        "--login-url",
        default=DEFAULT_LOGIN_URL,
        help="登录页 URL",
    )
    ensure_p.add_argument(
        "--wait-timeout",
        type=float,
        default=600.0,
        help="等待登录超时（秒，默认 600）",
    )
    ensure_p.add_argument(
        "--poll-interval",
        type=float,
        default=1.5,
        help="轮询 Cookie 间隔（秒，默认 1.5）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    status_file = _resolve_status_file(args.status_file)

    if args.command == "check":
        return run_check_login(status_file)

    if args.command == "login":
        return run_browser_login(
            status_file,
            login_url=args.login_url,
            wait_timeout_s=args.wait_timeout,
            poll_interval_s=args.poll_interval,
        )

    if args.command == "ensure":
        return run_ensure_login(
            status_file,
            login_url=args.login_url,
            wait_timeout_s=args.wait_timeout,
            poll_interval_s=args.poll_interval,
        )

    build_parser().error(f"未知子命令: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())