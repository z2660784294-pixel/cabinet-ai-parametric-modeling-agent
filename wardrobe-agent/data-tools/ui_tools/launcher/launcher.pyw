"""双击入口：Windows 转交 python.exe；其他平台直接运行 launcher.py。"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

DETACHED_PROCESS = 0x00000008


def _python_exe() -> str:
    exe = sys.executable
    if exe.lower().endswith("pythonw.exe"):
        return exe[: -len("pythonw.exe")] + "python.exe"
    return exe


def main() -> None:
    script = Path(__file__).resolve().with_name("launcher.py")
    cmd = [_python_exe(), str(script)]
    kwargs: dict[str, object] = {"cwd": str(script.parent), "close_fds": True}
    if sys.platform == "win32":
        kwargs["creationflags"] = DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


if __name__ == "__main__":
    main()
