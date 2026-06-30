from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path


EXIT_PASSED = 0
EXIT_NEEDS_REVIEW = 1
EXIT_ERROR = 2
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
GENERATOR_SCRIPT = REPO_ROOT / "workspace" / "skills" / "parametric-model-design" / "scripts" / "generate_pm_script.py"
CURRENT_ABD_PATH = REPO_ROOT / "workspace" / "tmp" / "input" / "abd.json"
CURRENT_DESIGN_PATH = REPO_ROOT / "workspace" / "tmp" / "output" / "design.json"
CURRENT_EDIT_DATA_PATH = REPO_ROOT / "workspace" / "tmp" / "output" / "editor_data.json"


def append_log(result_dir: Path, message: str) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    with (result_dir / "output.log").open("a", encoding="utf-8") as log_file:
        log_file.write(message.rstrip() + "\n")


def reset_output_log(result_dir: Path) -> None:
    result_dir.mkdir(parents=True, exist_ok=True)
    (result_dir / "output.log").write_text("", encoding="utf-8")


def write_single_case_summary(cases_root: Path, case_id: str, regression: str, status: str, message: str = "") -> None:
    from regression.report.summary import CaseRunResult, collect_artifacts, write_run_summary

    result_dir = cases_root / case_id / "result"
    write_run_summary(
        cases_root,
        REPO_ROOT,
        f"{regression} --case {case_id}",
        [CaseRunResult(case_id, regression, status, message, collect_artifacts(result_dir, cases_root))],
    )


