from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_TMP_INPUT = REPO_ROOT / "workspace" / "tmp" / "input"
WORKSPACE_TMP_OUTPUT = REPO_ROOT / "workspace" / "tmp" / "output"


def sync_case_inputs(case: Any) -> None:
    WORKSPACE_TMP_INPUT.mkdir(parents=True, exist_ok=True)
    WORKSPACE_TMP_OUTPUT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(case.abd_path, WORKSPACE_TMP_INPUT / "abd.json")
    shutil.copy2(case.design_path, WORKSPACE_TMP_OUTPUT / "design.json")
    case.result_dir.mkdir(parents=True, exist_ok=True)


def result_cabinet_script_path(case: Any) -> Path:
    return case.result_dir / "cabinet_script.js"
