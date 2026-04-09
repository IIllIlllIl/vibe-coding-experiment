#!/usr/bin/env python3
"""
Experiment execution script for Claude Code variability study.
Usage: python scripts/run-experiment.py <experiment_dir> [--runs N] [--start N] [--dry-run]
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


SUCCESS_STATUSES = {"success", "success_timeout", "success_with_error"}


def extract_token_usage(run_path: Path) -> Dict[str, int]:
    """Extract token usage details from transcript.json if available."""
    transcript_file = run_path / "transcript.json"
    empty_usage = {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "total_tokens": 0,
    }

    if not transcript_file.exists():
        return empty_usage

    try:
        with open(transcript_file) as f:
            data = json.load(f)

        def build_usage(usage: Dict[str, Any]) -> Dict[str, int]:
            input_tokens = usage.get("input_tokens", 0)
            output_tokens = usage.get("output_tokens", 0)
            cache_read_input_tokens = usage.get("cache_read_input_tokens", 0)
            total_tokens = usage.get("total_tokens")

            if not isinstance(input_tokens, int):
                input_tokens = 0
            if not isinstance(output_tokens, int):
                output_tokens = 0
            if not isinstance(cache_read_input_tokens, int):
                cache_read_input_tokens = 0
            if not isinstance(total_tokens, int):
                total_tokens = input_tokens + output_tokens

            return {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read_input_tokens,
                "total_tokens": total_tokens,
            }

        usage = data.get("usage")
        if isinstance(usage, dict):
            return build_usage(usage)

        model_usage = data.get("modelUsage")
        if isinstance(model_usage, dict):
            input_tokens = 0
            output_tokens = 0
            cache_read_input_tokens = 0
            found = False
            for model_data in model_usage.values():
                if not isinstance(model_data, dict):
                    continue
                model_input = model_data.get("inputTokens")
                model_output = model_data.get("outputTokens")
                model_cache_read = model_data.get("cacheReadInputTokens")
                if isinstance(model_input, int):
                    input_tokens += model_input
                    found = True
                if isinstance(model_output, int):
                    output_tokens += model_output
                    found = True
                if isinstance(model_cache_read, int):
                    cache_read_input_tokens += model_cache_read
                    found = True
            if found:
                return {
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_input_tokens": cache_read_input_tokens,
                    "total_tokens": input_tokens + output_tokens,
                }

        stdout = data.get("stdout", "")
        if stdout:
            try:
                stdout_data = json.loads(stdout)
                usage = stdout_data.get("usage")
                if isinstance(usage, dict):
                    return build_usage(usage)
            except json.JSONDecodeError:
                pass

            match = re.search(r'"tokens?"\s*:\s*(\d+)', stdout)
            if match:
                total = int(match.group(1))
                return {**empty_usage, "total_tokens": total}

            match = re.search(r'Total tokens?:?\s*(\d+)', stdout, re.IGNORECASE)
            if match:
                total = int(match.group(1))
                return {**empty_usage, "total_tokens": total}

        return empty_usage
    except Exception:
        return empty_usage


def extract_tokens(run_path: Path) -> int:
    """Extract total token count from transcript.json if available."""
    return extract_token_usage(run_path)["total_tokens"]


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Claude Code experiment with fixed plan"
    )
    parser.add_argument(
        "experiment_dir",
        help="Path to experiment directory (e.g., experiments/exp-001-django-10924)"
    )
    parser.add_argument(
        "--runs", "-n",
        type=int,
        default=1,
        help="Number of executions (default: 1)"
    )
    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Starting run number (default: 1)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without executing"
    )
    parser.add_argument(
        "--validation-image",
        help="Docker image to use for validation test execution"
    )
    parser.add_argument(
        "--plan-file",
        help="Path to plan.md file (default: experiment_dir/plan.md)"
    )
    parser.add_argument(
        "--runs-dir",
        help="Directory to store run outputs (default: experiment_dir/runs)"
    )
    parser.add_argument(
        "--analysis-dir",
        help="Directory to store summary outputs (default: experiment_dir/analysis)"
    )
    parser.add_argument(
        "--keep-work",
        action="store_true",
        help="Keep temporary work/ and validation/ directories after each run (default: delete them)"
    )
    parser.add_argument(
        "--claude-permission-mode",
        default="acceptEdits",
        help="Permission mode for Claude Code (default: acceptEdits)"
    )
    parser.add_argument(
        "--docker-cpus",
        type=str,
        default=None,
        help="CPU limit for Docker container (e.g., '2'). Passed to --cpus flag."
    )
    parser.add_argument(
        "--docker-memory",
        type=str,
        default=None,
        help="Memory limit for Docker container (e.g., '4g'). Passed to --memory flag."
    )
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Re-run validation for existing runs and rebuild summary (does NOT re-run Claude)"
    )
    return parser.parse_args()


def resolve_path(path_str: Optional[str], default_path: Path) -> Path:
    if not path_str:
        return default_path
    return Path(path_str).resolve()


def ensure_run_range_available(runs_dir: Path, start: int, runs: int) -> None:
    """Fail if any requested run directory already exists."""
    existing = []

    for run_num in range(start, start + runs):
        run_dir = runs_dir / f"run-{run_num:03d}"
        if run_dir.exists():
            existing.append(run_dir.name)

    if existing:
        raise FileExistsError(
            "Requested run numbers already exist: " + ", ".join(existing)
        )


def setup_run_directory(runs_dir: Path, run_num: int) -> Path:
    """Create run directory and return path."""
    runs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = runs_dir / f"run-{run_num:03d}"
    run_dir.mkdir(exist_ok=True)
    return run_dir


def prepare_working_copy(exp_path: Path, run_path: Path) -> Path:
    """
    Create a working copy of the repository at base commit.
    Returns the path to the working copy.
    """
    source_repo = exp_path / "repo"
    if not source_repo.exists():
        raise FileNotFoundError(f"Source repository not found: {source_repo}")

    base_commit_file = exp_path / "base-commit.txt"
    if base_commit_file.exists():
        base_commit = base_commit_file.read_text().strip()
    else:
        metadata_file = exp_path / "metadata.json"
        if metadata_file.exists():
            with open(metadata_file) as f:
                metadata = json.load(f)
                base_commit = metadata.get("base_commit", "")
        else:
            base_commit = ""

    work_dir = run_path / "work"
    work_dir.mkdir(exist_ok=True)

    if (work_dir / ".git").exists():
        shutil.rmtree(work_dir)

    shutil.copytree(source_repo, work_dir, dirs_exist_ok=True)

    if base_commit:
        subprocess.run(
            ["git", "reset", "--hard", base_commit],
            cwd=work_dir,
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["git", "clean", "-fd"],
            cwd=work_dir,
            capture_output=True
        )

    commit_info_file = run_path / "commit-info.txt"
    commit_info_file.write_text(f"Base commit: {base_commit}\n")

    return work_dir


def create_execution_prompt(plan_path: Path) -> str:
    """Load plan and wrap with minimal execution directive."""
    if not plan_path.exists():
        raise FileNotFoundError(f"Plan file not found: {plan_path}")

    plan_content = plan_path.read_text()

    prompt_template = """Below is an approved final execution plan.

