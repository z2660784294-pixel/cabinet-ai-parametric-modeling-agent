"""
Wardrobe Agent 桌面启动器：后台静默启动 MCP Server，并管理登录态。

用法：
    python data-tools/ui_tools/launcher/launcher.py   # Windows / macOS / Linux
    双击 launcher.bat 或 launcher.pyw（Windows）或 launcher.command（macOS）
    若 .pyw 双击无反应，多为系统将其关联到了 Python 2.7，请改用 launcher.bat
需已通过 wain/setup.ps1 或 setup_mac.sh 完成环境准备。
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import traceback
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

LAUNCHER_DIR = Path(__file__).resolve().parent
DATA_TOOLS_ROOT = LAUNCHER_DIR.parent.parent
AGENT_ROOT = DATA_TOOLS_ROOT.parent
WAIN_ROOT = AGENT_ROOT.parent
MCP_ROOT = WAIN_ROOT / "mcp-server"
LOGIN_STATUS_FILE = DATA_TOOLS_ROOT / "utils" / "login" / "status.json"
BRIDGE_LOCK_DIR = Path.home() / ".koomaster" / "bridge-locks"
LOG_FILE = LAUNCHER_DIR / "launcher.log"

CREATE_NO_WINDOW = 0x08000000
POLL_INTERVAL_MS = 2000
BRIDGE_LOCK_RE = re.compile(r"bridge-(\d+)-(\d+)\.lock")


def _subprocess_hide_window_kwargs() -> dict[str, Any]:
    """Windows 静默子进程；Unix 使用独立进程组便于停止整棵进程树。"""
    if sys.platform == "win32":
        return {"creationflags": CREATE_NO_WINDOW}
    return {"start_new_session": True}


sys.path.insert(0, str(DATA_TOOLS_ROOT / "utils"))
from login import (  # noqa: E402
    backfill_user_profile,
    check_login_status,
    get_user_profile,
    refresh_status_via_browser,
)

_PROFILE_BACKFILL_LOCK = threading.Lock()
_PROFILE_BACKFILL_STATE: dict[str, Any] = {
    "status": "idle",  # idle | running | done | error
    "error": None,
}

_BROWSER_LOGIN_LOCK = threading.Lock()
_BROWSER_LOGIN_JOB: dict[str, Any] = {
    "status": "idle",
    "message": None,
    "error": None,
    "result": None,
}

_CUSTOM_LOGIN_ENV: str | None = None


def _log(msg: str) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}\n"
    try:
        with LOG_FILE.open("a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        synchronize = 0x00100000
        handle = kernel32.OpenProcess(synchronize, False, pid)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _signal_pid(pid: int, sig: int) -> None:
    import signal

    try:
        os.killpg(os.getpgid(pid), sig)
        return
    except (ProcessLookupError, PermissionError):
        pass
    except OSError:
        pass
    os.kill(pid, sig)


def _kill_process_tree(pid: int) -> None:
    if pid <= 0 or not _is_process_running(pid):
        return
    _log(f"Stopping MCP process pid={pid}")
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            creationflags=CREATE_NO_WINDOW,
            check=False,
            capture_output=True,
        )
        return

    import signal

    try:
        result = subprocess.run(
            ["pgrep", "-P", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        for line in (result.stdout or "").splitlines():
            if line.strip().isdigit():
                _kill_process_tree(int(line.strip()))
    except OSError:
        pass

    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            _signal_pid(pid, sig)
        except ProcessLookupError:
            return
        time.sleep(0.3)
        if not _is_process_running(pid):
            return


def get_login_profile() -> dict[str, Any]:
    status = check_login_status(LOGIN_STATUS_FILE)
    profile: dict[str, Any] = {
        "ok": bool(status.get("ok")),
        "expired": bool(status.get("expired")),
        "message": status.get("message") or "",
        "userId": None,
        "userLabel": None,
        "updatedAt": None,
    }
    if not profile["ok"]:
        return profile
    user = get_user_profile(LOGIN_STATUS_FILE)
    profile["userId"] = user.get("userId")
    profile["userLabel"] = user.get("userName")
    profile["updatedAt"] = user.get("updatedAt")
    return profile


def _profile_backfill_worker() -> None:
    global _PROFILE_BACKFILL_STATE  # noqa: PLW0603
    try:
        backfill_user_profile(LOGIN_STATUS_FILE)
        with _PROFILE_BACKFILL_LOCK:
            _PROFILE_BACKFILL_STATE = {"status": "done", "error": None}
    except Exception as exc:
        _log(f"Profile backfill failed: {exc}")
        with _PROFILE_BACKFILL_LOCK:
            _PROFILE_BACKFILL_STATE = {"status": "error", "error": str(exc)}


def maybe_backfill_user_profile() -> None:
    """旧版 status.json 无 userName 时，后台无头补全一次。"""
    profile = get_login_profile()
    if not profile.get("ok") or profile.get("userLabel"):
        return
    with _PROFILE_BACKFILL_LOCK:
        if _PROFILE_BACKFILL_STATE.get("status") in ("running", "done"):
            return
        _PROFILE_BACKFILL_STATE["status"] = "running"
        _PROFILE_BACKFILL_STATE["error"] = None
    thread = threading.Thread(target=_profile_backfill_worker, daemon=True)
    thread.start()


def discover_active_bridges() -> list[dict[str, int]]:
    if not BRIDGE_LOCK_DIR.is_dir():
        return []
    bridges: list[dict[str, int]] = []
    for path in BRIDGE_LOCK_DIR.glob("bridge-*-*.lock"):
        match = BRIDGE_LOCK_RE.fullmatch(path.name)
        if not match:
            continue
        pid = int(match.group(1))
        port = int(match.group(2))
        if _is_process_running(pid):
            bridges.append({"pid": pid, "port": port})
    bridges.sort(key=lambda item: item["port"])
    return bridges


class McpProcessManager:
    def __init__(self) -> None:
        self._proc: subprocess.Popen[Any] | None = None
        self._log_handle: Any = None
        self._start_error: str | None = None
        self.started_by_launcher = False

    def is_active(self) -> bool:
        if discover_active_bridges():
            return True
        return self._proc is not None and self._proc.poll() is None

    def get_status(self) -> tuple[str, str]:
        bridges = discover_active_bridges()
        if bridges:
            port = bridges[0]["port"]
            return "running", f"WebSocket: ws://localhost:{port}"
        if self._proc is not None and self._proc.poll() is None:
            return "starting", "正在启动 MCP Server…"
        if self._start_error:
            return "stopped", self._start_error
        return "stopped", "点击「启动」运行 MCP Server"

    def start(self) -> tuple[bool, str]:
        if self.is_active():
            _, detail = self.get_status()
            return True, detail

        self._start_error = None

        if not MCP_ROOT.is_dir():
            self._start_error = f"找不到 mcp-server 目录：{MCP_ROOT}"
            return False, self._start_error

        cli_entry = MCP_ROOT / "src" / "cli.ts"
        if not cli_entry.is_file():
            self._start_error = f"找不到 MCP 入口：{cli_entry}"
            return False, self._start_error

        npx = shutil.which("npx")
        if not npx:
            self._start_error = "找不到 npx，请确认 Node.js 已安装并在 PATH 中"
            _log(self._start_error)
            return False, self._start_error

        try:
            self._log_handle = LOG_FILE.open("a", encoding="utf-8")
            _log(f"Starting MCP server: {npx} tsx src/cli start")
            self._proc = subprocess.Popen(
                [npx, "tsx", "src/cli", "start"],
                cwd=str(MCP_ROOT),
                stdout=self._log_handle,
                stderr=subprocess.STDOUT,
                **_subprocess_hide_window_kwargs(),
            )
            self.started_by_launcher = True
        except OSError as exc:
            self._start_error = f"启动失败：{exc}"
            _log(f"MCP start failed: {exc}")
            return False, self._start_error

        return True, "正在启动 MCP Server…"

    def stop(self) -> tuple[bool, str]:
        stopped_any = False
        for bridge in discover_active_bridges():
            _kill_process_tree(bridge["pid"])
            stopped_any = True

        if self._proc is not None and self._proc.poll() is None:
            _kill_process_tree(self._proc.pid)
            stopped_any = True

        self._proc = None
        self.started_by_launcher = False
        self._start_error = None
        self._close_log_handle()

        if stopped_any:
            return True, "MCP Server 已停止"
        return True, "MCP Server 未在运行"

    def _close_log_handle(self) -> None:
        if self._log_handle is not None:
            try:
                self._log_handle.close()
            except OSError:
                pass
            self._log_handle = None

    def shutdown_if_started_here(self) -> None:
        if self.started_by_launcher and self.is_active():
            self.stop()


def _browser_login_worker(*, wait_timeout_s: float) -> None:
    global _BROWSER_LOGIN_JOB  # noqa: PLW0603
    _log("Browser login worker started")
    try:
        kwargs: dict[str, Any] = {"wait_timeout_s": wait_timeout_s}
        if _CUSTOM_LOGIN_ENV:
            kwargs["login_env"] = _CUSTOM_LOGIN_ENV
        result = refresh_status_via_browser(
            LOGIN_STATUS_FILE,
            **kwargs,
        )
        with _BROWSER_LOGIN_LOCK:
            _BROWSER_LOGIN_JOB = {
                "status": "success",
                "message": result.get("message"),
                "error": None,
                "result": result,
            }
        _log("Browser login succeeded")
    except Exception as exc:
        with _BROWSER_LOGIN_LOCK:
            _BROWSER_LOGIN_JOB = {
                "status": "error",
                "message": None,
                "error": str(exc),
                "result": None,
            }
        _log(f"Browser login failed: {exc}")


def start_browser_login(*, wait_timeout_s: float = 600.0) -> tuple[bool, str]:
    with _BROWSER_LOGIN_LOCK:
        if _BROWSER_LOGIN_JOB.get("status") == "running":
            return False, "已有登录任务进行中，请先在弹出浏览器中完成登录"
        _BROWSER_LOGIN_JOB.clear()
        _BROWSER_LOGIN_JOB.update(
            {
                "status": "running",
                "message": (
                    "已打开 Chromium，请手动登录。"
                    " 看到标签页标题「[已登录]」后关闭浏览器窗口即可保存登录态。"
                ),
                "error": None,
                "result": None,
            }
        )

    thread = threading.Thread(
        target=_browser_login_worker,
        kwargs={"wait_timeout_s": wait_timeout_s},
        daemon=True,
    )
    thread.start()
    return True, str(_BROWSER_LOGIN_JOB["message"])


def get_browser_login_job() -> dict[str, Any]:
    with _BROWSER_LOGIN_LOCK:
        return dict(_BROWSER_LOGIN_JOB)


def logout() -> None:
    global _PROFILE_BACKFILL_STATE  # noqa: PLW0603
    if LOGIN_STATUS_FILE.is_file():
        LOGIN_STATUS_FILE.unlink()
        _log("Removed login status file")
    with _BROWSER_LOGIN_LOCK:
        _BROWSER_LOGIN_JOB.clear()
        _BROWSER_LOGIN_JOB.update(
            {"status": "idle", "message": None, "error": None, "result": None}
        )
    with _PROFILE_BACKFILL_LOCK:
        _PROFILE_BACKFILL_STATE = {"status": "idle", "error": None}


def _format_timestamp(ts: float | None) -> str:
    if ts is None:
        return "—"
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError, OSError):
        return "—"


class LauncherApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.mcp = McpProcessManager()
        self._poll_job: str | None = None

        root.title("Wardrobe Agent 启动器")
        root.geometry("480x360")
        root.minsize(420, 320)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        main = ttk.Frame(root, padding=16)
        main.pack(fill=tk.BOTH, expand=True)

        mcp_frame = ttk.LabelFrame(main, text="MCP Server", padding=12)
        mcp_frame.pack(fill=tk.X, pady=(0, 12))

        self.mcp_status_var = tk.StringVar(value="检查中…")
        self.mcp_detail_var = tk.StringVar(value="")
        ttk.Label(mcp_frame, textvariable=self.mcp_status_var).pack(anchor=tk.W)
        ttk.Label(mcp_frame, textvariable=self.mcp_detail_var, foreground="#555").pack(
            anchor=tk.W, pady=(4, 0)
        )

        mcp_btn_row = ttk.Frame(mcp_frame)
        mcp_btn_row.pack(anchor=tk.W, pady=(8, 0))
        self.mcp_start_btn = ttk.Button(mcp_btn_row, text="启动", command=self._on_mcp_start)
        self.mcp_start_btn.pack(side=tk.LEFT)
        self.mcp_stop_btn = ttk.Button(mcp_btn_row, text="停止", command=self._on_mcp_stop)
        self.mcp_stop_btn.pack(side=tk.LEFT, padx=(8, 0))

        login_frame = ttk.LabelFrame(main, text="登录态", padding=12)
        login_frame.pack(fill=tk.X, pady=(0, 12))

        self.login_status_var = tk.StringVar(value="检查中…")
        self.login_user_var = tk.StringVar(value="")
        self.login_updated_var = tk.StringVar(value="")
        ttk.Label(login_frame, textvariable=self.login_status_var).pack(anchor=tk.W)
        ttk.Label(login_frame, textvariable=self.login_user_var, foreground="#555").pack(
            anchor=tk.W, pady=(4, 0)
        )
        ttk.Label(login_frame, textvariable=self.login_updated_var, foreground="#555").pack(
            anchor=tk.W, pady=(2, 0)
        )

        btn_row = ttk.Frame(main)
        btn_row.pack(fill=tk.X, pady=(0, 8))

        self.login_btn = ttk.Button(btn_row, text="登录", command=self._on_login)
        self.login_btn.pack(side=tk.LEFT)

        self.logout_btn = ttk.Button(btn_row, text="注销", command=self._on_logout)
        self.logout_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.hint_var = tk.StringVar(value="")
        ttk.Label(main, textvariable=self.hint_var, foreground="#666", wraplength=420).pack(
            anchor=tk.W, fill=tk.X
        )

        self._auto_start_mcp()
        self._refresh()
        self._schedule_poll()

    def _schedule_poll(self) -> None:
        self._poll_job = self.root.after(POLL_INTERVAL_MS, self._poll_tick)

    def _poll_tick(self) -> None:
        try:
            self._refresh()
        except Exception:
            _log("Refresh failed:\n" + traceback.format_exc())
        self._schedule_poll()

    def _set_btn_enabled(self, btn: ttk.Button, enabled: bool) -> None:
        btn.configure(state="normal" if enabled else "disabled")

    def _auto_start_mcp(self) -> None:
        if self.mcp.is_active():
            return
        ok, message = self.mcp.start()
        if not ok:
            _log(f"Auto-start MCP failed: {message}")

    def _refresh_mcp_ui(self) -> None:
        state, detail = self.mcp.get_status()
        if state == "running":
            self.mcp_status_var.set("● 运行中")
        elif state == "starting":
            self.mcp_status_var.set("○ 启动中")
        else:
            self.mcp_status_var.set("○ 未启动")
        self.mcp_detail_var.set(detail)
        mcp_active = state in ("running", "starting")
        self._set_btn_enabled(self.mcp_start_btn, not mcp_active)
        self._set_btn_enabled(self.mcp_stop_btn, mcp_active)

    def _refresh(self) -> None:
        self._refresh_mcp_ui()

        job = get_browser_login_job()
        if job.get("status") == "running":
            self.login_status_var.set("登录中…")
            self.login_user_var.set("")
            self.login_updated_var.set("")
            self.hint_var.set(str(job.get("message") or ""))
            self._set_btn_enabled(self.login_btn, False)
            self._set_btn_enabled(self.logout_btn, False)
            return

        if job.get("status") == "error":
            self.hint_var.set(f"登录失败：{job.get('error')}")

        profile = get_login_profile()
        if profile["ok"]:
            maybe_backfill_user_profile()
            profile = get_login_profile()
            self.login_status_var.set("● 已登录")
            user_bits: list[str] = []
            if profile.get("userLabel"):
                user_bits.append(str(profile["userLabel"]))
            elif _PROFILE_BACKFILL_STATE.get("status") == "running":
                user_bits.append("（正在获取用户名…）")
            if profile.get("userId"):
                user_bits.append(f"ID: {profile['userId']}")
            self.login_user_var.set("用户：" + (" / ".join(user_bits) if user_bits else "（已登录）"))
            self.login_updated_var.set(
                "更新时间：" + _format_timestamp(profile.get("updatedAt"))
            )
            self.hint_var.set(profile.get("message") or "")
            self._set_btn_enabled(self.login_btn, False)
            self._set_btn_enabled(self.logout_btn, True)
        else:
            if profile.get("expired"):
                self.login_status_var.set("✕ 登录已过期")
            else:
                self.login_status_var.set("○ 未登录")
            self.login_user_var.set("")
            self.login_updated_var.set("")
            if job.get("status") != "error":
                self.hint_var.set(profile.get("message") or "")
            self._set_btn_enabled(self.login_btn, True)
            self._set_btn_enabled(self.logout_btn, False)

    def _on_mcp_start(self) -> None:
        ok, message = self.mcp.start()
        self.mcp_detail_var.set(message)
        if not ok:
            messagebox.showerror("MCP Server", message)
        self._refresh_mcp_ui()

    def _on_mcp_stop(self) -> None:
        if not messagebox.askyesno("停止 MCP Server", "确定停止 MCP Server？"):
            return
        _, message = self.mcp.stop()
        self.mcp_detail_var.set(message)
        self._refresh_mcp_ui()

    def _on_login(self) -> None:
        ok, message = start_browser_login()
        if ok:
            self.hint_var.set(message)
            self._refresh()
        else:
            messagebox.showwarning("登录", message)

    def _on_logout(self) -> None:
        if not messagebox.askyesno("注销", "确定删除登录状态（status.json）并注销？"):
            return
        logout()
        self.hint_var.set("已注销")
        self._refresh()

    def _on_close(self) -> None:
        if self._poll_job is not None:
            try:
                self.root.after_cancel(self._poll_job)
            except tk.TclError:
                pass
        self.mcp.shutdown_if_started_here()
        self.root.destroy()


def main(*, login_env: str | None = None) -> None:
    global _CUSTOM_LOGIN_ENV
    _CUSTOM_LOGIN_ENV = login_env
    _log("Launcher started")
    if not MCP_ROOT.is_dir():
        messagebox.showerror(
            "启动失败",
            f"找不到 mcp-server 目录：\n{MCP_ROOT}\n\n"
            "请确认 wardrobe-agent 与 mcp-server 位于同一父目录（wain 包布局）。",
        )
        return

    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    LauncherApp(root)
    root.update_idletasks()
    root.mainloop()


if __name__ == "__main__":
    main()