def generate_cabinet_script(case) -> Path:
    output_path = case.result_dir / "cabinet_script.js"
    command = [
        sys.executable,
        str(GENERATOR_SCRIPT),
        "--abd",
        str(case.abd_path),
        "--design",
        str(case.design_path),
        "-o",
        str(output_path),
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if completed.stdout:
        append_log(case.result_dir, completed.stdout.rstrip())
    if completed.returncode != 0:
        append_log(case.result_dir, f"error: generate_pm_script.py failed with exit code {completed.returncode}")
        raise RuntimeError("generate_pm_script.py failed")
    if not output_path.exists():
        append_log(case.result_dir, f"error: missing generated cabinet_script.js: {output_path}")
        raise RuntimeError(f"missing generated cabinet_script.js: {output_path}")
    return output_path

def execute_design2edit_case(case, parameditor_url: str, param_editor_data_url: str) -> tuple[str, str]:
    from regression.case_manager import compare_ignore_paths, validate_case_for_design2edit
    from regression.report.summary import clean_known_result_artifacts

    clean_known_result_artifacts(case.result_dir)
    reset_output_log(case.result_dir)
    validate_case_for_design2edit(case)
    append_log(case.result_dir, f"info: validated case {case.case_id}")
    from regression.workspace_bridge.io import sync_case_inputs
    from regression.workspace_bridge.mcp_client import ParamEditorClient, ParamEditorDataClient

    sync_case_inputs(case)
    append_log(case.result_dir, "info: synced case inputs to workspace/tmp (abd -> input, design -> output)")
    cabinet_script_path = generate_cabinet_script(case)
    parameditor = ParamEditorClient(parameditor_url)
    parameditor.clear_scene()
    append_log(case.result_dir, "info: parameditor.clear_scene completed")
    parameditor.execute_script(cabinet_script_path)
    append_log(case.result_dir, f"info: parameditor.execute_script completed: {cabinet_script_path.resolve()}")
    edit_data_path = case.result_dir / "editData.json"
    ParamEditorDataClient(param_editor_data_url).export_current_editor_data(edit_data_path)
    append_log(case.result_dir, f"info: param-editor-data.get_current_editor_data completed: {edit_data_path.resolve()}")
    from regression.compare.json_compare import compare_json_files
    from regression.report.summary import build_case_message

    compare_path = case.result_dir / "compare.json"
    ignore_paths = compare_ignore_paths(case)
    if ignore_paths is None:
        compare_result = compare_json_files(case.baseline_path, edit_data_path, compare_path)
    else:
        compare_result = compare_json_files(case.baseline_path, edit_data_path, compare_path, ignore_paths)
    status = compare_result["status"]
    append_log(case.result_dir, f"info: compare completed with status {status}")
    return status, build_case_message(case.result_dir, "design2edit", status)


def run_design2edit(args: argparse.Namespace) -> int:
    cases_root = Path(args.cases)
    if args.case:
        try:
            from regression.case_manager import load_case

            case = load_case(cases_root, args.case)
            status, message = execute_design2edit_case(case, args.parameditor_url, args.param_editor_data_url)
        except Exception as exc:
            if "case" in locals():
                append_log(case.result_dir, f"error: {exc}")
                write_single_case_summary(cases_root, case.case_id, "design2edit", "error", str(exc))
            print(f"error: {exc}")
            return EXIT_ERROR

        write_single_case_summary(cases_root, case.case_id, "design2edit", status, message)
        print(f"{status}: {case.case_id}")
        if status == "passed":
            return EXIT_PASSED
        return EXIT_NEEDS_REVIEW

    from regression.case_manager import list_cases
    from regression.report.summary import CaseRunResult, collect_artifacts, exit_code_for_results, write_run_summary

    results: list[CaseRunResult] = []
    for case in list_cases(cases_root):
        if not case.enabled:
            results.append(CaseRunResult(case.case_id, "design2edit", "skipped", "case disabled", collect_artifacts(case.result_dir, cases_root)))
            continue
        if "design2edit" not in case.regressions:
            results.append(CaseRunResult(case.case_id, "design2edit", "skipped", "design2edit disabled by manifest", collect_artifacts(case.result_dir, cases_root)))
            continue
        try:
            if not case.has_design2edit_inputs():
                raise RuntimeError("missing design2edit inputs")
            status, message = execute_design2edit_case(case, args.parameditor_url, args.param_editor_data_url)
        except Exception as exc:
            append_log(case.result_dir, f"error: {exc}")
            status, message = "error", str(exc)
        results.append(CaseRunResult(case.case_id, "design2edit", status, message, collect_artifacts(case.result_dir, cases_root)))
        print(f"{status}: {case.case_id}")
    summary_path = write_run_summary(cases_root, REPO_ROOT, "run-design2edit", results)
    print(f"summary: {summary_path}")
    return exit_code_for_results(results)


def execute_abd2edit_case(case, stage: str, design_backend: str, parameditor_url: str, param_editor_data_url: str) -> tuple[str, str]:
    from regression.case_manager import validate_case_for_abd2edit
    from regression.report.summary import build_case_message, clean_known_result_artifacts

    if stage in {"validate", "design", "full"}:
        clean_known_result_artifacts(case.result_dir)
    reset_output_log(case.result_dir)
    validate_case_for_abd2edit(case)
    append_log(case.result_dir, f"info: validated case {case.case_id}")
    from regression.runners.abd2edit import run_bbox_stage, run_design_stage, run_full, run_report_stage, run_screenshot_stage, run_validate_stage

    if stage == "validate":
        status = run_validate_stage(case, append_log)
    elif stage == "design":
        status = run_design_stage(case, REPO_ROOT, design_backend, append_log)
    elif stage == "bbox":
        status = run_bbox_stage(case, parameditor_url, append_log)
    elif stage == "report":
        status = run_report_stage(case, append_log)
    elif stage == "screenshot":
        status = run_screenshot_stage(case, parameditor_url, append_log)
    elif stage == "full":
        status = run_full(case, REPO_ROOT, design_backend, parameditor_url, param_editor_data_url, append_log)
    else:
        raise RuntimeError(f"unsupported run-abd2edit stage: {stage}")
    return status, build_case_message(case.result_dir, "abd2edit", status)


def run_abd2edit(args: argparse.Namespace) -> int:
    cases_root = Path(args.cases)
    if args.case:
        try:
            from regression.case_manager import load_case

            case = load_case(cases_root, args.case)
            status, message = execute_abd2edit_case(case, args.stage, args.design_backend, args.parameditor_url, args.param_editor_data_url)
        except Exception as exc:
            if "case" in locals():
                append_log(case.result_dir, f"error: {exc}")
                write_single_case_summary(cases_root, case.case_id, "abd2edit", "error", str(exc))
            print(f"error: {exc}")
            return EXIT_ERROR

        write_single_case_summary(cases_root, case.case_id, "abd2edit", status, message)
        print(f"{status}: {case.case_id}")
        if status == "passed":
            return EXIT_PASSED
        if status == "needs_review":
            return EXIT_NEEDS_REVIEW
        return EXIT_ERROR

    from regression.case_manager import list_cases
    from regression.report.summary import CaseRunResult, collect_artifacts, exit_code_for_results, write_run_summary

    results: list[CaseRunResult] = []
    for case in list_cases(cases_root):
        if not case.enabled:
            results.append(CaseRunResult(case.case_id, "abd2edit", "skipped", "case disabled", collect_artifacts(case.result_dir, cases_root)))
            continue
        if "abd2edit" not in case.regressions:
            results.append(CaseRunResult(case.case_id, "abd2edit", "skipped", "abd2edit disabled by manifest", collect_artifacts(case.result_dir, cases_root)))
            continue
        try:
            if not case.has_abd2edit_inputs():
                raise RuntimeError("missing abd2edit inputs")
            status, message = execute_abd2edit_case(case, args.stage, args.design_backend, args.parameditor_url, args.param_editor_data_url)
        except Exception as exc:
            append_log(case.result_dir, f"error: {exc}")
            status, message = "error", str(exc)
        results.append(CaseRunResult(case.case_id, "abd2edit", status, message, collect_artifacts(case.result_dir, cases_root)))
        print(f"{status}: {case.case_id}")
    summary_path = write_run_summary(cases_root, REPO_ROOT, f"run-abd2edit --stage {args.stage}", results)
    print(f"summary: {summary_path}")
    return exit_code_for_results(results)


def run_all(args: argparse.Namespace) -> int:
    from regression.case_manager import list_cases
    from regression.report.summary import CaseRunResult, collect_artifacts, exit_code_for_results, write_run_summary

    cases_root = Path(args.cases)
    results: list[CaseRunResult] = []
    for case in list_cases(cases_root):
        if not case.enabled:
            for regression in ("design2edit", "abd2edit"):
                results.append(CaseRunResult(case.case_id, regression, "skipped", "case disabled", collect_artifacts(case.result_dir, cases_root)))
            continue
        if "design2edit" in case.regressions:
            try:
                if not case.has_design2edit_inputs():
                    raise RuntimeError("missing design2edit inputs")
                status, message = execute_design2edit_case(case, args.parameditor_url, args.param_editor_data_url)
            except Exception as exc:
                append_log(case.result_dir, f"error: {exc}")
                status, message = "error", str(exc)
            results.append(CaseRunResult(case.case_id, "design2edit", status, message, collect_artifacts(case.result_dir, cases_root)))
            print(f"{status}: {case.case_id} design2edit")
        else:
            results.append(CaseRunResult(case.case_id, "design2edit", "skipped", "design2edit disabled by manifest", collect_artifacts(case.result_dir, cases_root)))
        if "abd2edit" in case.regressions:
            try:
                if not case.has_abd2edit_inputs():
                    raise RuntimeError("missing abd2edit inputs")
                status, message = execute_abd2edit_case(case, "full", args.design_backend, args.parameditor_url, args.param_editor_data_url)
            except Exception as exc:
                append_log(case.result_dir, f"error: {exc}")
                status, message = "error", str(exc)
            results.append(CaseRunResult(case.case_id, "abd2edit", status, message, collect_artifacts(case.result_dir, cases_root)))
            print(f"{status}: {case.case_id} abd2edit")
        else:
            results.append(CaseRunResult(case.case_id, "abd2edit", "skipped", "abd2edit disabled by manifest", collect_artifacts(case.result_dir, cases_root)))
    summary_path = write_run_summary(cases_root, REPO_ROOT, "run-all", results)
    print(f"summary: {summary_path}")
    return exit_code_for_results(results)


def list_cases_command(args: argparse.Namespace) -> int:
    from regression.case_manager import list_cases

    cases = list_cases(Path(args.cases))
    for case in cases:
        print(
            f"{case.case_id}\t"
            f"enabled={case.enabled}\t"
            f"regressions={','.join(case.regressions)}\t"
            f"design2edit={case.has_design2edit_inputs()}\t"
            f"abd2edit={case.has_abd2edit_inputs()}"
        )
    return EXIT_PASSED


def add_case_command(args: argparse.Namespace) -> int:
    from regression.case_manager import add_case

    try:
        case = add_case(
            Path(args.cases),
            args.case_id,
            Path(args.abd),
            Path(args.preview) if args.preview else None,
            Path(args.design) if args.design else None,
            Path(args.baseline) if args.baseline else None,
            args.overwrite,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return EXIT_ERROR
    print(f"added: {case.case_id}")
    return EXIT_PASSED


def rebaseline_command(args: argparse.Namespace) -> int:
    from regression.case_manager import rebaseline_case

    try:
        baseline_path = rebaseline_case(Path(args.cases), args.case, args.force)
    except Exception as exc:
        print(f"error: {exc}")
        return EXIT_ERROR
    print(f"rebaselined: {baseline_path}")
    return EXIT_PASSED


def generate_current_case_id() -> str:
    return f"case_{datetime.now().strftime('%y%m%d%H%M')}"


def add_current_case_command(args: argparse.Namespace) -> int:
    from regression.case_manager import add_case

    case_id = args.case_id or generate_current_case_id()
    try:
        case = add_case(
            Path(args.cases),
            case_id,
            CURRENT_ABD_PATH,
            design_path=CURRENT_DESIGN_PATH,
            baseline_path=CURRENT_EDIT_DATA_PATH,
            overwrite=args.overwrite,
        )
    except Exception as exc:
        print(f"error: {exc}")
        return EXIT_ERROR
    print(f"added: {case.case_id}")
    return EXIT_PASSED


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run wardrobe regression checks")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_cases_parser = subparsers.add_parser("list-cases", help="List regression cases")
    list_cases_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    list_cases_parser.set_defaults(func=list_cases_command)

    add_case_parser = subparsers.add_parser("add-case", help="Add a regression case from local files")
    add_case_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    add_case_parser.add_argument("--case-id", required=True, help="Regression case id")
    add_case_parser.add_argument("--abd", required=True, help="Source abd.json")
    add_case_parser.add_argument("--preview", help="Source preview image")
    add_case_parser.add_argument("--design", help="Source design.json")
    add_case_parser.add_argument("--baseline", help="Source editData baseline JSON")
    add_case_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing case")
    add_case_parser.set_defaults(func=add_case_command)

    add_current_case_parser = subparsers.add_parser("add-current-case", help="Add a regression case from workspace/tmp current outputs")
    add_current_case_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    add_current_case_parser.add_argument("--case-id", help="Regression case id; defaults to case_YYMMDDHHMM")
    add_current_case_parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing case")
    add_current_case_parser.set_defaults(func=add_current_case_command)

    rebaseline_parser = subparsers.add_parser("rebaseline", help="Replace source baseline with result editData")
    rebaseline_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    rebaseline_parser.add_argument("--case", required=True, help="Regression case id")
    rebaseline_parser.add_argument("--force", action="store_true", help="Rebaseline without latest needs_review status")
    rebaseline_parser.set_defaults(func=rebaseline_command)

    run_all_parser = subparsers.add_parser("run-all", help="Run design2edit and abd2edit for all enabled cases")
    run_all_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    run_all_parser.add_argument(
        "--design-backend",
        choices=("existing-design", "claude-code", "codex", "cursor-cli"),
        default="existing-design",
        help="Design backend for run-abd2edit design generation",
    )
    run_all_parser.add_argument(
        "--parameditor-url",
        default="http://localhost:7764/sse",
        help="parameditor MCP endpoint",
    )
    run_all_parser.add_argument(
        "--param-editor-data-url",
        default="http://localhost:7765/sse",
        help="param-editor-data MCP endpoint",
    )
    run_all_parser.set_defaults(func=run_all)

    run_design2edit_parser = subparsers.add_parser("run-design2edit", help="Run design2edit for one case or all enabled cases")
    run_design2edit_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    run_design2edit_parser.add_argument("--case", help="Regression case id; omit to run all enabled design2edit cases")
    run_design2edit_parser.add_argument(
        "--parameditor-url",
        default="http://localhost:7764/sse",
        help="parameditor MCP endpoint",
    )
    run_design2edit_parser.add_argument(
        "--param-editor-data-url",
        default="http://localhost:7765/sse",
        help="param-editor-data MCP endpoint",
    )
    run_design2edit_parser.set_defaults(func=run_design2edit)

    run_abd2edit_parser = subparsers.add_parser("run-abd2edit", help="Run abd2edit for one case or all enabled cases")
    run_abd2edit_parser.add_argument("--cases", required=True, help="Regression cases root directory")
    run_abd2edit_parser.add_argument("--case", help="Regression case id; omit to run all enabled abd2edit cases")
    run_abd2edit_parser.add_argument(
        "--stage",
        choices=("validate", "design", "bbox", "report", "screenshot", "full"),
        default="full",
        help="run-abd2edit stage to execute",
    )
    run_abd2edit_parser.add_argument(
        "--design-backend",
        choices=("existing-design", "claude-code", "codex", "cursor-cli"),
        default="existing-design",
        help="Design backend for run-abd2edit design generation",
    )
    run_abd2edit_parser.add_argument(
        "--parameditor-url",
        default="http://localhost:7764/sse",
        help="parameditor MCP endpoint",
    )
    run_abd2edit_parser.add_argument(
        "--param-editor-data-url",
        default="http://localhost:7765/sse",
        help="param-editor-data MCP endpoint",
    )
    run_abd2edit_parser.set_defaults(func=run_abd2edit)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
