from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


class ClaudeSkillRunner:
    def __init__(self, repo_root: Path, timeout_seconds: int = 600) -> None:
        self.repo_root = repo_root
        self.timeout_seconds = timeout_seconds

    def run_parametric_model_design(self, result_dir: Path) -> bool:
        prompt = """
Use workspace/skills/parametric-model-design/SKILL.md exactly for this task.
Input: workspace/tmp/input/abd.json.
Output: workspace/tmp/output/design.json.
You must call workspace/skills/parametric-model-design/scripts/generate_pm_script.py to generate workspace/tmp/output/cabinet_script.js.
If workspace/tmp/output/bbox_diff.json exists, use it only to correct bbox/size mismatches in the next design attempt.
Do not do extra exploration.
""".strip()
        claude_command = shutil.which("claude") or shutil.which("claude.cmd") or shutil.which("claude.CMD")
        if claude_command is None:
            with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
                log_file.write("error: claude CLI not found\n")
            return False
        command = [
            claude_command,
            "-p",
            prompt,
            "--permission-mode",
            "acceptEdits",
            "--allowedTools",
            "Read,Write,Edit,Bash(python *)",
            "--add-dir",
            str((self.repo_root / "workspace").resolve()),
        ]
        with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
            log_file.write("info: invoking claude-code design backend\n")
            try:
                completed = subprocess.run(
                    command,
                    cwd=self.repo_root,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    timeout=self.timeout_seconds,
                    check=False,
                )
            except FileNotFoundError:
                log_file.write(f"error: claude CLI not found or not executable: {claude_command}\n")
                return False
            except subprocess.TimeoutExpired:
                log_file.write(f"error: claude-code design backend timed out after {self.timeout_seconds}s\n")
                return False
            if completed.stdout:
                log_file.write(completed.stdout.rstrip() + "\n")
            if completed.returncode != 0:
                log_file.write(f"error: claude-code design backend failed with exit code {completed.returncode}\n")
                return False
        return True
