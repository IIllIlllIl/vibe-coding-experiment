#!/usr/bin/env python3
"""
Experiment execution script for Claude Code variability study.
Usage: python scripts/run-experiment.py <experiment_dir> [--runs N] [--start N] [--dry-run]
"""

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


SUCCESS_STATUSES = {"success", "success_timeout", "success_with_error"}


def detect_test_framework(task_metadata: Dict[str, Any], work_dir: Optional[Path] = None) -> str:
    """Detect whether the project uses Django test runner or pytest.

    Returns "django" or "pytest".
    """
    repo = task_metadata.get("repo", "")
    # Django always uses its own test runner
    if "django" in repo.lower():
        return "django"

    # Check for conftest.py or pytest config in work_dir
    if work_dir and work_dir.exists():
        for marker in ["conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg"]:
            if (work_dir / marker).exists():
                if marker == "conftest.py":
                    return "pytest"
                try:
                    content = (work_dir / marker).read_text()
                    if "pytest" in content or "[tool:pytest]" in content or "[tool.pytest" in content:
                        return "pytest"
                except Exception:
                    pass

    # All non-Django repos in SWE-bench Verified use pytest
    return "pytest"


def build_docker_test_command(
    framework: str,
    fail_to_pass: List[str],
    pass_to_pass: List[str],
) -> str:
    """Build the test command string to run inside the Docker container."""
    all_tests = fail_to_pass + pass_to_pass

    if framework == "django":
        test_modules = set()
        for test in all_tests:
            match = re.match(r'\w+\s+\(([\w.]+)\.\w+\)', test)
            if match:
                test_modules.add(match.group(1))

        if not test_modules:
            return ""

        module_args = " ".join(shlex.quote(module) for module in sorted(test_modules))
        return (
            "python -m pip install --disable-pip-version-check -e . && "
            f"python tests/runtests.py -v 2 {module_args}"
        )

    # pytest: extract unique test file paths and run whole files, then match results from output
    if not all_tests:
        return ""

    test_files = set()
    for test in all_tests:
        parts = test.split("::")
        if parts:
            test_files.add(parts[0])
    file_args = " ".join(shlex.quote(f) for f in sorted(test_files))
    return (
        "python -m pip install --disable-pip-version-check -e . 2>/dev/null && "
        f"python -m pytest {file_args} -v --tb=short 2>&1"
    )


def parse_pytest_output(output: str, fail_to_pass: List[str], pass_to_pass: List[str]) -> Dict[str, Any]:
    """Parse pytest verbose output and match against expected test names."""
    passed_tests = set()
    failed_tests = set()

    # pytest -v output: "test/path/test_file.py::TestClass::test_method[param] PASSED [pct%]"
    # Some parametrized IDs contain spaces (e.g. "*1 xfailed*]"), so use lazy .+? up to status word
    pytest_pattern = re.compile(
        r'^(.+?)\s+(PASSED|FAILED|ERROR|XFAIL|XPASS)\s',
        re.MULTILINE,
    )
    for match in pytest_pattern.finditer(output):
        test_id = match.group(1)
        status = match.group(2)
        if status == "PASSED":
            passed_tests.add(test_id)
        else:
            failed_tests.add(test_id)

    return {
        "passed_tests": len(passed_tests),
        "failed_tests": len(failed_tests),
        "passed_set": passed_tests,
        "failed_set": failed_tests,
    }


def match_pytest_results(
    expected_tests: List[str],
    pytest_passed: set,
    pytest_failed: set,
    label: str,
) -> tuple:
    """Match expected test names against pytest output test IDs.

    pytest outputs full IDs like 'test_file.py::TestClass::test_method'.
    Expected names may be partial. We match by checking if the expected
    name's test function appears in the pytest ID.

    Returns (results_dict, success_bool).
    """
    results = {}
    success = True

    for test in expected_tests:
        # Try exact match first
        if test in pytest_passed:
            results[test] = "PASSED"
            print(f"   ✅ {test}: PASSED (expected to {label})")
            continue
        if test in pytest_failed:
            results[test] = "FAILED"
            success = False
            print(f"   ❌ {test}: FAILED (expected to {label})")
            continue

        # Try partial match: extract function name and match
        parts = test.split("::") if "::" in test else [test]
        func_name = parts[-1] if parts else test
        found = False
        for pytest_id in pytest_passed:
            if func_name in pytest_id or test in pytest_id:
                results[test] = "PASSED"
                print(f"   ✅ {test}: PASSED (expected to {label}, matched {pytest_id})")
                found = True
                break
        if found:
            continue
        for pytest_id in pytest_failed:
            if func_name in pytest_id or test in pytest_id:
                results[test] = "FAILED"
                success = False
                print(f"   ❌ {test}: FAILED (expected to {label}, matched {pytest_id})")
                found = True
                break
        if found:
            continue

        results[test] = "NOT_FOUND"
        success = False
        print(f"   ⚠️  {test}: NOT FOUND in test output")

    return results, success


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


