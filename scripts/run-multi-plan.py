#!/usr/bin/env python3
"""
Run a multi-plan Claude Code experiment.
Usage: python scripts/run-multi-plan.py <experiment_dir> [--plans 01 02] [--runs 10] [--rebuild-env] [--dry-run]
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


SCRIPT_DIR = Path(__file__).resolve().parent
BUILD_ENV_SCRIPT = SCRIPT_DIR / "build-env.py"
CHECK_ENV_SCRIPT = SCRIPT_DIR / "check-env.py"
RUN_EXPERIMENT_SCRIPT = SCRIPT_DIR / "run-experiment.py"

def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run multi-plan experiment")
    parser.add_argument("experiment_dir", help="Path to experiment directory")
    parser.add_argument(
        "--plans",
        nargs="+",
        help="Specific plan numbers to run, e.g. --plans 01 02 03",
    )
    parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=10,
        help="Runs per plan (default: 10)",
    )
    parser.add_argument(
        "--rebuild-env",
        action="store_true",
        help="Force rebuild the Docker validation image before running",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing",
    )
    return parser.parse_args()


def load_task(exp_path: Path) -> Dict[str, Any]:
    task_file = exp_path / "task_full.json"
    if not task_file.exists():
        raise FileNotFoundError(f"task_full.json not found: {task_file}")
    return json.loads(task_file.read_text())


def derive_image_tag(exp_path: Path, task: Dict[str, Any]) -> str:
    if task.get("instance_id"):
        suffix = str(task["instance_id"]).replace("/", "-").replace("__", "-")
    else:
        suffix = exp_path.name.replace("_", "-")
    return f"swe-env:{suffix}"


def run_command(command: List[str], description: str, dry_run: bool = False) -> None:
    quoted = " ".join(str(part) for part in command)
    print(f"{description}: {quoted}")
    if dry_run:
        return
    subprocess.run(command, check=True)


def docker_image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def normalize_plan_selector(value: str) -> str:
    value = value.strip()
    if value.startswith("plan-"):
        value = value[5:]
    return value.zfill(2)


def discover_plans(plans_dir: Path, selected_plan_numbers: Optional[List[str]] = None) -> List[Path]:
    plan_files = sorted(plans_dir.glob("plan-*.md"))
    if selected_plan_numbers is None:
        return plan_files

    wanted = {normalize_plan_selector(item) for item in selected_plan_numbers}
    filtered = []
    for plan_path in plan_files:
        plan_number = plan_path.stem.replace("plan-", "")
        if plan_number in wanted:
            filtered.append(plan_path)
    return filtered


def plan_result_root(exp_path: Path, plan_name: str) -> Path:
    return exp_path / "results" / plan_name


def list_existing_run_numbers(runs_dir: Path) -> List[int]:
    numbers = []
    if not runs_dir.exists():
        return numbers

    for run_dir in sorted(runs_dir.glob("run-*")):
        if not run_dir.is_dir():
            continue
        try:
            numbers.append(int(run_dir.name.split("-")[-1]))
        except ValueError:
            continue
    return sorted(numbers)


def missing_run_numbers(runs_dir: Path, expected_runs: int) -> List[int]:
    existing = set(list_existing_run_numbers(runs_dir))
    return [run_num for run_num in range(1, expected_runs + 1) if run_num not in existing]


def ensure_environment(exp_path: Path, image_tag: str, rebuild_env: bool, dry_run: bool) -> None:
    should_build = rebuild_env or not docker_image_exists(image_tag)
    if should_build:
        run_command(
            [sys.executable, str(BUILD_ENV_SCRIPT), str(exp_path)],
            "Build validation image",
            dry_run=dry_run,
        )
    else:
        print(f"Validation image already exists: {image_tag}")

    run_command(
        [sys.executable, str(CHECK_ENV_SCRIPT), str(exp_path), "--image", image_tag],
        "Validate environment",
        dry_run=dry_run,
    )


def copy_plan_snapshot(source_plan: Path, destination_plan: Path, dry_run: bool) -> None:
    print(f"Snapshot plan to result directory: {destination_plan}")
    if dry_run:
        return
    destination_plan.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_plan, destination_plan)


def run_single_plan(
    exp_path: Path,
    plan_path: Path,
    image_tag: str,
    runs_per_plan: int,
    dry_run: bool,
) -> Dict[str, Any]:
    plan_name = plan_path.stem
    result_root = plan_result_root(exp_path, plan_name)
    runs_dir = result_root / "runs"
    analysis_dir = result_root / "analysis"
    snapshot_plan = result_root / "plan.md"
    summary_file = analysis_dir / "runs-summary.json"

    print(f"\n=== Plan {plan_name} ===")
    print(f"Source plan: {plan_path}")
    print(f"Result root: {result_root}")

    copy_plan_snapshot(plan_path, snapshot_plan, dry_run=dry_run)

    if summary_file.exists() and not dry_run:
        print(f"Skip completed plan: {summary_file}")
        return {
            "plan": plan_name,
            "status": "skipped_completed",
            "summary_file": str(summary_file),
            "missing_runs": [],
        }

    missing_runs = missing_run_numbers(runs_dir, runs_per_plan)
    if not missing_runs:
        print("No missing runs. Regenerating summary only.")
        command = [
            sys.executable,
            str(RUN_EXPERIMENT_SCRIPT),
            str(exp_path),
            "--runs",
            "0",
            "--plan-file",
            str(plan_path),
            "--runs-dir",
            str(runs_dir),
            "--analysis-dir",
            str(analysis_dir),
            "--validation-image",
            image_tag,
        ]
        run_command(command, f"Refresh summary for {plan_name}", dry_run=dry_run)
        return {
            "plan": plan_name,
            "status": "summary_refreshed",
            "summary_file": str(summary_file),
            "missing_runs": [],
        }

    print(f"Missing runs for {plan_name}: {', '.join(f'{n:03d}' for n in missing_runs)}")
    for run_num in missing_runs:
        command = [
            sys.executable,
            str(RUN_EXPERIMENT_SCRIPT),
            str(exp_path),
            "--runs",
            "1",
            "--start",
            str(run_num),
            "--plan-file",
            str(plan_path),
            "--runs-dir",
            str(runs_dir),
            "--analysis-dir",
            str(analysis_dir),
            "--validation-image",
            image_tag,
        ]
        run_command(command, f"Run {plan_name} / run-{run_num:03d}", dry_run=dry_run)

    return {
        "plan": plan_name,
        "status": "executed" if not dry_run else "dry_run",
        "summary_file": str(summary_file),
        "missing_runs": missing_runs,
    }


def compute_average(values: List[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def build_status_breakdown(run_statuses: List[Dict[str, Any]]) -> Dict[str, int]:
    breakdown: Dict[str, int] = {}
    for item in run_statuses:
        status = item.get("status", "unknown")
        breakdown[status] = breakdown.get(status, 0) + 1
    return breakdown


def parse_duration_seconds(run_status: Dict[str, Any]) -> Optional[float]:
    start_raw = run_status.get("start_time", "")
    end_raw = run_status.get("end_time", "")
    if not start_raw or not end_raw:
        return None
    try:
        start = datetime.fromisoformat(start_raw)
        end = datetime.fromisoformat(end_raw)
    except ValueError:
        return None
    return (end - start).total_seconds()


def summarize_plan(summary: Dict[str, Any], plan_name: str) -> Dict[str, Any]:
    run_statuses = summary.get("run_statuses", [])
    total_runs = summary.get("total_runs", len(run_statuses))
    successful_runs = summary.get("successful_runs", 0)
    validation = summary.get("validation", {})
    token_summary = summary.get("tokens", {})

    durations = []
    for item in run_statuses:
        seconds = parse_duration_seconds(item)
        if seconds is not None:
            durations.append(seconds)

    status_breakdown = summary.get("status_breakdown") or build_status_breakdown(run_statuses)

    diff_stats = summary.get("statistics", {}).get("diff_size_bytes", {})
    changed_stats = summary.get("statistics", {}).get("files_changed", {})

    return {
        "plan": plan_name,
        "total_runs": total_runs,
        "successful_runs": successful_runs,
        "success_rate": successful_runs / total_runs if total_runs else 0.0,
        "perfect_validation_rate": validation.get("perfect_runs", 0) / total_runs if total_runs else 0.0,
        "status_breakdown": status_breakdown,
        "status_diversity": len(status_breakdown),
        "diff_size_bytes": {
            "min": diff_stats.get("min", 0),
            "max": diff_stats.get("max", 0),
            "avg": diff_stats.get("avg", 0),
            "range": diff_stats.get("range", diff_stats.get("max", 0) - diff_stats.get("min", 0)),
        },
        "changed_files_count": {
            "min": changed_stats.get("min", 0),
            "max": changed_stats.get("max", 0),
            "avg": changed_stats.get("avg", 0),
            "range": changed_stats.get("range", changed_stats.get("max", 0) - changed_stats.get("min", 0)),
        },
        "duration_seconds": {
            "min": min(durations) if durations else 0.0,
            "max": max(durations) if durations else 0.0,
            "avg": compute_average(durations),
            "range": (max(durations) - min(durations)) if durations else 0.0,
        },
        "validation": {
            "average_functional_score": validation.get("average_functional_score", 0.0),
            "average_regression_score": validation.get("average_regression_score", 0.0),
            "average_overall_score": validation.get("average_overall_score", 0.0),
            "perfect_runs": validation.get("perfect_runs", 0),
            "total_validated": validation.get("total_validated", 0),
        },
        "token_usage": {
            "average_input_tokens": token_summary.get("average_input_tokens", 0.0),
            "average_output_tokens": token_summary.get("average_output_tokens", 0.0),
            "average_cache_read_input_tokens": token_summary.get("average_cache_read_input_tokens", 0.0),
            "average_total_tokens": token_summary.get("average_total_tokens", 0.0),
        },
        "variability_score": (
            diff_stats.get("range", diff_stats.get("max", 0) - diff_stats.get("min", 0))
            + changed_stats.get("range", changed_stats.get("max", 0) - changed_stats.get("min", 0))
            + len(status_breakdown) * 100
        ),
    }


def choose_plan(plans: List[Dict[str, Any]], key_path: List[str], highest: bool) -> Optional[Dict[str, Any]]:
    if not plans:
        return None

    def extract(plan: Dict[str, Any]) -> Any:
        current: Any = plan
        for key in key_path:
            current = current.get(key, 0) if isinstance(current, dict) else 0
        return current

    return max(plans, key=extract) if highest else min(plans, key=extract)


def build_comparison_summary(exp_path: Path, plan_files: List[Path]) -> Dict[str, Any]:
    plan_summaries = []
    for plan_path in plan_files:
        plan_name = plan_path.stem
        summary_file = plan_result_root(exp_path, plan_name) / "analysis" / "runs-summary.json"
        if not summary_file.exists():
            continue
        summary_data = json.loads(summary_file.read_text())
        plan_summaries.append(summarize_plan(summary_data, plan_name))

    comparison = {
        "experiment": exp_path.name,
        "generated_at": utc_now_iso(),
        "plans": plan_summaries,
        "cross_plan": {
            "highest_success_rate": choose_plan(plan_summaries, ["success_rate"], highest=True),
            "lowest_success_rate": choose_plan(plan_summaries, ["success_rate"], highest=False),
            "highest_overall_validation": choose_plan(plan_summaries, ["validation", "average_overall_score"], highest=True),
            "lowest_overall_validation": choose_plan(plan_summaries, ["validation", "average_overall_score"], highest=False),
            "most_variable_diff_size": choose_plan(plan_summaries, ["diff_size_bytes", "range"], highest=True),
            "least_variable_diff_size": choose_plan(plan_summaries, ["diff_size_bytes", "range"], highest=False),
            "most_variable_changed_files": choose_plan(plan_summaries, ["changed_files_count", "range"], highest=True),
            "least_variable_changed_files": choose_plan(plan_summaries, ["changed_files_count", "range"], highest=False),
            "most_variable_duration": choose_plan(plan_summaries, ["duration_seconds", "range"], highest=True),
            "least_variable_duration": choose_plan(plan_summaries, ["duration_seconds", "range"], highest=False),
            "most_variable_overall": choose_plan(plan_summaries, ["variability_score"], highest=True),
            "least_variable_overall": choose_plan(plan_summaries, ["variability_score"], highest=False),
        },
    }
    return comparison


def write_comparison_outputs(exp_path: Path, comparison: Dict[str, Any], dry_run: bool) -> None:
    output_dir = exp_path / "comparative-analysis"
    summary_file = output_dir / "comparison-summary.json"
    report_file = output_dir / "comparison-report.txt"

    print(f"Write comparative summary: {summary_file}")
    print(f"Write comparative report: {report_file}")
    if dry_run:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    summary_file.write_text(json.dumps(comparison, indent=2))

    lines = [
        f"Experiment: {comparison['experiment']}",
        f"Generated: {comparison['generated_at']}",
        "",
        "Per-plan summary:",
    ]

    for plan in comparison.get("plans", []):
        lines.extend([
            f"- {plan['plan']}",
            f"  success_rate={plan['success_rate']:.2%}",
            f"  perfect_validation_rate={plan['perfect_validation_rate']:.2%}",
            f"  diff_range={plan['diff_size_bytes']['range']}",
            f"  changed_files_range={plan['changed_files_count']['range']}",
            f"  duration_range={plan['duration_seconds']['range']:.2f}s",
            f"  avg_overall_validation={plan['validation']['average_overall_score']:.2%}",
            f"  variability_score={plan['variability_score']}",
            "",
        ])

    lines.append("Cross-plan comparison:")
    for key, value in comparison.get("cross_plan", {}).items():
        if value:
            lines.append(f"- {key}: {value['plan']}")
        else:
            lines.append(f"- {key}: N/A")

    report_file.write_text("\n".join(lines) + "\n")


def validate_experiment_layout(exp_path: Path) -> Path:
    if not exp_path.exists():
        raise FileNotFoundError(f"Experiment directory not found: {exp_path}")

    plans_dir = exp_path / "plans"
    repo_dir = exp_path / "repo"
    task_file = exp_path / "task_full.json"

    if not plans_dir.exists():
        raise FileNotFoundError(f"plans directory not found: {plans_dir}")
    if not repo_dir.exists():
        raise FileNotFoundError(f"repo directory not found: {repo_dir}")
    if not task_file.exists():
        raise FileNotFoundError(f"task_full.json not found: {task_file}")

    return plans_dir


def main() -> None:
    args = parse_args()
    exp_path = Path(args.experiment_dir).resolve()

    try:
        plans_dir = validate_experiment_layout(exp_path)
        task = load_task(exp_path)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        sys.exit(1)

    image_tag = derive_image_tag(exp_path, task)
    plan_files = discover_plans(plans_dir, args.plans)
    if not plan_files:
        print("Error: no matching plan files found")
        sys.exit(1)

    print("=== Multi-plan Experiment ===")
    print(f"Experiment: {exp_path}")
    print(f"Plans directory: {plans_dir}")
    print(f"Plans: {', '.join(path.stem for path in plan_files)}")
    print(f"Runs per plan: {args.runs}")
    print(f"Dry run: {args.dry_run}")
    print(f"Validation image: {image_tag}")
    print("=============================")

    try:
        ensure_environment(exp_path, image_tag, args.rebuild_env, args.dry_run)

        execution_results = []
        for plan_path in plan_files:
            execution_results.append(
                run_single_plan(
                    exp_path=exp_path,
                    plan_path=plan_path,
                    image_tag=image_tag,
                    runs_per_plan=args.runs,
                    dry_run=args.dry_run,
                )
            )

        comparison = build_comparison_summary(exp_path, plan_files)
        write_comparison_outputs(exp_path, comparison, args.dry_run)

    except subprocess.CalledProcessError as exc:
        print(f"Error: command failed with exit code {exc.returncode}")
        sys.exit(exc.returncode)

    print("\n=== Multi-plan Experiment Complete ===")
    for item in execution_results:
        print(f"- {item['plan']}: {item['status']}")
    print(f"Comparison summary: {exp_path / 'comparative-analysis' / 'comparison-summary.json'}")


if __name__ == "__main__":
    main()