Do not re-plan, do not rewrite the plan, do not propose alternatives, do not restate the plan.
Proceed to implement this plan directly.

Approved plan:
--- plan start ---
{plan_content}
--- plan end ---"""

    return prompt_template.format(plan_content=plan_content)


def run_claude_code(
    work_dir: Path,
    prompt: str,
    dry_run: bool,
    claude_permission_mode: str = "acceptEdits",
    executor_image: Optional[str] = None,
    docker_cpus: Optional[str] = None,
    docker_memory: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute Claude Code with the prompt inside a Docker container.

    Args:
        work_dir: Working directory for execution.
        prompt: The prompt to send to Claude.
        dry_run: If True, skip actual execution.
        claude_permission_mode: Permission mode for Claude (e.g. acceptEdits, bypassPermissions).
        executor_image: Docker image to use.
        docker_cpus: CPU limit for Docker container (e.g. "2").
        docker_memory: Memory limit for Docker container (e.g. "4g").
    """
    start_time = utc_now_iso()
    claude_cmd_label = f"claude -p --permission-mode {claude_permission_mode} --output-format json"

    if dry_run:
        print(f"  [DRY RUN] Would execute Claude Code in: {work_dir}")
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": 0,
            "status": "dry_run",
            "transcript": "",
            "error": ""
        }

    return _run_claude_code_docker(
        work_dir, prompt, start_time, claude_cmd_label, claude_permission_mode,
        executor_image, docker_cpus=docker_cpus, docker_memory=docker_memory,
    )