def run_claude_code(work_dir: Path, prompt: str, dry_run: bool) -> Dict[str, Any]:
    """Execute Claude Code with the prompt and capture output."""
    start_time = utc_now_iso()

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

    try:
        result = subprocess.run(
            ["claude", "-p", "--permission-mode", "acceptEdits", "--output-format", "json"],
            cwd=work_dir,
            input=prompt,
            capture_output=True,
            text=True,
            timeout=3600
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
                "command": "claude -p --permission-mode acceptEdits --output-format json",
                "cwd": str(work_dir)
            })
        else:
            transcript_data = {
                "stdout": stdout_text,
                "stderr": result.stderr,
                "exit_code": result.returncode,
                "command": "claude -p --permission-mode acceptEdits --output-format json",
                "cwd": str(work_dir)
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

    except subprocess.TimeoutExpired as e:
        end_time = utc_now_iso()

        transcript_file = work_dir.parent / "transcript.json"
        transcript_data = {
            "stdout": e.stdout or "",
            "stderr": e.stderr or "",
            "exit_code": -1,
            "command": "claude -p --permission-mode acceptEdits --output-format json",
            "cwd": str(work_dir),
            "timeout": True
        }
        transcript_file.write_text(json.dumps(transcript_data, indent=2))

        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": end_time,
            "exit_code": -1,
            "status": "timeout",
            "transcript_file": str(transcript_file),
            "error": "Execution exceeded 1 hour timeout"
        }
    except FileNotFoundError:
        return {
            "run_id": None,
            "start_time": start_time,
            "end_time": utc_now_iso(),
            "exit_code": -1,
            "status": "failed",
            "error": "Claude Code not found. Please ensure 'claude' is installed and in PATH."
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

    changed_files_file = run_path / "changed-files.txt"
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            cwd=work_dir,
            capture_output=True,
            text=True,
            check=False
        )
        changed_files = [f for f in result.stdout.strip().split("\n") if f]
        changed_files_file.write_text("\n".join(changed_files))
        results["changed_files"] = changed_files
        results["changed_files_count"] = len(changed_files)
    except Exception as e:
        results["changed_files_error"] = str(e)
        results["changed_files_count"] = 0

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
    }


def _normalize_path(p: str) -> str:
    """Normalize a diff path: strip a/ b/ prefix and remove leading ./ """
    if p.startswith("a/") or p.startswith("b/"):
        p = p[2:]
    if p.startswith("./"):
        p = p[2:]
    return p


def parse_diff_file_paths(patch_content: str) -> set:
    """Extract file paths from a unified diff.

    Handles paths with spaces by splitting from the right on ' b/'.
    For renames, both old and new paths are included.
    All paths are normalized (strip a/ b/ prefix, remove leading ./).
    """
    paths = set()
    rename_re = re.compile(r'^rename (?:from|to) (.+)$')

    for line in patch_content.splitlines():
        if line.startswith("diff --git "):
            # "diff --git a/path/to/file b/path/to/file"
            # Split from right on " b/" to handle spaces in path
            rest = line[len("diff --git "):]
            b_idx = rest.rfind(" b/")
            if b_idx >= 0:
                path_a = rest[:b_idx]
                path_b = rest[b_idx + 1:]  # "b/path/to/file"
                paths.add(_normalize_path(path_a))
                paths.add(_normalize_path(path_b))
            continue
        m = rename_re.match(line)
        if m:
            paths.add(_normalize_path(m.group(1)))
    return paths


def filter_diff_excluding_paths(patch_content: str, exclude_paths: set) -> str:
    """Filter a unified diff, removing hunks for files in exclude_paths.

    Uses the same rfind strategy as parse_diff_file_paths to handle
    paths with spaces correctly.
    """
    filtered_lines: list[str] = []
    skip = False
    for line in patch_content.splitlines():
        if line.startswith("diff --git "):
            rest = line[len("diff --git "):]
            b_idx = rest.rfind(" b/")
            path = _normalize_path(rest[b_idx + 1:]) if b_idx >= 0 else ""
            skip = path in exclude_paths
        if not skip:
            filtered_lines.append(line)
    return "\n".join(filtered_lines)


