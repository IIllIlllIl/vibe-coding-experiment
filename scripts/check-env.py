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

    out_file = exp_path / "env-check.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"Saved environment check to {out_file}")
    print(json.dumps(output, indent=2))

    if not output["overall"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
