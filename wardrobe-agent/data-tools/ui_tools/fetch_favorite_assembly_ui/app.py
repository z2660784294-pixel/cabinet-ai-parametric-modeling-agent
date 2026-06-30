"""
本地网页：用给定 login/status.json 中的 cookie 依次浏览收藏夹目录 → 目录内商品（brandGoodId）→
导出封面图、abd.json、parammodel_param_list.json、assembly.json（每项商品单独子目录），并在页面第三栏展示。

用法（在 data-tools 目录）：
    python ui_tools/fetch_favorite_assembly_ui/app.py
可选：
    python ui_tools/fetch_favorite_assembly_ui/app.py --port 8765
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import re
import shutil
import socket
import sys
import threading
import webbrowser
from pathlib import Path

from flask import Flask, abort, jsonify, render_template, request, send_file

DATA_TOOLS_ROOT = Path(__file__).resolve().parent.parent.parent
FFA_DIR = DATA_TOOLS_ROOT / "utils" / "fetch_favorite_assembly"
UI_ROOT = Path(__file__).resolve().parent
EXPORTS_ROOT = UI_ROOT / "exports"
LOGIN_STATUS_FILE = DATA_TOOLS_ROOT / "utils" / "login" / "status.json"

# 导入登录管理模块
sys.path.insert(0, str(DATA_TOOLS_ROOT / "utils"))
from login import (
    check_login_status,
    get_cookie,
    is_cookie_expired,
    prepare_headers_with_cookie,
    refresh_status_via_browser,
)

REPO_ROOT = DATA_TOOLS_ROOT.parent
WORKSPACE_ROOT = REPO_ROOT / "workspace"
WORKSPACE_TMP = WORKSPACE_ROOT / "tmp"
WORKSPACE_AGENT_INPUT = WORKSPACE_TMP / "input"

sys.path.insert(0, str(FFA_DIR))

import fetch_common  # noqa: E402
from fetch_bg_collections import build_bg_collections_url  # noqa: E402
from generate_assembly_abd import export_assembly_abd_bundle  # noqa: E402
from fetch_assembly import (  # noqa: E402
    build_assembly_url,
    build_request_payload_bytes,
    decrypt_assembly_response,
    prepare_assembly_post_headers,
)
from crypt_zstd import encrypt_body_to_base64  # noqa: E402


app = Flask(__name__, template_folder=str(Path(__file__).resolve().parent / "templates"))

_BROWSER_LOGIN_LOCK = threading.Lock()
_BROWSER_LOGIN_JOB: dict[str, object] = {
    "status": "idle",  # idle | running | success | error
    "message": None,
    "error": None,
    "result": None,
}

_EXPORT_ID_RE = re.compile(r"^folder_\d+_bg_\d+$")


def _export_dir_segment(folder_id: str, brand_good_id: int) -> str:
    return f"folder_{folder_id}_bg_{int(brand_good_id)}"


def _clear_workspace_tmp() -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "clear_tmp",
        WORKSPACE_ROOT / "utils" / "clear_tmp.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载 workspace/utils/clear_tmp.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.clear_tmp(WORKSPACE_TMP)


def _safe_export_dir(export_id: str) -> Path:
    if not _EXPORT_ID_RE.fullmatch(export_id.strip()):
        raise ValueError("无效的 exportId")
    base = EXPORTS_ROOT.resolve()
    target = (base / export_id.strip()).resolve()
    try:
        target.relative_to(base)
    except ValueError as e:
        raise ValueError("无效的导出路径") from e
    return target


def _fetch_folders(*, timeout: float) -> list[dict]:
    cookie = get_cookie(LOGIN_STATUS_FILE)
    if is_cookie_expired(cookie):
        raise RuntimeError("登录已过期，请重新登录")
    
    headers = prepare_headers_with_cookie(cookie)
    url = "https://yun-beta.kujiale.com/dcscms/api/c/favorite_folder?foldertype=4&x_plugin=custom&x_bz=BIM&locale=zh_CN"
    
    status, _resp_hdrs, body = fetch_common.fetch_body(url, "GET", headers, timeout)
    if status >= 400:
        preview = body[:800].decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {status}，响应前缀:\n{preview}")
    plain = fetch_common.decrypt_response_body(body)
    root = json.loads(plain)
    data = root.get("data")
    if not isinstance(data, list):
        raise ValueError("favorite_folder 解密 JSON 缺少 data 数组")
    out: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        fid = item.get("folderId")
        name = item.get("name")
        if fid is None:
            continue
        out.append(
            {
                "folderId": fid,
                "name": str(name) if name is not None else "",
                "folderType": item.get("folderType"),
                "modifiable": item.get("modifiable"),
            }
        )
    return out


def _fetch_folder_goods(
    folder_id: str,
    *,
    foldertype: int,
    timeout: float,
    jwt_bearer: bool,
    page_size: int = 40,
) -> tuple[list[dict], int | None]:
    cookie = get_cookie(LOGIN_STATUS_FILE)
    if is_cookie_expired(cookie):
        raise RuntimeError("登录已过期，请重新登录")
    
    headers = prepare_headers_with_cookie(cookie)
    if jwt_bearer:
        headers = fetch_common.enrich_bgcollections_auth_headers(headers, attach_bearer=True)
    
    all_rows: list[dict] = []
    start = 0
    total_count: int | None = None
    while True:
        url = build_bg_collections_url(
            folder_id, num=page_size, start=start, foldertype=foldertype
        )
        status, _rh, body = fetch_common.fetch_body(url, "GET", headers, timeout)
        if status >= 400:
            preview = body[:800].decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {status}，响应前缀:\n{preview}")
        plain = fetch_common.decrypt_response_body(body)
        obj = json.loads(plain)
        if total_count is None and "count" in obj:
            try:
                total_count = int(obj["count"])
            except (TypeError, ValueError):
                total_count = None
        batch = obj.get("data")
        if not isinstance(batch, list):
            batch = []
        for row in batch:
            if not isinstance(row, dict):
                continue
            bg = row.get("brandGoodId")
            if bg is None:
                continue
            try:
                bg_int = int(bg)
            except (TypeError, ValueError):
                continue
            obs = row.get("obsBrandGoodId")
            all_rows.append(
                {
                    "brandGoodId": bg_int,
                    "obsBrandGoodId": obs if isinstance(obs, str) else None,
                    "name": row.get("name") if isinstance(row.get("name"), str) else "",
                    "previewImgUrl": row.get("previewImgUrl"),
                    "coverImgUrl": row.get("coverImgUrl"),
                    "productType": row.get("productType"),
                }
            )
        if len(batch) < page_size:
            break
        start += page_size
        if total_count is not None and start >= total_count:
            break
    return all_rows, total_count


def _fetch_assembly(
    bg_id: int,
    *,
    timeout: float,
    jwt_bearer: bool,
    zstd_level: int,
) -> object:
    cookie = get_cookie(LOGIN_STATUS_FILE)
    if is_cookie_expired(cookie):
        raise RuntimeError("登录已过期，请重新登录")
    
    headers = prepare_headers_with_cookie(cookie)
    if jwt_bearer:
        headers = fetch_common.enrich_bgcollections_auth_headers(headers, attach_bearer=True)
    
    payload = build_request_payload_bytes(bg_id)
    b64_body = encrypt_body_to_base64(payload, level=zstd_level)
    post_bytes = b64_body.encode("ascii")
    headers = prepare_assembly_post_headers(headers, raw_json_len=len(payload))
    url = build_assembly_url()
    status, _rh, body = fetch_common.fetch_body(
        url, "POST", headers, timeout, data=post_bytes
    )
    if status >= 400:
        preview = body[:800].decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {status}，响应前缀:\n{preview}")
    plain = decrypt_assembly_response(body)
    return json.loads(plain)


def _debug_tool_from_request() -> bool:
    """URL 含 ?__debug_tool=true 时显示环境预览等调试 UI。"""
    v = (request.args.get("__debug_tool") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


@app.route("/")
def index():
    login_status = check_login_status(LOGIN_STATUS_FILE)
    return render_template(
        "ffa_browse.html",
        data_tools_root=str(DATA_TOOLS_ROOT),
        exports_root=str(EXPORTS_ROOT.resolve()),
        workspace_agent_input=str(WORKSPACE_AGENT_INPUT.resolve()),
        debug_tool=_debug_tool_from_request(),
        logged_in=bool(login_status.get("ok")),
    )


def _browser_login_worker(*, wait_timeout_s: float) -> None:
    global _BROWSER_LOGIN_JOB  # noqa: PLW0603
    print(f"[ffa_ui] 浏览器登录线程开始 → {LOGIN_STATUS_FILE}", file=sys.stderr, flush=True)
    try:
        result = refresh_status_via_browser(
            LOGIN_STATUS_FILE,
            wait_timeout_s=wait_timeout_s,
        )
        with _BROWSER_LOGIN_LOCK:
            _BROWSER_LOGIN_JOB = {
                "status": "success",
                "message": result.get("message"),
                "error": None,
                "result": result,
            }
        print(
            f"[ffa_ui] 浏览器登录已更新 status.json: {LOGIN_STATUS_FILE}",
            file=sys.stderr,
        )
    except Exception as e:
        with _BROWSER_LOGIN_LOCK:
            _BROWSER_LOGIN_JOB = {
                "status": "error",
                "message": None,
                "error": str(e),
                "result": None,
            }
        print(f"[ffa_ui] 浏览器登录失败: {e}", file=sys.stderr)


@app.route("/api/browser-login/check", methods=["GET"])
def api_browser_login_check():
    """检查登录状态文件是否存在以及 cookie 是否过期"""
    try:
        status = check_login_status(LOGIN_STATUS_FILE)
        return jsonify(status)
    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 400


@app.route("/api/browser-login/start", methods=["POST"])
def api_browser_login_start():
    """打开 Playwright 浏览器，由用户手动登录后更新 status.json（后台线程）。"""
    payload = request.get_json(silent=True) or {}
    wait_timeout = float(payload.get("waitTimeout") or payload.get("wait_timeout") or 600.0)

    with _BROWSER_LOGIN_LOCK:
        if _BROWSER_LOGIN_JOB.get("status") == "running":
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": "已有登录窗口任务进行中，请先在弹出浏览器中完成登录或等待结束",
                        "job": dict(_BROWSER_LOGIN_JOB),
                    }
                ),
                409,
            )
        _BROWSER_LOGIN_JOB.clear()
        _BROWSER_LOGIN_JOB.update(
            {
                "status": "running",
                "message": (
                    "已打开 Chromium 窗口，请在其中手动登录（含勾选用户协议）。"
                    " 登录成功后窗口标题会提示「已登录」——请再手动关闭该窗口，"
                    " 才会写入 status.json（不会登录后立刻关窗）。"
                ),
                "error": None,
                "result": None,
            }
        )

    t = threading.Thread(
        target=_browser_login_worker,
        kwargs={"wait_timeout_s": wait_timeout},
        daemon=True,
    )
    t.start()
    print(
        f"[ffa_ui] 请在弹出的 Chromium 中手动登录，目标 status.json: {LOGIN_STATUS_FILE}",
        file=sys.stderr,
    )
    return jsonify(
        {
            "ok": True,
            "status": "running",
            "message": _BROWSER_LOGIN_JOB["message"],
        }
    )


@app.route("/api/browser-login/status", methods=["GET"])
def api_browser_login_status():
    with _BROWSER_LOGIN_LOCK:
        job = dict(_BROWSER_LOGIN_JOB)
    status = job.get("status") or "idle"
    out: dict[str, object] = {"ok": True, "status": status}
    if job.get("message"):
        out["message"] = job["message"]
    if job.get("error"):
        out["error"] = job["error"]
    if job.get("result"):
        out["result"] = job["result"]
    if status == "error":
        out["ok"] = False
    return jsonify(out), (200 if status != "error" else 502)


@app.route("/api/folders", methods=["POST"])
def api_folders():
    payload = request.get_json(silent=True) or {}
    timeout = float(payload.get("timeout") or 60.0)
    try:
        folders = _fetch_folders(timeout=timeout)
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify(
        {
            "ok": True,
            "folders": folders,
        }
    )


@app.route("/api/folder-goods", methods=["POST"])
def api_folder_goods():
    payload = request.get_json(silent=True) or {}
    folder_id = payload.get("folderId") or payload.get("folder_id")
    foldertype = int(payload.get("foldertype") or payload.get("folderType") or 4)
    timeout = float(payload.get("timeout") or 60.0)
    jwt_bearer = bool(payload.get("jwtBearer") or payload.get("jwt_bearer"))
    if folder_id is None:
        return jsonify({"ok": False, "error": "缺少 folderId"}), 400
    folder_id_str = str(folder_id).strip()
    if not folder_id_str:
        return jsonify({"ok": False, "error": "folderId 为空"}), 400
    try:
        goods, total_count = _fetch_folder_goods(
            folder_id_str,
            foldertype=foldertype,
            timeout=timeout,
            jwt_bearer=jwt_bearer,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify(
        {
            "ok": True,
            "folderId": folder_id_str,
            "count": total_count,
            "goods": goods,
        }
    )


@app.route("/api/assembly", methods=["POST"])
def api_assembly():
    payload = request.get_json(silent=True) or {}
    bg_raw = payload.get("brandGoodId") or payload.get("bgId") or payload.get("bg_id")
    timeout = float(payload.get("timeout") or 60.0)
    jwt_bearer = bool(payload.get("jwtBearer") or payload.get("jwt_bearer"))
    zstd_level = int(payload.get("zstdLevel") or payload.get("zstd_level") or 1)
    if bg_raw is None:
        return jsonify({"ok": False, "error": "缺少 brandGoodId"}), 400
    try:
        bg_id = int(bg_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "brandGoodId 须为整数"}), 400
    try:
        asm = _fetch_assembly(
            bg_id,
            timeout=timeout,
            jwt_bearer=jwt_bearer,
            zstd_level=zstd_level,
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502
    return jsonify({"ok": True, "brandGoodId": bg_id, "assembly": asm})


@app.route("/api/export-abd", methods=["POST"])
def api_export_abd():
    payload = request.get_json(silent=True) or {}
    folder_id = payload.get("folderId") or payload.get("folder_id")
    foldertype = int(payload.get("foldertype") or payload.get("folderType") or 4)
    bg_raw = payload.get("brandGoodId") or payload.get("bgId") or payload.get("bg_id")
    timeout = float(payload.get("timeout") or 120.0)
    jwt_bearer = bool(payload.get("jwtBearer") or payload.get("jwt_bearer"))
    zstd_level = int(payload.get("zstdLevel") or payload.get("zstd_level") or 1)
    if folder_id is None:
        return jsonify({"ok": False, "error": "缺少 folderId"}), 400
    folder_id_str = str(folder_id).strip()
    if not folder_id_str:
        return jsonify({"ok": False, "error": "folderId 为空"}), 400
    if bg_raw is None:
        return jsonify({"ok": False, "error": "缺少 brandGoodId"}), 400
    try:
        bg_id = int(bg_raw)
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "brandGoodId 须为整数"}), 400

    export_id = _export_dir_segment(folder_id_str, bg_id)
    out_dir = EXPORTS_ROOT / export_id

    try:
        result = export_assembly_abd_bundle(
            LOGIN_STATUS_FILE,
            folder_id_str,
            bg_id,
            out_dir,
            foldertype=foldertype,
            timeout=timeout,
            jwt_bearer=jwt_bearer,
            zstd_level=zstd_level,
            ignore_cover_download_errors=True,
        )
    except LookupError as e:
        return jsonify({"ok": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    cover_file_name: str | None = None
    cv = result.get("cover_image_path")
    if isinstance(cv, str) and cv.strip():
        cover_file_name = Path(cv).name

    resp = {
        "ok": True,
        "exportId": export_id,
        "outputDir": result["output_dir"],
        "abdJsonPath": result["abd_json_path"],
        "assemblyJsonPath": result["assembly_json_path"],
        "parammodelParamListPath": result["parammodel_param_list_json_path"],
        "coverImagePath": result.get("cover_image_path"),
        "coverFileName": cover_file_name,
        "coverUrl": (
            f"/api/exports/{export_id}/{cover_file_name}" if cover_file_name else None
        ),
        "abd": result["abd"],
    }
    err = result.get("cover_download_error")
    if err:
        resp["coverDownloadError"] = err
    return jsonify(resp)


@app.route("/api/copy-to-agent", methods=["POST"])
def api_copy_to_agent():
    """清空 workspace/tmp 后：abd.json、cover、param_current.json→tmp/input。"""
    payload = request.get_json(silent=True) or {}
    raw_id = payload.get("exportId") or payload.get("export_id")
    if not isinstance(raw_id, str) or not raw_id.strip():
        return jsonify({"ok": False, "error": "缺少 exportId"}), 400
    try:
        export_dir = _safe_export_dir(raw_id)
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400
    if not export_dir.is_dir():
        return jsonify({"ok": False, "error": f"导出目录不存在: {export_dir}"}), 404

    abd_src = export_dir / "abd.json"
    if not abd_src.is_file():
        return jsonify({"ok": False, "error": "当前导出目录缺少 abd.json"}), 400
    pml_src = export_dir / "parammodel_param_list.json"
    if not pml_src.is_file():
        return jsonify({"ok": False, "error": "当前导出目录缺少 parammodel_param_list.json"}), 400

    # 同步阻塞：clear_tmp 返回后才继续；下方校验确保未清干净时不拷贝
    cleared = _clear_workspace_tmp()
    if WORKSPACE_TMP.is_dir():
        remaining = [p.name for p in WORKSPACE_TMP.iterdir()]
        if remaining:
            return (
                jsonify(
                    {
                        "ok": False,
                        "error": f"清空 tmp 未完成，仍存在: {remaining}",
                    }
                ),
                500,
            )

    WORKSPACE_AGENT_INPUT.mkdir(parents=True, exist_ok=True)

    # 写入 abd.json 时注入 use_current 标记，供 query_param_list 优先查找 current-value 文件
    abd_dest = WORKSPACE_AGENT_INPUT / "abd.json"
    with abd_src.open(encoding="utf-8") as f:
        abd_data = json.load(f)
    abd_data["use_current"] = True
    with abd_dest.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(abd_data, f, ensure_ascii=False, indent=2)
        f.write("\n")

    param_current_dest = WORKSPACE_AGENT_INPUT / "param_current.json"
    shutil.copy2(pml_src, param_current_dest)

    cover_copied: str | None = None
    cover_warn: str | None = None
    cover_candidates = sorted(export_dir.glob("cover.*"))
    if cover_candidates:
        shutil.copy2(cover_candidates[0], WORKSPACE_AGENT_INPUT / "cover.jpg")
        cover_copied = str((WORKSPACE_AGENT_INPUT / "cover.jpg").resolve())
    else:
        cover_warn = "导出目录下无 cover.*，未写入 workspace/tmp/input/cover.jpg"

    return jsonify(
        {
            "ok": True,
            "tmpCleared": cleared,
            "agentInputDir": str(WORKSPACE_AGENT_INPUT.resolve()),
            "abdDest": str((WORKSPACE_AGENT_INPUT / "abd.json").resolve()),
            "paramCurrentValueDest": str(param_current_dest.resolve()),
            "coverDest": cover_copied,
            "coverWarn": cover_warn,
        }
    )


@app.route("/api/exports/<export_id>/<filename>")
def api_exports_file(export_id: str, filename: str):
    if not _EXPORT_ID_RE.fullmatch(export_id):
        abort(404)
    safe = Path(filename).name
    if safe != filename:
        abort(404)
    allowed_named = safe in (
        "abd.json",
        "assembly.json",
        "parammodel_param_list.json",
        "parammodel_param_list_backup.json",
    )
    if not allowed_named and not (
        safe.startswith("cover.") or safe.startswith("preview.")
    ):
        abort(404)
    base = EXPORTS_ROOT.resolve()
    target = (base / export_id / safe).resolve()
    try:
        target.relative_to(base)
    except ValueError:
        abort(404)
    if not target.is_file():
        abort(404)
    return send_file(target, conditional=True)


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser(description="本地浏览收藏夹 → 商品 → assembly（依赖 login/status.json）")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0, help="0 表示自动分配端口")
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    args = parser.parse_args()

    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    port = args.port or _find_free_port()
    url = f"http://{args.host}:{port}"
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    EXPORTS_ROOT.mkdir(parents=True, exist_ok=True)
    print(f"[ffa_ui] 请在浏览器打开: {url}", file=sys.stderr)
    print(f"[ffa_ui] data-tools 根目录: {DATA_TOOLS_ROOT}", file=sys.stderr)
    print(f"[ffa_ui] 商品导出目录: {EXPORTS_ROOT.resolve()}", file=sys.stderr)
    print(f"[ffa_ui] 登录状态文件: {LOGIN_STATUS_FILE.resolve()}", file=sys.stderr)
    app.run(host=args.host, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
