#!/usr/bin/env python3
"""
Build a reusable Docker validation image for an experiment.
Usage: python scripts/build-env.py <experiment_dir> [--tag TAG]
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

APT_PACKAGES = [
    "build-essential",
    "git",
    "libffi-dev",
    "libssl-dev",
    "libjpeg-dev",
    "zlib1g-dev",
    "libmemcached-dev",
    "libsasl2-dev",
]


def parse_args():
    parser = argparse.ArgumentParser(description="Build Docker validation image")
    parser.add_argument("experiment_dir", help="Path to experiment directory")
    parser.add_argument("--tag", help="Override Docker image tag")
    return parser.parse_args()


def load_task(exp_path: Path) -> dict:
    task_file = exp_path / "task_full.json"
    if not task_file.exists():
        raise FileNotFoundError(f"task_full.json not found: {task_file}")
    return json.loads(task_file.read_text())


def derive_image_tag(exp_path: Path, task: dict) -> str:
    if task.get("instance_id"):
        suffix = task["instance_id"].replace("/", "-").replace("__", "-")
    else:
        suffix = exp_path.name.replace("_", "-")
    return f"swe-env:{suffix}"


def detect_python_version(task: dict) -> str:
    """Detect appropriate Python version based on repo and version metadata."""
    version = str(task.get("version", "")).strip()
    repo = task.get("repo", "")

    # requests 2.x uses collections.MutableMapping (removed in 3.10+)
    if "requests" in repo and version.startswith("2."):
        return "3.9"

    # Django <3.2 needs older Python
    if "django" in repo.lower():
        if version.startswith("3.0") or version.startswith("3.1"):
            return "3.9"
        if version.startswith("2."):
            return "3.9"
        return "3.11"

    if version.startswith("2."):
        return "3.10"
    return "3.11"


def detect_test_framework_for_build(task: dict) -> str:
    """Detect test framework from task metadata. Returns 'django' or 'pytest'."""
    repo = task.get("repo", "")
    if "django" in repo.lower():
        return "django"
    return "pytest"


def build_dockerfile(python_version: str, test_framework: str = "pytest") -> str:
    pytest_install = ""
    if test_framework == "pytest":
        pytest_install = " && python -m pip install pytest"

    return f'''FROM python:{python_version}-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/repo

RUN apt-get update && apt-get install -y --no-install-recommends \
    {' '.join(APT_PACKAGES)} \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/repo
COPY repo /opt/repo
RUN python -m pip install --upgrade pip setuptools wheel{pytest_install} && \
    (python -m pip install -e . || python -m pip install --no-build-isolation -e . || python -m pip install . || true) && \
    if [ -f tests/requirements/py3.txt ]; then python -m pip install -r tests/requirements/py3.txt; fi

WORKDIR /workspace
CMD ["bash"]
'''


def main():
    args = parse_args()
    exp_path = Path(args.experiment_dir).resolve()
    if not exp_path.exists():
        print(f"Error: experiment directory not found: {exp_path}")
        sys.exit(1)

    task = load_task(exp_path)
    image_tag = args.tag or derive_image_tag(exp_path, task)
    python_version = detect_python_version(task)
    test_framework = detect_test_framework_for_build(task)

    print(f"  Python version: {python_version}")
    print(f"  Test framework: {test_framework}")

    dockerfile_content = build_dockerfile(python_version, test_framework)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        dockerfile_path = tmp_path / "Dockerfile"
        dockerfile_path.write_text(dockerfile_content)

        context_repo = tmp_path / "repo"
        shutil.copytree((exp_path / "repo").resolve(), context_repo)

        print(f"Building Docker image: {image_tag}")
        subprocess.run(
            ["docker", "build", "-t", image_tag, str(tmp_path)],
            check=True,
        )

    image_file = exp_path / "env-image.txt"
    image_file.write_text(image_tag + "\n")
    print(f"Saved image tag to {image_file}")
    print(image_tag)


if __name__ == "__main__":
    main()
