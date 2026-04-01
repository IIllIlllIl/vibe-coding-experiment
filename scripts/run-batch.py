#!/usr/bin/env python3
"""
Run multi-plan experiments across multiple SWE-bench tasks in batch.

Usage:
    python scripts/run-batch.py --tasks datasets/swe-bench-verified/selected-tasks.json
    python scripts/run-batch.py --tasks selected-tasks.json --runs 5 --dry-run
    python scripts/run-batch.py --tasks selected-tasks.json --only django__django-11951 sympy__sympy-12481

Workflow per task:
    1. Check experiment directory exists (experiments/<instance_id>/)
    2. Check plans/ directory has plan files
    3. Check Docker image exists (or build with --rebuild-env)
    4. Delegate to run-multi-plan.py for execution
    5. Collect results

Skip conditions:
    - No experiment directory → skip (run setup-task.py first)
    - No plan files → skip (plans not yet created)
    - All plans already completed → skip (handled by run-multi-plan.py)
"""

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
BUILD_ENV_SCRIPT = SCRIPT_DIR / "build-env.py"
RUN_MULTI_PLAN_SCRIPT = SCRIPT_DIR / "run-multi-plan.py"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run multi-plan experiments across multiple SWE-bench tasks"
    )
    parser.add_argument(
        "--tasks",
        default="datasets/swe-bench-verified/selected-tasks.json",
        help="Path to selected-tasks.json (default: datasets/swe-bench-verified/selected-tasks.json)",
    )
    parser.add_argument(
        "--experiments-dir",
        default="experiments",
        help="Root experiments directory (default: experiments)",
    )
    parser.add_argument(
        "--runs",
        "-n",
        type=int,
        default=5,
        help="Runs per plan (default: 5)",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        help="Only run specific instance_ids",
    )
    parser.add_argument(
        "--rebuild-env",
        action="store_true",
        help="Force rebuild Docker images before running",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing",
    )
    return parser.parse_args()