def _run_claude_code_docker(
    work_dir: Path,
    prompt: str,
    start_time: str,
    claude_cmd_label: str,
    claude_permission_mode: str,
    executor_image: Optional[str],
    docker_cpus: Optional[str] = None,
    docker_memory: Optional[str] = None,
) -> Dict[str, Any]:
    """Run Claude Code inside a Docker container."""
    if not executor_image:
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": -1,
            "status": "error",
            "error": "Docker execution requires --executor-image or a valid claude-executor-image.txt"
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    auth_token = os.environ.get("ANTHROPIC_AUTH_TOKEN", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "")

    if not api_key and not auth_token:
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": -1,
            "status": "error",
            "error": "ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN environment variable is not set"
        }

    # Write auth env vars to a temporary env file to avoid exposure in ps/process listing
    env_file = None
    try:
        fd, env_path = tempfile.mkstemp(prefix="claude-env-")
        lines = []
        if api_key:
            lines.append(f"ANTHROPIC_API_KEY={api_key}\n")
        if auth_token:
            lines.append(f"ANTHROPIC_AUTH_TOKEN={auth_token}\n")
        if base_url:
            lines.append(f"ANTHROPIC_BASE_URL={base_url}\n")
        os.write(fd, "".join(lines).encode())
        os.close(fd)
        env_file = Path(env_path)
        os.chmod(env_file, 0o600)
    except Exception:
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": -1,
            "status": "error",
            "error": "Failed to create temporary env file for API key"
        }

    uid = os.getuid()
    gid = os.getgid()

    container_id = None

    docker_cmd = [
        "docker", "run",
        "--rm",
        "-v", f"{work_dir.resolve()}:/testbed",
        "-w", "/testbed",
        "-e", "HOME=/testbed",
        "--env-file", str(env_file),
        "--user", f"{uid}:{gid}",
        "--label", f"experiment-work={work_dir.resolve()}",
    ]
    if docker_cpus:
        docker_cmd.extend(["--cpus", docker_cpus])
    if docker_memory:
        docker_cmd.extend(["--memory", docker_memory])
    docker_cmd.extend([
        "-i",
        executor_image,
        "bash", "-c",
        "source /opt/miniconda3/etc/profile.d/conda.sh 2>/dev/null && conda activate testbed 2>/dev/null; exec claude -p --permission-mode " + claude_permission_mode + " --output-format json",
    ])

    print(f"  Docker image: {executor_image}")
    print(f"  Container user: {uid}:{gid}")

    def _kill_orphaned_containers() -> None:
        """Kill any containers associated with this work_dir."""
        try:
            ps_result = subprocess.run(
                ["docker", "ps", "-q", "--filter", f"label=experiment-work={work_dir.resolve()}"],
                capture_output=True, text=True, timeout=10,
            )
            for cid in ps_result.stdout.strip().splitlines():
                if cid:
                    print(f"  Killing orphaned container: {cid[:12]}")
                    subprocess.run(["docker", "kill", cid], capture_output=True, timeout=15)
        except Exception:
            pass

    try:
        result = subprocess.run(
            docker_cmd,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=3600,
        )

        end_time = utc_now_iso()

        transcript_file = work_dir.parent / "transcript.json"
        stdout_text = result.stdout or ""
        transcript_data = None

        if stdout_text.strip():
            try:
                transcript_data = json.loads(stdout_text)
            except json.JSONDecodeError:
                transcript_data = None

        if isinstance(transcript_data, dict):
            transcript_data.update({
                "raw_stdout": stdout_text,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "command": claude_cmd_label,
                "cwd": "/testbed",
                "execution_mode": "docker",
                "executor_image": executor_image,
            })
        else:
            transcript_data = {
                "stdout": stdout_text,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "command": claude_cmd_label,
                "cwd": "/testbed",
                "execution_mode": "docker",
                "executor_image": executor_image,
            }

        transcript_file.write_text(json.dumps(transcript_data, indent=2))

        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": end_time,
            "exit_code": result.returncode,
            "status": "success" if result.returncode == 0 else "failed",
            "transcript_file": str(transcript_file),
            "error": result.stderr if result.returncode != 0 else ""
        }

    except subprocess.TimeoutExpired:
        end_time = utc_now_iso()
        print("  ⚠️  Container timed out, killing...")
        _kill_orphaned_containers()

        transcript_file = work_dir.parent / "transcript.json"
        transcript_data = {
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "command": claude_cmd_label,
            "cwd": "/testbed",
            "timeout": True,
            "execution_mode": "docker",
            "executor_image": executor_image,
        }
        transcript_file.write_text(json.dumps(transcript_data, indent=2))

        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": end_time,
            "exit_code": -1,
            "status": "timeout",
            "transcript_file": str(transcript_file),
            "error": "Execution exceeded 1 hour timeout (Docker container killed)"
        }
    except KeyboardInterrupt:
        print("  ⚠️  Interrupted, killing container...")
        _kill_orphaned_containers()
        raise
    except FileNotFoundError:
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": -1,
            "status": "error",
            "error": "Docker not found. Please ensure 'docker' is installed and in PATH."
        }
    except Exception as e:
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": -1,
            "status": "error",
            "error": str(e)
        }
    finally:
        # Always clean up the temporary env file
        if env_file and env_file.exists():
            try:
                env_file.unlink()
            except Exception:
                pass


def classify_run(exit_code: int, diff_size: int, validation: Optional[Dict[str, Any]] = None) -> str:
    """Classify run status based on exit_code, diff, and validation results."""
    has_code = diff_size > 0
    has_validation = validation is not None
    validation_passed = (
        has_validation
        and validation.get("correctness", {}).get("overall", 0) == 1.0
    )

    if not has_code and exit_code == 0:
        return "no_changes"

    if has_code and validation_passed:
        if exit_code == 0:
            return "success"
        if exit_code == -1:
            return "success_timeout"
        return "success_with_error"

    if has_code and has_validation and not validation_passed:
        if exit_code == -1:
            return "partial_timeout"
        return "partial"

    if has_code and not has_validation:
        if exit_code == -1:
            return "timeout"
        return "code_produced"

    return "failed"


def collect_results(run_path: Path, work_dir: Path) -> Dict[str, Any]:
    """Collect diff and changed files, including untracked new files."""
    results: Dict[str, Any] = {}

    diff_file = run_path / "final.diff"
    changed_files_file = run_path / "changed-files.txt"
    try:
        # Stage all changes (including untracked files) so they appear in the diff
        subprocess.run(
            ["git", "add", "-A"],
            cwd=work_dir,
            capture_output=True,
            check=False
        )
        with open(diff_file, "w") as f:
            subprocess.run(
                ["git", "diff", "--cached"],
                cwd=work_dir,
                stdout=f,
                stderr=subprocess.DEVNULL,
                check=False
            )

        # Capture changed file list BEFORE unstaging
        name_result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False
        )
        changed_files = [f for f in name_result.stdout.strip().split("\n") if f]
        changed_files_file.write_text("\n".join(changed_files))
        results["changed_files"] = changed_files
        results["changed_files_count"] = len(changed_files)

        # Unstage to restore working tree state
        subprocess.run(
            ["git", "reset", "HEAD"],
            cwd=work_dir,
            capture_output=True,
            check=False
        )
        diff_size = diff_file.stat().st_size if diff_file.exists() else 0
        results["diff_file"] = str(diff_file)
        results["diff_size"] = diff_size
    except Exception as e:
        results["diff_error"] = str(e)
        results.setdefault("changed_files_count", 0)

    return results


