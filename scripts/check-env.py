#!/usr/bin/env python3
"""
Check Docker environment for experiment readiness.

Verifies the unified Docker image exists and the main package is importable.
If the image is missing, triggers build-env.py --use-official-base.

Usage: python scripts/check-env.py <experiment_dir> --image IMAGE
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Check Docker validation environment")
    parser.add_argument("experiment_dir", help="Path to experiment directory")
    parser.add_argument("--image", required=True, help="Docker image to check")
    return parser.parse_args()


def load_task(exp_path: Path) -> dict:
    task_file = exp_path / "task_full.json"
    if not task_file.exists():
        raise FileNotFoundError(f"task_full.json not found: {task_file}")
    return json.loads(task_file.read_text())


def infer_main_package(repo: str) -> str:
    """Infer the main importable package name from the repo path."""
    mappings = {
        "django/django": "django",
        "pylint-dev/pylint": "pylint",
        "pytest-dev/pytest": "pytest",
        "scikit-learn/scikit-learn": "sklearn",
        "sympy/sympy": "sympy",
        "matplotlib/matplotlib": "matplotlib",
        "sphinx-doc/sphinx": "sphinx",
        "flask-cli/flask": "flask",
        "psf/requests": "requests",
        "astropy/astropy": "astropy",
    }
    return mappings.get(repo, repo.split("/")[-1].replace("-", "_"))


def main():
    args = parse_args()
    exp_path = Path(args.experiment_dir).resolve()
    if not exp_path.exists():
        print(f"Error: experiment directory not found: {exp_path}")
        sys.exit(1)

    image_tag = args.image

    # 1. Check image exists
    result = subprocess.run(
        ["docker", "image", "inspect", image_tag],
        capture_output=True, text=True,
    )
    image_exists = result.returncode == 0

    if not image_exists:
        print(f"Image not found: {image_tag}")
        print("Building with --use-official-base...")
        build_result = subprocess.run(
            [sys.executable, "scripts/build-env.py", str(exp_path), "--use-official-base"],
        )
        if build_result.returncode != 0:
            print("Image build failed!")
            sys.exit(1)

        # Re-check
        result = subprocess.run(
            ["docker", "image", "inspect", image_tag],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"Image still not found after build: {image_tag}")
            sys.exit(1)

    # 2. Smoke test: import the main package inside the container
    task = load_task(exp_path)
    repo = task.get("repo", "")
    package = infer_main_package(repo)

    print(f"  Running smoke test: import {package}")
    # Use conda testbed env if available (official SWE-bench images)
    smoke_result = subprocess.run(
        ["docker", "run", "--rm", image_tag,
         "bash", "-c",
         f"source /opt/miniconda3/etc/profile.d/conda.sh 2>/dev/null && conda activate testbed 2>/dev/null; python -c \"import {package}; print('{package} OK')\""],
        capture_output=True, text=True, timeout=120,
    )

    smoke_output = (smoke_result.stdout + smoke_result.stderr).strip()
    smoke_passed = smoke_result.returncode == 0

    # 3. Write result
    output = {
        "experiment": exp_path.name,
        "image": image_tag,
        "image_exists": True,
        "smoke_test": "pass" if smoke_passed else "fail",
        "smoke_test_output": smoke_output[-500:],  # Last 500 chars
    }

    out_file = exp_path / "env-check.json"
    out_file.write_text(json.dumps(output, indent=2))
    print(f"Saved environment check to {out_file}")

    if smoke_passed:
        print(f"Environment status: pass")
    else:
        print(f"Environment status: FAIL")
        print(f"  Output: {smoke_output[-200:]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
