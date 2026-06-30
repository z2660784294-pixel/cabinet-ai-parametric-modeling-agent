from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from regression.workspace_bridge.io import WORKSPACE_TMP_OUTPUT


@dataclass(frozen=True)
class DesignResult:
    status: str
    design_path: Path | None = None
    cabinet_script_path: Path | None = None
    message: str = ""


class DesignBackend(Protocol):
    def generate_design(self, case: Any, workspace_root: Path) -> DesignResult:
        ...


class ExistingDesignBackend:
    def generate_design(self, case: Any, workspace_root: Path) -> DesignResult:
        workspace_design_path = WORKSPACE_TMP_OUTPUT / "design.json"
        result_design_path = case.result_dir / "design.json"
        WORKSPACE_TMP_OUTPUT.mkdir(parents=True, exist_ok=True)
        case.result_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(case.design_path, workspace_design_path)
        with workspace_design_path.open("r", encoding="utf-8") as file:
            json.load(file)
        shutil.copy2(workspace_design_path, result_design_path)
        return DesignResult(status="passed", design_path=result_design_path)


class ClaudeCodeDesignBackend:
    def generate_design(self, case: Any, workspace_root: Path) -> DesignResult:
        from regression.workspace_bridge.claude_skill_runner import ClaudeSkillRunner

        runner = ClaudeSkillRunner(workspace_root)
        if not runner.run_parametric_model_design(case.result_dir):
            return DesignResult(status="error", message="error: claude-code design backend failed")

        workspace_design_path = WORKSPACE_TMP_OUTPUT / "design.json"
        workspace_script_path = WORKSPACE_TMP_OUTPUT / "cabinet_script.js"
        if not workspace_design_path.exists():
            return DesignResult(status="error", message=f"error: missing generated design.json: {workspace_design_path}")
        with workspace_design_path.open("r", encoding="utf-8") as file:
            json.load(file)
        if not workspace_script_path.exists():
            return DesignResult(status="error", message=f"error: missing generated cabinet_script.js: {workspace_script_path}")
        workspace_script_path.read_text(encoding="utf-8")

        result_design_path = case.result_dir / "design.json"
        result_script_path = case.result_dir / "cabinet_script.js"
        shutil.copy2(workspace_design_path, result_design_path)
        shutil.copy2(workspace_script_path, result_script_path)
        return DesignResult(status="passed", design_path=result_design_path, cabinet_script_path=result_script_path)


class NotImplementedDesignBackend:
    def __init__(self, name: str) -> None:
        self.name = name

    def generate_design(self, case: Any, workspace_root: Path) -> DesignResult:
        return DesignResult(status="error", message=f"design backend is not implemented: {self.name}")


def create_design_backend(name: str) -> DesignBackend:
    if name == "existing-design":
        return ExistingDesignBackend()
    if name == "claude-code":
        return ClaudeCodeDesignBackend()
    if name in {"codex", "cursor-cli"}:
        return NotImplementedDesignBackend(name)
    raise ValueError(f"unsupported design backend: {name}")
