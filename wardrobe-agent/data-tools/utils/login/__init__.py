"""
登录模块

提供统一的登录状态管理和浏览器登录功能。

主要功能：
- 从 status.json 读取登录状态
- 检查登录状态是否过期
- 通过浏览器登录并更新 status.json
- 准备认证请求头
"""

from .status_manager import (
    DEFAULT_REFERER,
    DEFAULT_STATUS_FILE,
    DEFAULT_USER_AGENT,
    check_login_status,
    decode_jwt_payload,
    get_cookie,
    get_user_profile,
    is_cookie_expired,
    load_status,
    patch_user_profile,
    prepare_headers_from_status,
    prepare_headers_with_cookie,
    save_status,
)
from .browser_login import (
    DEFAULT_LOGIN_URL,
    backfill_user_profile,
    cookies_to_header,
    refresh_status_via_browser,
)

__all__ = [
    # status_manager
    "DEFAULT_REFERER",
    "DEFAULT_STATUS_FILE",
    "DEFAULT_USER_AGENT",
    "check_login_status",
    "decode_jwt_payload",
    "get_cookie",
    "get_user_profile",
    "is_cookie_expired",
    "load_status",
    "patch_user_profile",
    "prepare_headers_from_status",
    "prepare_headers_with_cookie",
    "save_status",
    # browser_login
    "DEFAULT_LOGIN_URL",
    "backfill_user_profile",
    "cookies_to_header",
    "refresh_status_via_browser",
]

__version__ = "1.0.0"