def load_selected_tasks(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        print(f"Error: tasks file not found: {path}")
        print("Run scripts/select-tasks.py first.")
        sys.exit(1)
    data = json.loads(path.read_text())
    return data.get("tasks", [])


def docker_image_exists(tag: str) -> bool:
    result = subprocess.run(
        ["docker", "image", "inspect", tag],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def derive_image_tag(instance_id: str) -> str:
    suffix = instance_id.replace("/", "-").replace("__", "-")
    return f"swe-env:{suffix}"


def check_task_ready(exp_dir: Path) -> Optional[str]:
    """Check if a task is ready to run. Returns skip reason or None if ready."""
    if not exp_dir.exists():
        return "no experiment directory (run setup-task.py first)"

    task_file = exp_dir / "task_full.json"
    if not task_file.exists():
        return "no task_full.json"

    repo_dir = exp_dir / "repo"
    if not repo_dir.exists():
        return "no repo/ directory"

    plans_dir = exp_dir / "plans"
    if not plans_dir.exists():
        return "no plans/ directory"

    plan_files = sorted(plans_dir.glob("plan-*.md"))
    if not plan_files:
        return "no plan files in plans/ (create plans first)"

    return None


def get_plan_files(exp_dir: Path) -> List[Path]:
    """Get list of plan files for a task."""
    plans_dir = exp_dir / "plans"
    return sorted(plans_dir.glob("plan-*.md"))


def run_task(
    instance_id: str,
    exp_dir: Path,
    runs_per_plan: int,
    rebuild_env: bool,
    dry_run: bool,
) -> Dict[str, Any]:
    """Run multi-plan experiment for a single task."""
    image_tag = derive_image_tag(instance_id)
    plan_files = get_plan_files(exp_dir)

    result: Dict[str, Any] = {
        "instance_id": instance_id,
        "exp_dir": str(exp_dir),
        "plans": [p.stem for p in plan_files],
        "runs_per_plan": runs_per_plan,
        "status": "unknown",
        "skip_reason": "",
    }

    # Build Docker image if needed
    should_build = rebuild_env or not docker_image_exists(image_tag)
    if should_build:
        print(f"  Building image: {image_tag}")
        cmd = [sys.executable, str(BUILD_ENV_SCRIPT), str(exp_dir)]
        if rebuild_env:
            pass  # build-env always rebuilds
        if dry_run:
            print(f"  [DRY RUN] Would run: {' '.join(cmd)}")
        else:
            try:
                subprocess.run(cmd, check=True)
            except subprocess.CalledProcessError as e:
                result["status"] = "build_failed"
                result["skip_reason"] = f"Docker build failed (exit {e.returncode})"
                return result
    else:
        print(f"  Image exists: {image_tag}")

    # Run multi-plan experiment
    cmd = [
        sys.executable,
        str(RUN_MULTI_PLAN_SCRIPT),
        str(exp_dir),
        "--runs", str(runs_per_plan),
    ]
    if dry_run:
        cmd.append("--dry-run")

    print(f"  Running multi-plan: {' '.join(cmd)}")
    try:
        subprocess.run(cmd, check=True)
        result["status"] = "completed"
    except subprocess.CalledProcessError as e:
        result["status"] = "execution_failed"
        result["skip_reason"] = f"run-multi-plan.py failed (exit {e.returncode})"

    return result


def main():
    args = parse_args()
    tasks_path = Path(args.tasks).resolve()
    experiments_dir = Path(args.experiments_dir).resolve()

    selected_tasks = load_selected_tasks(tasks_path)
    print(f"Loaded {len(selected_tasks)} tasks from {tasks_path}")

    # Filter to --only if specified
    if args.only:
        only_set = set(args.only)
        selected_tasks = [t for t in selected_tasks if t["instance_id"] in only_set]
        print(f"Filtered to {len(selected_tasks)} tasks: {args.only}")

    print(f"Runs per plan: {args.runs}")
    print(f"Experiments dir: {experiments_dir}")
    print(f"Dry run: {args.dry_run}")
    print("=" * 60)

    results: List[Dict[str, Any]] = []

    for i, task in enumerate(selected_tasks, 1):
        instance_id = task["instance_id"]
        exp_dir = experiments_dir / instance_id

        print(f"\n[{i}/{len(selected_tasks)}] {instance_id}")

        # Check readiness
        skip_reason = check_task_ready(exp_dir)
        if skip_reason:
            print(f"  SKIP: {skip_reason}")
            results.append({
                "instance_id": instance_id,
                "status": "skipped",
                "skip_reason": skip_reason,
            })
            continue

        plan_files = get_plan_files(exp_dir)
        print(f"  Plans: {', '.join(p.stem for p in plan_files)}")

        # Run the task
        result = run_task(
            instance_id, exp_dir,
            runs_per_plan=args.runs,
            rebuild_env=args.rebuild_env,
            dry_run=args.dry_run,
        )
        results.append(result)

    # Summary
    status_counts = {}
    for r in results:
        s = r["status"]
        status_counts[s] = status_counts.get(s, 0) + 1

    summary = {
        "batch_date": datetime.now(UTC).isoformat(),
        "total_tasks": len(results),
        "runs_per_plan": args.runs,
        "status_counts": status_counts,
        "tasks": results,
    }

    summary_file = experiments_dir / "batch-summary.json"
    summary_file.write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 60)
    print("BATCH SUMMARY")
    print("=" * 60)
    for r in results:
        status = r["status"]
        reason = r.get("skip_reason", "")
        line = f"  {r['instance_id']}: {status}"
        if reason:
            line += f" ({reason})"
        print(line)
    print("-" * 60)
    print(f"Total: {len(results)}")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")
    print(f"\nSummary saved: {summary_file}")


if __name__ == "__main__":
    main()
