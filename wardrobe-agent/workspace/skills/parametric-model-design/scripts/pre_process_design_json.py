"""design.json 生成脚本前的可选预处理钩子。

默认实现为空操作；可在其它分支重写 preProcessDesignJson 以修改 design.json。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def preProcessDesignJson(
    design: dict[str, Any],
    abd: dict[str, Any],
    design_path: Path | None = None,
) -> dict[str, Any]:
    """在 generate_pm_script 使用 design.json 之前调用，返回处理后的 design。"""
    return design