def apply_git_patch(work_dir: Path, patch_content: str, patch_name: str = "test_patch") -> bool:
    """
    将 git patch 应用到验证目录。
    """
    if not patch_content or not patch_content.strip():
        print(f"⚠️  {patch_name} is empty, skipping")
        return True

    patch_file = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".diff", delete=False) as f:
            f.write(patch_content)
            patch_file = Path(f.name)

        check_result = subprocess.run(
            ["git", "apply", "--check", str(patch_file)],
            cwd=work_dir,
            capture_output=True,
            text=True
        )

        if check_result.returncode != 0:
            print(f"❌ {patch_name} check failed (exit code {check_result.returncode}):")
            print(check_result.stderr)
            return False

        apply_result = subprocess.run(
            ["git", "apply", str(patch_file)],
            cwd=work_dir,
            capture_output=True,
            text=True
        )

        if apply_result.returncode != 0:
            print(f"❌ {patch_name} apply failed (exit code {apply_result.returncode}):")
            print(apply_result.stderr)
            return False

        print(f"✅ Applied {patch_name} successfully")
        return True

    except Exception as e:
        print(f"❌ Failed to apply {patch_name}: {e}")
        return False

    finally:
        if patch_file and patch_file.exists():
            patch_file.unlink()


def run_tests_in_docker(
    work_dir: Path,
    fail_to_pass: List[str],
    pass_to_pass: List[str],
    image: str,
    timeout_seconds: int = 300,
    task_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run tests inside a fixed Docker validation image and parse results.

    Supports both Django and pytest frameworks automatically.
    """
    results: Dict[str, Any] = {
        "success": False,
        "fail_to_pass_results": {},
        "pass_to_pass_results": {},
        "total_tests": 0,
        "passed_tests": 0,
        "failed_tests": 0,
        "output": "",
        "image": image,
    }

    if not fail_to_pass and not pass_to_pass:
        print("⚠️  No test cases specified, skipping test run")
        results["success"] = True
        return results

    # Detect test framework
    framework = detect_test_framework(task_metadata or {}, work_dir)
    print(f"   Detected test framework: {framework}")

    container_cmd = build_docker_test_command(framework, fail_to_pass, pass_to_pass)
    if not container_cmd:
        print("⚠️  Could not build test command")
        results["output"] = "Could not build test command"
        return results

    # For pytest: test files are now passed directly in the command (no _test_ids.txt needed)

    cmd = [
        "docker", "run", "--rm",
        "-v", f"{work_dir.resolve()}:/workspace",
        "-w", "/workspace",
        image,
        "bash", "-lc", container_cmd,
    ]

    print("🧪 Running validation tests in Docker...")
    print(f"   Image: {image}")
    print(f"   Framework: {framework}")
    print(f"   Tests expected: {len(fail_to_pass) + len(pass_to_pass)}")

    try:
        process = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds
        )

        output = process.stdout + process.stderr
        results["output"] = output
        results["docker_command"] = cmd
        results["container_command"] = container_cmd
        results["exit_code"] = process.returncode
        results["framework"] = framework

        if framework == "django":
            # Django -v 2 output has two formats:
            #   single-line: test_name (module.class) ... ok
            #   multi-line:  test_name (module.class)\ndocstring ... ok
            # We find test names first, then pair each with its result.
            name_re = re.compile(
                r'^(\w+)\s+\(([\w.]+)\.(\w+)\)',
                re.MULTILINE,
            )
            result_re = re.compile(r'\.\.\.\s+(ok|FAIL|FAILED|ERROR)\s*$', re.MULTILINE)

            passed_tests = set()
            failed_tests = set()
            name_matches = list(name_re.finditer(output))
            for i, match in enumerate(name_matches):
                displayed_name = match.group(1)
                class_path = match.group(2)
                class_name = match.group(3)
                full_test_name = f"{displayed_name} ({class_path}.{class_name})"

                # Search for result between this match and the next
                search_start = match.end()
                search_end = name_matches[i + 1].start() if i + 1 < len(name_matches) else len(output)
                section = output[search_start:search_end]
                result_match = result_re.search(section)
                if result_match:
                    status = result_match.group(1)
                    if status == "ok":
                        passed_tests.add(full_test_name)
                    else:
                        failed_tests.add(full_test_name)

            results["total_tests"] = len(passed_tests) + len(failed_tests)
            results["passed_tests"] = len(passed_tests)
            results["failed_tests"] = len(failed_tests)

            ftp_success = True
            for test in fail_to_pass:
                if test in passed_tests:
                    results["fail_to_pass_results"][test] = "PASSED"
                    print(f"   ✅ {test}: PASSED (expected to pass)")
                elif test in failed_tests:
                    results["fail_to_pass_results"][test] = "FAILED"
                    ftp_success = False
                    print(f"   ❌ {test}: FAILED (expected to pass)")
                else:
                    results["fail_to_pass_results"][test] = "NOT_FOUND"
                    ftp_success = False
                    print(f"   ⚠️  {test}: NOT FOUND in test output")

            ptp_success = True
            for test in pass_to_pass:
                if test in passed_tests:
                    results["pass_to_pass_results"][test] = "PASSED"
                    print(f"   ✅ {test}: PASSED (expected to pass)")
                elif test in failed_tests:
                    results["pass_to_pass_results"][test] = "FAILED"
                    ptp_success = False
                    print(f"   ❌ {test}: FAILED (expected to pass)")
                else:
                    results["pass_to_pass_results"][test] = "NOT_FOUND"
                    ptp_success = False
                    print(f"   ⚠️  {test}: NOT FOUND in test output")

            results["success"] = ftp_success and ptp_success

        else:
            # pytest framework
            parsed = parse_pytest_output(output, fail_to_pass, pass_to_pass)
            results["total_tests"] = parsed["passed_tests"] + parsed["failed_tests"]
            results["passed_tests"] = parsed["passed_tests"]
            results["failed_tests"] = parsed["failed_tests"]

            ftp_results, ftp_success = match_pytest_results(
                fail_to_pass, parsed["passed_set"], parsed["failed_set"], "pass"
            )
            ptp_results, ptp_success = match_pytest_results(
                pass_to_pass, parsed["passed_set"], parsed["failed_set"], "pass"
            )
            results["fail_to_pass_results"] = ftp_results
            results["pass_to_pass_results"] = ptp_results
            results["success"] = ftp_success and ptp_success

        if results["success"]:
            print("✅ All tests passed as expected!")
        else:
            print("❌ Test validation failed")

        return results

    except subprocess.TimeoutExpired:
        print(f"❌ Tests timed out after {timeout_seconds} seconds")
        results["output"] = f"TIMEOUT after {timeout_seconds} seconds"
        return results
    except Exception as e:
        print(f"❌ Failed to run tests in Docker: {e}")
        results["output"] = str(e)
        return results


def check_test_file_created(work_dir: Path, test_patch: str) -> Dict[str, Any]:
    """Check if expected test file from test_patch was created."""
    if not test_patch:
        return {"test_file_expected": False}

    match = re.search(r'diff --git a/(.+?) b/(.+?)\s', test_patch)
    if not match:
        return {"test_file_expected": False}

    expected_file = match.group(2)
    expected_path = work_dir / expected_file

    return {
        "test_file_expected": True,
        "expected_test_file": expected_file,
        "test_file_created": expected_path.exists(),
        "test_file_size": expected_path.stat().st_size if expected_path.exists() else 0
    }


def run_validation(
    run_path: Path,
    source_repo: Path,
    task_metadata: Dict[str, Any],
    diff_content: str,
    validation_image: str,
    base_commit: str = ""
) -> Dict[str, Any]:
    """
    Run complete validation on Claude's implementation.

    Applies test_patch first, then final.diff with test_patch file paths
    excluded to prevent conflicts. All exclusions are recorded for audit.
    """
    validation_dir = run_path / "validation"

    if validation_dir.exists():
        shutil.rmtree(validation_dir)
    validation_dir.mkdir(parents=True)

    work_dir = validation_dir / "work"
    print(f"  Copying repository to {work_dir}...")
    shutil.copytree(source_repo, work_dir, dirs_exist_ok=True)

    if base_commit:
        subprocess.run(
            ["git", "reset", "--hard", base_commit],
            cwd=work_dir,
            capture_output=True
        )
        print(f"  Reset to base commit: {base_commit[:8]}...")

    test_patch = task_metadata.get("test_patch", "")

    # Parse file paths touched by test_patch
    test_patch_paths = parse_diff_file_paths(test_patch)

    # Step 1: Apply test_patch (SWE-bench test cases)
    test_patch_applied = apply_git_patch(work_dir, test_patch, "test_patch")

    # Step 2: Filter final.diff to exclude files touched by test_patch
    filtered_diff = filter_diff_excluding_paths(diff_content, test_patch_paths)
    excluded_paths = sorted(test_patch_paths & parse_diff_file_paths(diff_content))

    if excluded_paths:
        print(f"  📝 Excluded from final.diff (overlaps with test_patch): {excluded_paths}")

    claude_patch_applied = apply_git_patch(work_dir, filtered_diff, "final.diff")
    test_file_check = check_test_file_created(work_dir, test_patch)

    fail_to_pass = task_metadata.get("fail_to_pass", [])
    pass_to_pass = task_metadata.get("pass_to_pass", [])

    test_results = run_tests_in_docker(
        work_dir,
        fail_to_pass,
        pass_to_pass,
        image=validation_image,
        task_metadata=task_metadata,
    )

    functional_score = 0.0
    if test_results.get("fail_to_pass_results"):
        passed = sum(1 for v in test_results["fail_to_pass_results"].values() if v == "PASSED")
        total = len(test_results["fail_to_pass_results"])
        functional_score = passed / total if total > 0 else 1.0

    regression_score = 0.0
    if test_results.get("pass_to_pass_results"):
        passed = sum(1 for v in test_results["pass_to_pass_results"].values() if v == "PASSED")
        total = len(test_results["pass_to_pass_results"])
        regression_score = passed / total if total > 0 else 1.0

    validation_result = {
        "validation_directory": str(validation_dir),
        "validation_image": validation_image,
        "patches_applied": {
            "test_patch": test_patch_applied,
            "claude_patch": claude_patch_applied
        },
        "diff_exclusions": {
            "excluded_paths": excluded_paths,
            "reason": "overlaps with test_patch"
        },
        "test_file_check": test_file_check,
        "test_results": test_results,
        "correctness": {
            "functional": functional_score,
            "regression": regression_score,
            "overall": (functional_score + regression_score) / 2
        }
    }

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
    result["changed_files"] = changed_files
    result["changed_files_count"] = len(changed_files)

    validation_file = run_path / "validation-results.json"
    if validation_file.exists():
        try:
            with open(validation_file) as f:
                result["validation"] = json.load(f)
        except Exception:
            pass

    timestamps = []
    for file_name in ["transcript.json", "final.diff", "validation-results.json"]:
        file_path = run_path / file_name
        if file_path.exists():
            timestamps.append(datetime.fromtimestamp(file_path.stat().st_mtime, UTC))

    if timestamps:
        result["start_time"] = min(timestamps).isoformat()
        result["end_time"] = max(timestamps).isoformat()
    else:
        result["start_time"] = ""
        result["end_time"] = ""

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
        functional_scores = [v["functional"] for v in validation_results]
        regression_scores = [v["regression"] for v in validation_results]
        overall_scores = [v["overall"] for v in validation_results]

        summary["validation"] = {
            "total_validated": len(validation_results),
            "average_functional_score": sum(functional_scores) / len(functional_scores),
            "average_regression_score": sum(regression_scores) / len(regression_scores),
            "average_overall_score": sum(overall_scores) / len(overall_scores),
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
            start_str = r.get("start_time", "")
            end_str = r.get("end_time", "")
            start = parse_timestamp(start_str)
            end = parse_timestamp(end_str)
            if start and end:
                duration_str = f"{int((end - start).total_seconds())}s"

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
    print(f"Validation image: {validation_image or 'N/A (dry run)'}")
    print("============================")

    if not args.dry_run:
        try:
            ensure_run_range_available(runs_dir, args.start, args.runs)
        except FileExistsError as e:
            print(f"Error: {e}")
            sys.exit(1)

    task_metadata = load_task_metadata(exp_path)
    base_commit = load_base_commit(exp_path)
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

        result = run_claude_code(work_dir, prompt, args.dry_run)
        result["run_id"] = run_num
        if validation_image:
            result["validation_image"] = validation_image

        if not args.dry_run:
            result.update(collect_results(run_path, work_dir))

            if task_metadata and task_metadata.get("test_patch"):
                diff_file = run_path / "final.diff"
                diff_content = diff_file.read_text() if diff_file.exists() else ""

                if diff_content.strip():
                    validation_result = run_validation(
                        run_path,
                        exp_path / "repo",
                        task_metadata,
                        diff_content,
                        validation_image,
                        base_commit=base_commit,
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
