#!/usr/bin/env python3
"""
Run environment self-check using test_patch and gold patch.
Usage: python scripts/check-env.py <experiment_dir> --image IMAGE
"""

import argparse
import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path


RUN_EXPERIMENT_PATH = Path(__file__).with_name("run-experiment.py")
_spec = importlib.util.spec_from_file_location("run_experiment_script", RUN_EXPERIMENT_PATH)
if _spec is None or _spec.loader is None:
    raise ImportError(f"Unable to load run-experiment.py from {RUN_EXPERIMENT_PATH}")
_run_experiment = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_run_experiment)

load_task_metadata = _run_experiment.load_task_metadata
apply_git_patch = _run_experiment.apply_git_patch
run_tests_in_docker = _run_experiment.run_tests_in_docker
check_test_file_created = _run_experiment.check_test_file_created


def parse_args():
    parser = argparse.ArgumentParser(description="Check Docker validation environment")
    parser.add_argument("experiment_dir", help="Path to experiment directory")
    parser.add_argument("--image", required=True, help="Docker image to use for validation")
    return parser.parse_args()


def prepare_clean_copy(exp_path: Path, work_root: Path, name: str) -> Path:
    source_repo = exp_path / "repo"
    work_dir = work_root / name
    if work_dir.exists():
        shutil.rmtree(work_dir)
    shutil.copytree(source_repo, work_dir, dirs_exist_ok=True)

    task_file = exp_path / "task_full.json"
    task = json.loads(task_file.read_text())
    base_commit = task.get("base_commit", "")
    if base_commit:
        subprocess.run(["git", "reset", "--hard", base_commit], cwd=work_dir, capture_output=True, check=True)
        subprocess.run(["git", "clean", "-fd"], cwd=work_dir, capture_output=True, check=False)
    return work_dir


def evaluate_expectations(results: dict, expect_fail_to_pass_passed: bool) -> dict:
    ftp = results.get("fail_to_pass_results", {})
    ptp = results.get("pass_to_pass_results", {})
    ftp_ok = all(v == ("PASSED" if expect_fail_to_pass_passed else "FAILED") for v in ftp.values()) if ftp else False
    ptp_ok = all(v == "PASSED" for v in ptp.values()) if ptp else False
    return {
        "fail_to_pass_expectation_met": ftp_ok,
        "pass_to_pass_expectation_met": ptp_ok,
        "overall": ftp_ok and ptp_ok,
    }


def main():
    args = parse_args()
    exp_path = Path(args.experiment_dir).resolve()
    if not exp_path.exists():
        print(f"Error: experiment directory not found: {exp_path}")
        sys.exit(1)

    task_metadata = load_task_metadata(exp_path)
    output = {
        "experiment": exp_path.name,
        "image": args.image,
        "checks": {}
    }

    work_root = exp_path / "env-check-work"
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)

    try:
        work_a = prepare_clean_copy(exp_path, work_root, "check-a")
        test_patch_applied = apply_git_patch(work_a, task_metadata.get("test_patch", ""), "test_patch")
        test_file_check = check_test_file_created(work_a, task_metadata.get("test_patch", ""))
        test_results_a = run_tests_in_docker(
            work_a,
            task_metadata.get("fail_to_pass", []),
            task_metadata.get("pass_to_pass", []),
            image=args.image,
            task_metadata=task_metadata,
        )
        output["checks"]["test_patch_only"] = {
            "patches_applied": {"test_patch": test_patch_applied},
            "test_file_check": test_file_check,
            "test_results": test_results_a,
            "expectations": evaluate_expectations(test_results_a, expect_fail_to_pass_passed=False),
        }

        work_b = prepare_clean_copy(exp_path, work_root, "check-b")
        test_patch_applied_b = apply_git_patch(work_b, task_metadata.get("test_patch", ""), "test_patch")
        gold_patch_applied = apply_git_patch(work_b, task_metadata.get("gold_patch", ""), "gold_patch")
        test_file_check_b = check_test_file_created(work_b, task_metadata.get("test_patch", ""))
        test_results_b = run_tests_in_docker(
            work_b,
            task_metadata.get("fail_to_pass", []),
            task_metadata.get("pass_to_pass", []),
            image=args.image,
            task_metadata=task_metadata,
        )
        output["checks"]["test_patch_plus_gold_patch"] = {
            "patches_applied": {
                "test_patch": test_patch_applied_b,
                "gold_patch": gold_patch_applied,
            },
            "test_file_check": test_file_check_b,
            "test_results": test_results_b,
            "expectations": evaluate_expectations(test_results_b, expect_fail_to_pass_passed=True),
        }
    finally:
        if work_root.exists():
            shutil.rmtree(work_root)

    output["overall"] = all(check.get("expectations", {}).get("overall", False) for check in output["checks"].values())

    output["env_status"] = "pass" if output["overall"] else "fail"

    out_file = exp_path / "env-check.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"Saved environment check to {out_file}")
    print(f"Environment status: {output['env_status']}")
    print(json.dumps(output, indent=2))

    if not output["overall"]:
        _generate_fix_prompt(exp_path, output, task_metadata, args.image)
        sys.exit(1)


