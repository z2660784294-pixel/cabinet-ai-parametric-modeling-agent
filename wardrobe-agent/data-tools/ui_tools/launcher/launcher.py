"""Wardrobe Agent 启动器入口（推荐：python launcher.py）。"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

LAUNCHER_DIR = Path(__file__).resolve().parent
LOG_FILE = LAUNCHER_DIR / "launcher.log"


def _hide_console_on_windows() -> None:
    if sys.platform != "win32":
        return
    import ctypes

    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        ctypes.windll.user32.ShowWindow(hwnd, 0)


def _install_excepthook() -> None:
    def _hook(exc_type: type[BaseException], exc: BaseException, tb: object) -> None:
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with LOG_FILE.open("a", encoding="utf-8") as f:
                f.write(text + "\n")
        except OSError:
            pass
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("启动器错误", text[-2000:])
            root.destroy()
        except Exception:
            pass

    sys.excepthook = _hook


def main() -> None:
    _hide_console_on_windows()
    _install_excepthook()

    parser = argparse.ArgumentParser(description="Wardrobe Agent 启动器")
    parser.add_argument(
        "--login-env",
        choices=["prod", "beta"],
        default="beta",
        help="登录环境：prod（www.kujiale.com）或 beta（默认，beta.kujiale.com）",
    )
    args = parser.parse_args()

    from app import main as run_app

    run_app(login_env=args.login_env)


if __name__ == "__main__":
    main()
