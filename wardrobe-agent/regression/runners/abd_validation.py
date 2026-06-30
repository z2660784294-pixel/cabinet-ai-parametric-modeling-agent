from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATE_ABD_SCRIPT = REPO_ROOT / "workspace" / "skills" / "shared" / "scripts" / "validate_abd_layout.py"


def validate_abd_layout(abd_path: Path, result_dir: Path) -> bool:
    command = [sys.executable, str(VALIDATE_ABD_SCRIPT), str(abd_path)]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.stdout:
        with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
            log_file.write(completed.stdout.rstrip() + "\n")
    if completed.returncode != 0:
        with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
            log_file.write(f"error: validate_abd_layout.py failed with exit code {completed.returncode}\n")
        return False
    return True
