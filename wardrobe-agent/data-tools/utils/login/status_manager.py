"""
登录状态管理模块

负责：
1. 从 status.json 读取登录状态
2. 检查登录状态是否过期
3. 写入登录状态到 status.json
4. 提供统一的 cookie 获取接口
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

# 默认登录状态文件路径
DEFAULT_STATUS_FILE = Path(__file__).resolve().parent / "status.json"

# JWT Cookie 名称
JWT_COOKIE_NAME = "qunhe-jwt"

DEFAULT_REFERER = "https://yun-beta.kujiale.com/cloud/tool/h5/bim"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
)


def _looks_like_jwt(value: str) -> bool:
    """检查字符串是否像 JWT 格式"""
    if not value or "." not in value:
        return False
    parts = value.split(".")
    return len(parts) >= 3 and all(len(p) > 0 for p in parts[:3])


def decode_jwt_payload(jwt: str) -> dict[str, Any]:
    """解析 qunhe-jwt 的 payload 段。"""
    if not _looks_like_jwt(jwt):
        return {}
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        return payload if isinstance(payload, dict) else {}
    except (ValueError, json.JSONDecodeError, IndexError, TypeError):
        return {}


def _get_jwt_expiry(jwt: str) -> float | None:
    """从 JWT 中获取过期时间（秒级时间戳）"""
    if not _looks_like_jwt(jwt):
        return None
    try:
        payload_b64 = jwt.split(".")[1]
        payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        exp = payload.get("exp")
        if exp is None:
            return None
        exp_s = float(exp)
        if exp_s > 1e12:  # 毫秒级时间戳
            exp_s /= 1000.0
        return exp_s
    except (ValueError, json.JSONDecodeError, IndexError, TypeError):
        return None


def _extract_cookie_from_header(cookie_header: str, cookie_name: str) -> str | None:
    """从 Cookie 请求头中提取指定 cookie 的值"""
    for segment in cookie_header.split(";"):
        segment = segment.strip()
        if "=" not in segment:
            continue
        k, _, v = segment.partition("=")
        if k.strip().lower() == cookie_name.lower():
            return v.strip().strip('"').strip("'")
    return None


def is_cookie_expired(cookie_header: str) -> bool:
    """
    检查 Cookie 中的 JWT 是否已过期
    
    Args:
        cookie_header: Cookie 请求头字符串
        
    Returns:
        True 表示已过期或无法判断，False 表示未过期
    """
    jwt = _extract_cookie_from_header(cookie_header, JWT_COOKIE_NAME)
    if not jwt:
        return False  # 无法判断，假设未过期
    
    expiry = _get_jwt_expiry(jwt)
    if expiry is None:
        return False  # 无法解析过期时间，假设未过期
    
    return expiry < time.time()


def load_status(status_file: Path | None = None) -> dict[str, Any]:
    """
    从 status.json 加载登录状态
    
    Args:
        status_file: 登录状态文件路径，默认为 DEFAULT_STATUS_FILE
        
    Returns:
        包含登录状态的字典，包含 cookie、referer、userAgent、updatedAt 等字段
        
    Raises:
        FileNotFoundError: 状态文件不存在
        ValueError: 状态文件格式错误或缺少必要字段
    """
    if status_file is None:
        status_file = DEFAULT_STATUS_FILE
    
    if not status_file.is_file():
        raise FileNotFoundError(f"找不到登录状态文件: {status_file}")
    
    try:
        data = json.loads(status_file.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"status.json 格式错误: {e}") from e
    
    # 验证必要字段
    if not isinstance(data, dict):
        raise ValueError("status.json 内容应为 JSON 对象")
    
    cookie = data.get("cookie")
    if not cookie or not isinstance(cookie, str):
        raise ValueError("status.json 中缺少 cookie 字段或 cookie 为空")
    
    return data


def get_cookie(status_file: Path | None = None) -> str:
    """
    从 status.json 获取 Cookie 请求头
    
    Args:
        status_file: 登录状态文件路径，默认为 DEFAULT_STATUS_FILE
        
    Returns:
        Cookie 请求头字符串
        
    Raises:
        FileNotFoundError: 状态文件不存在
        ValueError: 状态文件格式错误或缺少 cookie
    """
    status = load_status(status_file)
    return status["cookie"]


def check_login_status(status_file: Path | None = None) -> dict[str, Any]:
    """
    检查登录状态
    
    Args:
        status_file: 登录状态文件路径，默认为 DEFAULT_STATUS_FILE
        
    Returns:
        包含检查结果的字典：
        - ok: bool, 登录状态是否有效
        - message: str, 状态描述（英文，供 CLI/自动化解析）
        - expired: bool, 是否已过期
    """
    try:
        status = load_status(status_file)
        cookie = status["cookie"]
        
        if is_cookie_expired(cookie):
            return {
                "ok": False,
                "expired": True,
                "message": "Login expired; please sign in again",
            }
        
        return {
            "ok": True,
            "expired": False,
            "message": "Login session is valid",
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "expired": False,
            "message": "Login status file not found",
        }
    except ValueError as e:
        return {
            "ok": False,
            "expired": False,
            "message": f"Invalid login status file: {e}",
        }


def save_status(
    cookie_header: str,
    referer: str,
    user_agent: str,
    status_file: Path | None = None,
    *,
    user_id: str | None = None,
    user_name: str | None = None,
) -> None:
    """
    保存登录状态到 status.json
    
    Args:
        cookie_header: Cookie 请求头字符串
        referer: Referer 请求头
        user_agent: User-Agent 请求头
        status_file: 登录状态文件路径，默认为 DEFAULT_STATUS_FILE
        user_id: 用户 ID（如 3FO4MFO1HW36）
        user_name: 显示名称（如云图页 window.g_accountName）
    """
    if status_file is None:
        status_file = DEFAULT_STATUS_FILE
    
    status_data: dict[str, Any] = {
        "cookie": cookie_header,
        "referer": referer,
        "userAgent": user_agent,
        "updatedAt": time.time(),
    }
    if user_id:
        status_data["userId"] = str(user_id)
    if user_name:
        status_data["userName"] = str(user_name)
    
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with status_file.open("w", encoding="utf-8") as f:
        json.dump(status_data, f, ensure_ascii=False, indent=2)


def get_user_profile(status_file: Path | None = None) -> dict[str, Any]:
    """
    从 status.json 读取用户展示信息；userId 可回退到 JWT 中的 k_id。
    """
    try:
        status = load_status(status_file)
    except (FileNotFoundError, ValueError):
        return {"userId": None, "userName": None, "updatedAt": None}

    user_id = status.get("userId") or status.get("user_id")
    user_name = status.get("userName") or status.get("user_name")

    if not user_id:
        jwt = _extract_cookie_from_header(status["cookie"], JWT_COOKIE_NAME)
        if jwt:
            claims = decode_jwt_payload(jwt)
            user_id = claims.get("k_id") or claims.get("s_id")

    return {
        "userId": user_id,
        "userName": user_name,
        "updatedAt": status.get("updatedAt"),
    }


def patch_user_profile(
    status_file: Path | None = None,
    *,
    user_id: str | None = None,
    user_name: str | None = None,
) -> None:
    """在保留 cookie 等字段的前提下，更新 status.json 中的用户信息。"""
    if status_file is None:
        status_file = DEFAULT_STATUS_FILE
    status = load_status(status_file)
    changed = False
    if user_id and status.get("userId") != str(user_id):
        status["userId"] = str(user_id)
        changed = True
    if user_name and status.get("userName") != str(user_name):
        status["userName"] = str(user_name)
        changed = True
    if not changed:
        return
    status_file.parent.mkdir(parents=True, exist_ok=True)
    with status_file.open("w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)


def prepare_headers_with_cookie(
    cookie_header: str,
    referer: str | None = None,
    user_agent: str | None = None,
) -> dict[str, str]:
    """
    使用 cookie 准备请求头
    
    Args:
        cookie_header: Cookie 请求头字符串
        referer: Referer 请求头，默认为云图工具页
        user_agent: User-Agent 请求头，默认为 Chrome
        
    Returns:
        包含请求头的字典
    """
    if referer is None:
        referer = DEFAULT_REFERER

    if user_agent is None:
        user_agent = DEFAULT_USER_AGENT

    return {
        "Accept": "text/plain,*/*",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7,zh-TW;q=0.6,pl;q=0.5",
        "Referer": referer,
        "Cookie": cookie_header,
        "User-Agent": user_agent,
        "Origin": "https://yun-beta.kujiale.com",
        "x-plugin-name": "custom",
        "x-qh-locale": "zh_CN",
        "x-tool-name": "diy",
        "x-bz": "BIM",
    }


def prepare_headers_from_status(status_file: Path | None = None) -> dict[str, str]:
    """
    从 status.json 读取登录状态并准备请求头
    
    Args:
        status_file: 登录状态文件路径，默认为 DEFAULT_STATUS_FILE
        
    Returns:
        包含请求头的字典
        
    Raises:
        FileNotFoundError: 状态文件不存在
        ValueError: 状态文件格式错误或缺少必要字段
    """
    status = load_status(status_file)
    return prepare_headers_with_cookie(
        cookie_header=status["cookie"],
        referer=status.get("referer"),
        user_agent=status.get("userAgent"),
    )