def load_task_metadata(exp_path: Path) -> Dict[str, Any]:
    """Load test validation data from task_full.json."""
    task_file = exp_path / "task_full.json"
    if not task_file.exists():
        return {}

    with open(task_file) as f:
        data = json.load(f)

    fail_to_pass = data.get("FAIL_TO_PASS", [])
    pass_to_pass = data.get("PASS_TO_PASS", [])
    if isinstance(fail_to_pass, str):
        fail_to_pass = json.loads(fail_to_pass)
    if isinstance(pass_to_pass, str):
        pass_to_pass = json.loads(pass_to_pass)

    return {
        "test_patch": data.get("test_patch", ""),
        "fail_to_pass": fail_to_pass,
        "pass_to_pass": pass_to_pass,
        "gold_patch": data.get("patch", ""),
        "repo": data.get("repo", ""),
        "instance_id": data.get("instance_id", ""),
        "version": data.get("version", ""),
        "base_commit": data.get("base_commit", ""),
        "environment_setup_commit": data.get("environment_setup_commit", ""),
        "hints_text": data.get("hints_text", ""),
        "created_at": data.get("created_at", ""),
    }


def _normalize_path(p: str) -> str:
    """Normalize a diff path: strip a/ b/ prefix and remove leading ./"""
    if p.startswith("a/") or p.startswith("b/"):
        p = p[2:]
    if p.startswith("./"):
        p = p[2:]
    return p


def parse_diff_file_paths(patch_content: str) -> set:
    """Extract file paths from a unified diff (used by rebuild_run_result fallback)."""
    paths = set()
    rename_re = re.compile(r'^rename (?:from|to) (.+)$')
    for line in patch_content.splitlines():
        if line.startswith("diff --git "):
            rest = line[len("diff --git "):]
            b_idx = rest.rfind(" b/")
            if b_idx >= 0:
                paths.add(_normalize_path(rest[:b_idx]))
                paths.add(_normalize_path(rest[b_idx + 1:]))
            continue
        m = rename_re.match(line)
        if m:
            paths.add(_normalize_path(m.group(1)))
    return paths


def run_validation_official(
    run_path: Path,
    task_metadata: Dict[str, Any],
    diff_content: str,
    image_tag: str,
) -> Dict[str, Any]:
    """Run validation using the official SWE-bench run_instance() function.

    run_instance() handles everything inside the container:
    1. Applies model_patch (final.diff) via git apply
    2. Runs eval.sh which applies test_patch, runs tests, reverts test_patch
    3. Grades results using official parsers

    Returns dict matching our validation-results.json schema.
    """
    import docker as docker_sdk
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from swebench_adapter import ensure_swebench_importable, convert_report_to_validation_results
    ensure_swebench_importable()

    from swebench.harness.run_evaluation import run_instance
    from swebench.harness.test_spec.test_spec import make_test_spec

    instance_id = task_metadata["instance_id"]

    # Build the SWEbenchInstance dict from our task_metadata
    # task_full.json already has the right schema
    instance = dict(task_metadata)
    # Ensure FAIL_TO_PASS and PASS_TO_PASS are JSON strings for make_test_spec
    for key in ("FAIL_TO_PASS", "PASS_TO_PASS"):
        val = instance.get(key)
        if isinstance(val, list):
            instance[key] = json.dumps(val)

    # Official SWE-bench images use x86_64 conda packages
    arch = "x86_64"

    try:
        test_spec = make_test_spec(instance, arch=arch)
    except Exception as e:
        print(f"  make_test_spec() failed: {e}")
        val_file = run_path / "validation-results.json"
        with open(val_file, "w") as f:
            json.dump({"correctness": {"overall": 0}, "error": str(e)}, f, indent=2)
        return {"correctness": {"overall": 0}, "error": str(e)}

    pred = {
        "instance_id": instance_id,
        "model_name_or_path": "claude-code",
        "model_patch": diff_content,
    }

    client = docker_sdk.from_env()
    run_id = f"exp-{run_path.name}"

    print(f"  Running official validation via run_instance()...")
    print(f"  Instance image: {test_spec.instance_image_key}")

    completed = True
    report = {}
    try:
        result = run_instance(
            test_spec=test_spec,
            pred=pred,
            rm_image=False,
            force_rebuild=False,
            client=client,
            run_id=run_id,
            timeout=300,
        )
        completed = result.get("completed", False)

        # Read the report.json written by run_instance
        from swebench.harness.constants import RUN_EVALUATION_LOG_DIR
        report_path = RUN_EVALUATION_LOG_DIR / run_id / "claude-code" / instance_id / "report.json"
        if report_path.exists():
            report = json.loads(report_path.read_text())
            print(f"  Report loaded from {report_path}")
        else:
            # Fallback: try relative path
            for candidate in [
                Path(f"logs/run_evaluation/{run_id}/claude-code/{instance_id}/report.json"),
                Path(f"../logs/run_evaluation/{run_id}/claude-code/{instance_id}/report.json"),
            ]:
                if candidate.exists():
                    report = json.loads(candidate.read_text())
                    print(f"  Report loaded from {candidate}")
                    break

    except Exception as e:
        print(f"  run_instance() failed: {e}")
        completed = False

    # Convert official report to our validation-results.json schema
    fail_to_pass = task_metadata.get("fail_to_pass", [])
    pass_to_pass = task_metadata.get("pass_to_pass", [])

    validation_result = convert_report_to_validation_results(
        instance_id=instance_id,
        image_tag=image_tag,
        report=report,
        fail_to_pass=fail_to_pass,
        pass_to_pass=pass_to_pass,
        completed=completed,
    )

    val_file = run_path / "validation-results.json"
    with open(val_file, "w") as f:
        json.dump(validation_result, f, indent=2)

    print(f"  ✅ Validation results saved to {val_file}")
    return validation_result


