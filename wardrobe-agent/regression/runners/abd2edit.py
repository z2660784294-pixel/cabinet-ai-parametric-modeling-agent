from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

from regression.workspace_bridge.design_backend import create_design_backend
from regression.workspace_bridge.io import WORKSPACE_TMP_INPUT, WORKSPACE_TMP_OUTPUT, sync_case_inputs


AppendLog = Callable[[Path, str], None]


def run_validate_stage(case: Any, append_log: AppendLog) -> str:
    sync_case_inputs(case)
    append_log(case.result_dir, "info: synced case inputs to workspace/tmp (abd -> input, design -> output)")
    append_log(case.result_dir, "info: ABD content validation skipped for abd2edit regression; basic file and JSON validation already completed")
    return "passed"


def run_design_stage(case: Any, workspace_root: Path, design_backend: str, append_log: AppendLog) -> str:
    sync_case_inputs(case)
    append_log(case.result_dir, "info: synced case inputs to workspace/tmp (abd -> input, design -> output)")
    backend = create_design_backend(design_backend)
    result = backend.generate_design(case, workspace_root)
    if result.message:
        append_log(case.result_dir, result.message)
    if result.status == "passed":
        append_log(case.result_dir, f"info: design backend {design_backend} completed")
    return result.status


def run_bbox_stage(case: Any, parameditor_url: str, append_log: AppendLog) -> str:
    sync_case_inputs(case)
    append_log(case.result_dir, "info: synced case inputs to workspace/tmp (abd -> input, design -> output)")
    from regression.compare.abd_scene_compare import run_bbox_compare

    result = run_bbox_compare(WORKSPACE_TMP_INPUT / "abd.json", case.result_dir / "bbox_diff.json", case.result_dir, parameditor_url)
    append_log(case.result_dir, f"info: bbox compare completed with status {result['status']}")
    return result["status"]


def run_report_stage(case: Any, append_log: AppendLog) -> str:
    from regression.report.markdown_report import generate_case_report

    report_path = generate_case_report(case)
    append_log(case.result_dir, f"info: report generated: {report_path}")
    return "passed"


def run_screenshot_stage(case: Any, parameditor_url: str, append_log: AppendLog) -> str:
    from regression.workspace_bridge.mcp_client import ParamEditorClient

    output_path = case.result_dir / "resultImage.png"
    try:
        ParamEditorClient(parameditor_url).capture_result_image(output_path)
    except Exception as exc:
        append_log(case.result_dir, f"warning: get_preview_image failed: {exc}")
        return "passed"
    append_log(case.result_dir, f"info: result image captured: {output_path}")
    return "passed"


def copy_attempt_artifacts(case: Any, attempt: int) -> None:
    attempt_dir = case.result_dir / f"attempt-{attempt}"
    attempt_dir.mkdir(parents=True, exist_ok=True)
    for name in ("design.json", "cabinet_script.js", "editData.json", "instance_compare.json", "bbox_diff.json", "resultImage.png"):
        source = case.result_dir / name
        if source.exists() and source.is_file():
            shutil.copy2(source, attempt_dir / name)


def run_full_attempt(case: Any, workspace_root: Path, design_backend: str, parameditor_url: str, param_editor_data_url: str, append_log: AppendLog) -> tuple[str, str, str]:
    backend = create_design_backend(design_backend)
    design_result = backend.generate_design(case, workspace_root)
    if design_result.message:
        append_log(case.result_dir, design_result.message)
    if design_result.status != "passed":
        return "error", "error", "error"
    append_log(case.result_dir, f"info: design backend {design_backend} completed")

    cabinet_script_path = design_result.cabinet_script_path or case.result_dir / "cabinet_script.js"
    if not cabinet_script_path.exists():
        from regression.run_regression import generate_cabinet_script

        cabinet_script_path = generate_cabinet_script(case)
        workspace_script_path = WORKSPACE_TMP_OUTPUT / "cabinet_script.js"
        workspace_script_path.write_text(cabinet_script_path.read_text(encoding="utf-8"), encoding="utf-8")

    from regression.compare.abd_scene_compare import compare_instance_files, run_bbox_compare
    from regression.workspace_bridge.mcp_client import ParamEditorClient, ParamEditorDataClient

    parameditor = ParamEditorClient(parameditor_url)
    parameditor.clear_scene()
    append_log(case.result_dir, "info: parameditor.clear_scene completed")
    parameditor.execute_script(cabinet_script_path)
    append_log(case.result_dir, f"info: parameditor.execute_script completed: {cabinet_script_path.resolve()}")

    edit_data_path = case.result_dir / "editData.json"
    ParamEditorDataClient(param_editor_data_url).export_current_editor_data(edit_data_path)
    append_log(case.result_dir, f"info: param-editor-data.get_current_editor_data completed: {edit_data_path.resolve()}")

    instance_result = compare_instance_files(case.abd_path, edit_data_path, case.result_dir / "instance_compare.json")
    append_log(case.result_dir, f"info: instance compare completed with status {instance_result['status']}")
    if instance_result["status"] == "error":
        return "error", "error", "error"

    bbox_result = run_bbox_compare(WORKSPACE_TMP_INPUT / "abd.json", case.result_dir / "bbox_diff.json", case.result_dir, parameditor_url)
    append_log(case.result_dir, f"info: bbox compare completed with status {bbox_result['status']}")
    if bbox_result["status"] == "error":
        return "error", instance_result["status"], "error"

    try:
        parameditor.capture_result_image(case.result_dir / "resultImage.png")
        append_log(case.result_dir, f"info: result image captured: {case.result_dir / 'resultImage.png'}")
    except Exception as exc:
        append_log(case.result_dir, f"warning: get_preview_image failed: {exc}")

    status = "needs_review" if "needs_review" in {instance_result["status"], bbox_result["status"]} else "passed"
    return status, instance_result["status"], bbox_result["status"]


def run_full(case: Any, workspace_root: Path, design_backend: str, parameditor_url: str, param_editor_data_url: str, append_log: AppendLog) -> str:
    sync_case_inputs(case)
    append_log(case.result_dir, "info: synced case inputs to workspace/tmp (abd -> input, design -> output)")
    append_log(case.result_dir, "info: ABD content validation skipped for abd2edit regression; basic file and JSON validation already completed")

    from regression.report.markdown_report import generate_case_report

    status = "error"
    for attempt in range(3):
        append_log(case.result_dir, f"info: run-abd2edit full attempt {attempt + 1}")
        status, instance_status, bbox_status = run_full_attempt(case, workspace_root, design_backend, parameditor_url, param_editor_data_url, append_log)
        copy_attempt_artifacts(case, attempt + 1)
        if status == "error":
            break
        if bbox_status != "needs_review" or attempt == 2:
            break
        bbox_diff_path = case.result_dir / "bbox_diff.json"
        if bbox_diff_path.exists():
            shutil.copy2(bbox_diff_path, WORKSPACE_TMP_OUTPUT / "bbox_diff.json")
        append_log(case.result_dir, "info: bbox needs_review; retrying design backend with bbox_diff.json")

    report_path = generate_case_report(case, status)
    append_log(case.result_dir, f"info: report generated: {report_path}")
    return status