def _generate_fix_prompt(exp_path: Path, output: dict, task_metadata: dict, image: str) -> None:
    """Generate a diagnostic log and fix prompt for Claude Code."""
    task_file = exp_path / "task_full.json"
    task = json.loads(task_file.read_text())
    instance_id = task.get("instance_id", exp_path.name)

    # Build diagnostic report
    lines = [
        f"# Environment Fix Needed: {instance_id}",
        "",
        f"## Task Info",
        f"- repo: {task.get('repo', '')}",
        f"- version: {task.get('version', '')}",
        f"- base_commit: {task.get('base_commit', '')[:12]}...",
        f"- Docker image: {image}",
        f"- env_status: {output['env_status']}",
        "",
    ]

    # Per-check details
    for check_name, check_data in output.get("checks", {}).items():
        exps = check_data.get("expectations", {})
        lines.append(f"## Check: {check_name}")
        lines.append(f"- expectations: {exps}")
        patches = check_data.get("patches_applied", {})
        lines.append(f"- patches_applied: {patches}")
        lines.append("")

        # Test results summary
        tr = check_data.get("test_results", {})
        lines.append(f"- framework: {tr.get('framework', '?')}")
        lines.append(f"- exit_code: {tr.get('exit_code', '?')}")
        lines.append(f"- total/passed/failed: {tr['total_tests']}/{tr['passed_tests']}/{tr['failed_tests']}")

        # Fail-to-pass details
        ftp = tr.get("fail_to_pass_results", {})
        if ftp:
            lines.append("- fail_to_pass:")
            for k, v in ftp.items():
                lines.append(f"    {v}: {k}")

        # Pass-to-pass details (condensed)
        ptp = tr.get("pass_to_pass_results", {})
        if ptp:
            passed = sum(1 for v in ptp.values() if v == "PASSED")
            failed = sum(1 for v in ptp.values() if v == "FAILED")
            notfound = sum(1 for v in ptp.values() if v == "NOT_FOUND")
            lines.append(f"- pass_to_pass: passed={passed} failed={failed} not_found={notfound} (total={len(ptp)})")

        # Docker test output (last 80 lines)
        test_output = tr.get("output", "")
        if test_output:
            output_lines = test_output.strip().split("\n")
            if len(output_lines) > 80:
                lines.append(f"- test output (last 80 of {len(output_lines)} lines):")
                output_lines = output_lines[-80:]
            else:
                lines.append("- test output:")
            for ol in output_lines:
                lines.append(f"    {ol}")

        lines.append("")

    # Actionable fix prompt
    dockerfile_path = exp_path / "env-build" / "Dockerfile"
    lines.extend([
        "## How to Fix",
        "",
        "1. Read the diagnostic output above to understand what's failing",
        f"2. Check the Dockerfile: {dockerfile_path}",
        f"3. Check the repo source: {exp_path / 'repo'}",
        "4. Common fixes:",
        "   - Missing dependencies: add pip install to Dockerfile",
        "   - Wrong Python version: update FROM line in Dockerfile",
        "   - Test framework issues: ensure pytest/django test runner is properly configured",
        "   - Import errors: install missing packages",
        "5. After fixing, rebuild the image:",
        f"   python scripts/build-env.py {exp_path} --rebuild",
        f"6. Re-run env check:",
        f"   python scripts/check-env.py {exp_path} --image {image}",
        "",
        "## Claude Code Fix Prompt",
        "",
        "Paste the following to Claude Code (run from repo directory):",
        "---",
    ])

    # Generate the actual prompt Claude Code should receive
    repo_dir = exp_path / "repo"
    fail_summary = []
    for check_name, check_data in output.get("checks", {}).items():
        tr = check_data.get("test_results", {})
        if tr.get("exit_code") != 0:
            fail_summary.append(f"  {check_name}: exit_code={tr.get('exit_code')}, {tr.get('passed_tests',0)} passed, {tr.get('failed_tests',0)} failed")

    fix_prompt = "\n".join([
        f"/plan Fix the Docker test environment for {instance_id}.",
        f"",
        f"Repo: {task.get('repo', '')} (version {task.get('version', '')})",
        f"Docker image: {image}",
        f"",
        f"The environment check failed:",
        *fail_summary,
        f"",
        f"Key issues to investigate:",
        f"1. Check the test output in {exp_path / 'env-check.json'} for errors",
        f"2. Check if the Dockerfile at {dockerfile_path} has correct dependencies",
        f"3. The test framework is: {output.get('checks', {}).get('test_patch_only', {}).get('test_results', {}).get('framework', 'unknown')}",
        f"",
        f"After fixing, rebuild and verify:",
        f"  python scripts/build-env.py {exp_path}",
        f"  python scripts/check-env.py {exp_path} --image {image}",
        "",
        f"Save this plan to {exp_path}/plans/env-fix-plan.md",
    ])
    lines.append(fix_prompt)
    lines.append("---")

    # Write diagnostic log
    diag_file = exp_path / "env-diagnostic.md"
    diag_file.write_text("\n".join(lines))

    # Write the fix prompt separately for easy copy-paste
    prompt_file = exp_path / "env-fix-prompt.md"
    prompt_file.write_text(fix_prompt)

    print(f"\n{'='*60}")
    print(f"ENV CHECK FAILED: {output['env_status']}")
    print(f"{'='*60}")
    print(f"Diagnostic log: {diag_file}")
    print(f"Fix prompt:     {prompt_file}")
    print(f"")
    print(f"To fix: open the fix prompt and paste to Claude Code,")
    print(f"or read the diagnostic log for manual troubleshooting.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