def build_validation_image_path(exp_path: Path) -> Optional[str]:
    """Read validation image tag from env-image.txt if present."""
    image_file = exp_path / "env-image.txt"
    if not image_file.exists():
        return None
    image = image_file.read_text().strip()
    return image or None


def load_base_commit(exp_path: Path) -> str:
    base_commit_file = exp_path / "base-commit.txt"
    if base_commit_file.exists():
        return base_commit_file.read_text().strip()

    metadata_file = exp_path / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)
        return str(metadata.get("base_commit", "")).strip()

    return ""


def extract_run_id(run_path: Path) -> int:
    match = re.fullmatch(r"run-(\d+)", run_path.name)
    if not match:
        raise ValueError(f"Invalid run directory name: {run_path.name}")
    return int(match.group(1))


def parse_timestamp(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def load_transcript_metadata(run_path: Path) -> Dict[str, Any]:
    transcript_file = run_path / "transcript.json"
    if not transcript_file.exists():
        return {}

    try:
        with open(transcript_file) as f:
            data = json.load(f)
    except Exception:
        return {}

    return {
        "exit_code": data.get("exit_code", -1),
        "error": data.get("stderr", "") if data.get("exit_code", 0) != 0 else "",
        "timeout": bool(data.get("timeout", False)),
        "duration_ms": data.get("duration_ms"),
        "duration_api_ms": data.get("duration_api_ms"),
    }


def rebuild_run_result(run_path: Path) -> Dict[str, Any]:
    run_id = extract_run_id(run_path)
    result: Dict[str, Any] = {"run_id": run_id}

    transcript_meta = load_transcript_metadata(run_path)
    result["exit_code"] = transcript_meta.get("exit_code", -1)
    result["error"] = transcript_meta.get("error", "")

    diff_file = run_path / "final.diff"
    diff_size = diff_file.stat().st_size if diff_file.exists() else 0
    result["diff_file"] = str(diff_file)
    result["diff_size"] = diff_size

    changed_files_file = run_path / "changed-files.txt"
    if changed_files_file.exists():
        changed_files = [line for line in changed_files_file.read_text().splitlines() if line.strip()]
    else:
        changed_files = []
    # Fallback: parse final.diff if changed-files.txt is empty
    if not changed_files and diff_file.exists():
        diff_text = diff_file.read_text()
        if diff_text.strip():
            changed_files = sorted(parse_diff_file_paths(diff_text))
    result["changed_files"] = changed_files
    result["changed_files_count"] = len(changed_files)

    validation_file = run_path / "validation-results.json"
    if validation_file.exists():
        try:
            with open(validation_file) as f:
                result["validation"] = json.load(f)
        except Exception:
            pass

    # --- Timestamps & duration ---
    # Priority: run-meta.json > transcript duration_ms > file mtime fallback
    meta_file = run_path / "run-meta.json"
    meta = {}
    if meta_file.exists():
        try:
            with open(meta_file) as f:
                meta = json.load(f)
        except Exception:
            pass

    duration_seconds = None

    if meta.get("start_time") and meta.get("end_time"):
        result["start_time"] = meta["start_time"]
        result["end_time"] = meta["end_time"]
        meta_start = parse_timestamp(meta["start_time"])
        meta_end = parse_timestamp(meta["end_time"])
        if meta_start and meta_end:
            duration_seconds = (meta_end - meta_start).total_seconds()

    # If no duration from run-meta, try transcript duration_ms
    if duration_seconds is None:
        dur_ms = transcript_meta.get("duration_ms")
        if dur_ms is not None:
            duration_seconds = dur_ms / 1000.0
            # Compute approximate start/end from file mtime and duration
            transcript_file = run_path / "transcript.json"
            if transcript_file.exists():
                end_dt = datetime.fromtimestamp(transcript_file.stat().st_mtime, UTC)
                start_dt = end_dt - timedelta(seconds=duration_seconds)
                result["start_time"] = start_dt.isoformat()
                result["end_time"] = end_dt.isoformat()

    if duration_seconds is not None:
        result["duration_seconds"] = duration_seconds
    elif "start_time" not in result or "end_time" not in result:
        # Fallback: file mtime range
        timestamps = []
        for file_name in ["transcript.json", "final.diff", "validation-results.json"]:
            file_path = run_path / file_name
            if file_path.exists():
                timestamps.append(datetime.fromtimestamp(file_path.stat().st_mtime, UTC))
        if timestamps:
            result["start_time"] = min(timestamps).isoformat()
            result["end_time"] = max(timestamps).isoformat()
        else:
            result.setdefault("start_time", "")
            result.setdefault("end_time", "")

    result["status"] = classify_run(
        result.get("exit_code", -1),
        result.get("diff_size", 0),
        result.get("validation")
    )
    return result


def load_existing_run_results(runs_dir: Path) -> List[Dict[str, Any]]:
    if not runs_dir.exists():
        return []

    run_results = []
    for run_path in sorted(runs_dir.glob("run-*")):
        if not run_path.is_dir():
            continue
        try:
            run_results.append(rebuild_run_result(run_path))
        except ValueError:
            continue
    return sorted(run_results, key=lambda item: item.get("run_id", 0))


def update_summary(exp_path: Path, runs_dir: Path, analysis_dir: Path) -> Dict[str, Any]:
    """Generate summary JSON from all runs currently present under runs_dir."""
    analysis_dir.mkdir(parents=True, exist_ok=True)
    run_results = load_existing_run_results(runs_dir)

    successful_runs = [r for r in run_results if r.get("status") in SUCCESS_STATUSES]
    failed_runs = [r for r in run_results if r.get("status") not in SUCCESS_STATUSES]

    status_groups: Dict[str, List[Dict[str, Any]]] = {}
    for r in run_results:
        status = r.get("status", "unknown")
        status_groups.setdefault(status, []).append(r)

    files_changed_counts = [r.get("changed_files_count", 0) for r in run_results]
    diff_sizes = [r.get("diff_size", 0) for r in run_results]

    summary: Dict[str, Any] = {
        "experiment": exp_path.name,
        "runs_directory": str(runs_dir),
        "analysis_directory": str(analysis_dir),
        "generated_at": utc_now_iso(),
        "total_runs": len(run_results),
        "successful_runs": len(successful_runs),
        "failed_runs": len(failed_runs),
        "status_breakdown": {status: len(items) for status, items in sorted(status_groups.items())},
        "run_statuses": [
            {
                "run_id": r.get("run_id", i + 1),
                "status": r.get("status", "unknown"),
                "exit_code": r.get("exit_code", -1),
                "start_time": r.get("start_time", ""),
                "end_time": r.get("end_time", ""),
                "changed_files_count": r.get("changed_files_count", 0),
                "diff_size": r.get("diff_size", 0),
                "error": r.get("error", "")
            }
            for i, r in enumerate(run_results)
        ],
        "statistics": {
            "files_changed": {
                "min": min(files_changed_counts) if files_changed_counts else 0,
                "max": max(files_changed_counts) if files_changed_counts else 0,
                "avg": sum(files_changed_counts) / len(files_changed_counts) if files_changed_counts else 0,
                "range": (max(files_changed_counts) - min(files_changed_counts)) if files_changed_counts else 0,
            },
            "diff_size_bytes": {
                "min": min(diff_sizes) if diff_sizes else 0,
                "max": max(diff_sizes) if diff_sizes else 0,
                "avg": sum(diff_sizes) / len(diff_sizes) if diff_sizes else 0,
                "range": (max(diff_sizes) - min(diff_sizes)) if diff_sizes else 0,
            }
        }
    }

    validation_results = []
    duration_values = []
    token_usage_values = []

    for r in run_results:
        # Priority: duration_seconds from rebuild > computed from timestamps
        ds = r.get("duration_seconds")
        if ds is not None:
            duration_values.append(ds)
        else:
            start = parse_timestamp(r.get("start_time", ""))
            end = parse_timestamp(r.get("end_time", ""))
            if start and end:
                duration_values.append((end - start).total_seconds())

        run_path = runs_dir / f"run-{r.get('run_id', 0):03d}"
        token_usage = extract_token_usage(run_path)
        token_usage_values.append(token_usage)

        if "validation" in r:
            val = r["validation"]
            correctness = val.get("correctness", {})
            validation_results.append({
                "run_id": r.get("run_id", "unknown"),
                "functional": correctness.get("functional", 0),
                "regression": correctness.get("regression", 0),
                "overall": correctness.get("overall", 0),
                "test_file_created": val.get("test_file_check", {}).get("test_file_created", False)
            })

    if duration_values:
        summary["durations_seconds"] = {
            "min": min(duration_values),
            "max": max(duration_values),
            "avg": sum(duration_values) / len(duration_values),
            "range": max(duration_values) - min(duration_values),
        }

    if token_usage_values:
        summary["tokens"] = {
            "average_input_tokens": sum(v["input_tokens"] for v in token_usage_values) / len(token_usage_values),
            "average_output_tokens": sum(v["output_tokens"] for v in token_usage_values) / len(token_usage_values),
            "average_cache_read_input_tokens": sum(v["cache_read_input_tokens"] for v in token_usage_values) / len(token_usage_values),
            "average_total_tokens": sum(v["total_tokens"] for v in token_usage_values) / len(token_usage_values),
        }

    if validation_results:
        # Filter out None scores (from F8: correctness is None when no test results)
        functional_scores = [v["functional"] for v in validation_results if v["functional"] is not None]
        regression_scores = [v["regression"] for v in validation_results if v["regression"] is not None]
        overall_scores = [v["overall"] for v in validation_results if v["overall"] is not None]

        summary["validation"] = {
            "total_validated": len(validation_results),
            "average_functional_score": sum(functional_scores) / len(functional_scores) if functional_scores else 0,
            "average_regression_score": sum(regression_scores) / len(regression_scores) if regression_scores else 0,
            "average_overall_score": sum(overall_scores) / len(overall_scores) if overall_scores else 0,
            "perfect_runs": len([s for s in overall_scores if s == 1.0]),
            "test_file_created_count": len([v for v in validation_results if v["test_file_created"]]),
            "per_run": validation_results
        }

    summary_file = analysis_dir / "runs-summary.json"
    with open(summary_file, "w") as f:
        json.dump(summary, f, indent=2)

    readable_file = analysis_dir / "summary.txt"
    with open(readable_file, "w") as f:
        f.write(f"Experiment: {exp_path.name}\n")
        f.write(f"Runs directory: {runs_dir}\n")
        f.write(f"Generated: {summary['generated_at']}\n")
        f.write(f"Total runs: {summary['total_runs']}\n")
        f.write(f"Successful: {summary['successful_runs']}\n")
        f.write(f"Failed: {summary['failed_runs']}\n")

        f.write("\nStatus Breakdown:\n")
        for status, count in summary["status_breakdown"].items():
            f.write(f"  {status}: {count}\n")

        f.write("\nFiles Changed Statistics:\n")
        f.write(f"  Min: {summary['statistics']['files_changed']['min']}\n")
        f.write(f"  Max: {summary['statistics']['files_changed']['max']}\n")
        f.write(f"  Avg: {summary['statistics']['files_changed']['avg']:.2f}\n")
        f.write(f"  Range: {summary['statistics']['files_changed']['range']}\n")

        f.write("\nDiff Size Statistics (bytes):\n")
        f.write(f"  Min: {summary['statistics']['diff_size_bytes']['min']}\n")
        f.write(f"  Max: {summary['statistics']['diff_size_bytes']['max']}\n")
        f.write(f"  Avg: {summary['statistics']['diff_size_bytes']['avg']:.2f}\n")
        f.write(f"  Range: {summary['statistics']['diff_size_bytes']['range']}\n")

        if "durations_seconds" in summary:
            f.write("\nDuration Statistics (seconds):\n")
            f.write(f"  Min: {summary['durations_seconds']['min']:.2f}\n")
            f.write(f"  Max: {summary['durations_seconds']['max']:.2f}\n")
            f.write(f"  Avg: {summary['durations_seconds']['avg']:.2f}\n")
            f.write(f"  Range: {summary['durations_seconds']['range']:.2f}\n")

        f.write("\n" + "=" * 70 + "\n")
        f.write("RUN DETAILS\n")
        f.write("=" * 70 + "\n\n")

        for r in run_results:
            run_id = r.get("run_id", 0)
            status = r.get("status", "unknown")
            run_path = runs_dir / f"run-{run_id:03d}"

            duration_str = "N/A"
            ds = r.get("duration_seconds")
            if ds is not None:
                duration_str = f"{ds:.1f}s"
            else:
                start_str = r.get("start_time", "")
                end_str = r.get("end_time", "")
                start = parse_timestamp(start_str)
                end = parse_timestamp(end_str)
                if start and end:
                    duration_str = f"{(end - start).total_seconds():.1f}s"

            ftp_str = "N/A"
            ptp_str = "N/A"
            val = r.get("validation")
            if val:
                test_results = val.get("test_results", {})
                ftp_results = test_results.get("fail_to_pass_results", {})
                ptp_results = test_results.get("pass_to_pass_results", {})
                if ftp_results:
                    ftp_passed = sum(1 for v in ftp_results.values() if v == "PASSED")
                    ftp_total = len(ftp_results)
                    ftp_pct = int(100 * ftp_passed / ftp_total)
                    ftp_str = f"{ftp_passed}/{ftp_total} ({ftp_pct}%)"
                if ptp_results:
                    ptp_passed = sum(1 for v in ptp_results.values() if v == "PASSED")
                    ptp_total = len(ptp_results)
                    ptp_pct = int(100 * ptp_passed / ptp_total)
                    ptp_str = f"{ptp_passed}/{ptp_total} ({ptp_pct}%)"

            token_usage = extract_token_usage(run_path)

            f.write(
                f"Run {run_id:03d}: status={status}, duration={duration_str}, "
                f"FAIL_TO_PASS={ftp_str}, PASS_TO_PASS={ptp_str}, "
                f"input_tokens={token_usage['input_tokens']}, "
                f"output_tokens={token_usage['output_tokens']}, "
                f"cache_read_input_tokens={token_usage['cache_read_input_tokens']}, "
                f"tokens={token_usage['total_tokens']}\n"
            )

        if validation_results:
            f.write("\n" + "=" * 70 + "\n")
            f.write("VALIDATION SUMMARY\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Total validated runs: {len(validation_results)}\n")
            f.write(f"Average functional score: {summary['validation']['average_functional_score']:.2%}\n")
            f.write(f"Average regression score: {summary['validation']['average_regression_score']:.2%}\n")
            f.write(f"Average overall score: {summary['validation']['average_overall_score']:.2%}\n")
            f.write(f"Perfect runs (100% overall): {summary['validation']['perfect_runs']}\n")
            f.write(f"Runs with test file created: {summary['validation']['test_file_created_count']}\n")

    print(f"\n✅ Summary saved to: {summary_file}")
    print(f"📄 Human-readable summary: {readable_file}")
    return summary


def revalidate_runs(
    runs_dir: Path,
    source_repo: Path,
    task_metadata: Dict[str, Any],
    validation_image: str,
    base_commit: str = "",
) -> None:
    """Re-run validation for all existing runs without re-running Claude."""
    run_dirs = sorted(d for d in runs_dir.glob("run-*") if d.is_dir())
    if not run_dirs:
        print("No runs found to revalidate.")
        return

    print(f"=== Revalidating {len(run_dirs)} runs ===")
    for run_path in run_dirs:
        diff_file = run_path / "final.diff"
        if not diff_file.exists():
            print(f"  ⚠️  {run_path.name}: no final.diff, skipping")
            continue

        diff_content = diff_file.read_text()
        if not diff_content.strip():
            print(f"  ⚠️  {run_path.name}: empty diff, skipping")
            continue

        print(f"\n>>> Revalidating {run_path.name}...")
        run_validation_official(
            run_path,
            task_metadata,
            diff_content,
            validation_image,
        )

    print(f"\n✅ Revalidation complete for {len(run_dirs)} runs")


def main():
    args = parse_args()
    exp_path = Path(args.experiment_dir).resolve()

    if not exp_path.exists():
        print(f"Error: Experiment directory not found: {exp_path}")
        sys.exit(1)

    plan_path = resolve_path(args.plan_file, exp_path / "plan.md")
    runs_dir = resolve_path(args.runs_dir, exp_path / "runs")
    analysis_dir = resolve_path(args.analysis_dir, exp_path / "analysis")

    validation_image = args.validation_image or build_validation_image_path(exp_path)
    if not args.dry_run and not validation_image:
        print("Error: validation image is required. Pass --validation-image or create env-image.txt first.")
        sys.exit(1)

    # The unified image serves as both executor (Claude Code) and validator (run_instance)
    executor_image = validation_image

    task_metadata = load_task_metadata(exp_path)
    base_commit = load_base_commit(exp_path)

    # --revalidate mode: re-run validation only, then rebuild summary
    if args.revalidate:
        if not validation_image:
            print("Error: --validation-image is required for --revalidate mode.")
            sys.exit(1)
        revalidate_runs(runs_dir, exp_path / "repo", task_metadata, validation_image, base_commit)
        summary = update_summary(exp_path, runs_dir, analysis_dir)
        print("\n=== Revalidation Complete ===")
        print(f"Summary: {analysis_dir / 'runs-summary.json'}")
        return

    if not plan_path.exists():
        print(f"Error: Plan file not found: {plan_path}")
        sys.exit(1)

    print("=== Experiment Execution ===")
    print(f"Experiment: {exp_path.name}")
    print(f"Plan file: {plan_path}")
    print(f"Runs directory: {runs_dir}")
    print(f"Analysis directory: {analysis_dir}")
    print(f"Runs: {args.start} to {args.start + args.runs - 1}")
    print(f"Dry run: {args.dry_run}")
    print(f"Permission mode: {args.claude_permission_mode}")
    print(f"Image: {validation_image or 'N/A (dry run)'}")
    print("============================")

    if not args.dry_run:
        try:
            ensure_run_range_available(runs_dir, args.start, args.runs)
        except FileExistsError as e:
            print(f"Error: {e}")
            sys.exit(1)

    executed_runs = []

    for i in range(args.runs):
        run_num = args.start + i
        print(f"\n>>> Run {run_num:03d} starting...")

        if args.dry_run:
            run_path = runs_dir / f"run-{run_num:03d}"
            work_dir = run_path / "work"
        else:
            run_path = setup_run_directory(runs_dir, run_num)
            work_dir = prepare_working_copy(exp_path, run_path)
        prompt = create_execution_prompt(plan_path)

        result = run_claude_code(
            work_dir, prompt, args.dry_run,
            claude_permission_mode=args.claude_permission_mode,
            executor_image=executor_image,
            docker_cpus=args.docker_cpus,
            docker_memory=args.docker_memory,
        )
        result["run_id"] = run_num
        if validation_image:
            result["validation_image"] = validation_image

        # Persist execution metadata for accurate rebuild
        if not args.dry_run:
            meta_file = run_path / "run-meta.json"
            meta_file.write_text(json.dumps({
                "start_time": result.get("start_time", ""),
                "end_time": result.get("end_time", ""),
                "exit_code": result.get("exit_code", -1),
            }, indent=2))

        if not args.dry_run:
            result.update(collect_results(run_path, work_dir))

            if task_metadata and task_metadata.get("test_patch"):
                diff_file = run_path / "final.diff"
                diff_content = diff_file.read_text() if diff_file.exists() else ""

                if diff_content.strip():
                    validation_result = run_validation_official(
                        run_path,
                        task_metadata,
                        diff_content,
                        validation_image,
                    )
                    result["validation"] = validation_result
                else:
                    print("  ⚠️  No diff content found, skipping validation")

            result["status"] = classify_run(
                result.get("exit_code", -1),
                result.get("diff_size", 0),
                result.get("validation")
            )

        executed_runs.append(result)

        if not args.dry_run and not args.keep_work:
            for dir_name in ["work", "validation"]:
                dir_path = run_path / dir_name
                if dir_path.exists():
                    try:
                        shutil.rmtree(dir_path)
                        print(f"  🧹 Cleaned up {dir_name}/")
                    except Exception as e:
                        print(f"  ⚠️  Failed to delete {dir_name}/: {e}")
        elif not args.dry_run and args.keep_work:
            print("  📂 Kept work/ and validation/ (--keep-work flag set)")

        print(f"<<< Run {run_num:03d} completed")

        if not args.dry_run:
            time.sleep(2)

    if not args.dry_run:
        summary = update_summary(exp_path, runs_dir, analysis_dir)
        print("\n=== Experiment Complete ===")
        print(f"Executed runs this invocation: {len(executed_runs)}")
        print(f"Total runs summarized: {summary['total_runs']}")
        print(f"Summary: {analysis_dir / 'runs-summary.json'}")
    else:
        print("\n=== Experiment Complete ===")
        print(f"Total runs: {len(executed_runs)}")
        print(f"Summary: {analysis_dir / 'runs-summary.json'}")


if __name__ == "__main__":
    main()
