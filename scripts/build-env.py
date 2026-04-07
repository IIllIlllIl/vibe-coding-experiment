#!/usr/bin/env python3
"""
Build a reusable Docker validation image for an experiment.
Usage: python scripts/build-env.py <experiment_dir> [--tag TAG] [--with-claude]

With --with-claude, also builds a second image (claude-executor-<suffix>)
that extends the validation image with Node.js and Claude CLI installed.
"""

import argparse
import json
import shlex
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

CLAUDE_CODE_VERSION = "@anthropic-ai/claude-code@1.0.6"


def parse_args():
    parser = argparse.ArgumentParser(description="Build Docker validation image")
    parser.add_argument("experiment_dir", help="Path to experiment directory")
    parser.add_argument("--tag", help="Override Docker image tag")
    parser.add_argument(
        "--with-claude",
        action="store_true",
        help="Also build a Claude-enabled executor image on top of the validation image",
    )
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

    # pytest <7.0 assertion rewriter incompatible with Python 3.11+ AST
    if "pytest" in repo.lower() and not version.startswith("7.") and not version.startswith("8."):
        return "3.9"

    # sympy <1.1 uses collections.Mapping (removed in Python 3.10+)
    if "sympy" in repo.lower():
        # Only force 3.9 for old versions that use deprecated collections API
        if version and version.startswith(("0.", "1.0")):
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


def get_repo_pip_constraints(task: dict) -> list:
    """Return extra pip packages to pre-install for repos with known dependency issues."""
    repo = task.get("repo", "")
    constraints = []

    # scikit-learn 0.22.dev (2019) build needs:
    # - setuptools<71 for pkg_resources
    # - numpy<1.24 (np.float removed in 1.24+)
    # - Cython<3 for .pyx compilation
    # - scipy<1.12 (line_search_wolfe2 removed, numpy compat)
    if "scikit-learn" in repo:
        constraints.extend(["setuptools<71", "numpy<1.24", "Cython<3", "scipy<1.12"])

    # matplotlib 3.7.x C extensions incompatible with numpy 2.x
    # also needs pybind11 for --no-build-isolation
    if "matplotlib" in repo:
        constraints.extend(["numpy<2", "pybind11", "setuptools_scm"])

    return constraints


def build_dockerfile(python_version: str, test_framework: str = "pytest", extra_pip: list = None) -> str:
    pytest_install = ""
    if test_framework == "pytest":
        pytest_install = " && python -m pip install pytest"

    extra_install = ""
    if extra_pip:
        packages = " ".join(shlex.quote(p) for p in extra_pip)
        extra_install = f" && python -m pip install {packages}"

    return f'''FROM python:{python_version}-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CFLAGS="-Wno-error=incompatible-pointer-types -Wno-error=int-conversion"

RUN apt-get update && apt-get install -y --no-install-recommends \
    {' '.join(APT_PACKAGES)} \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/repo
COPY repo /opt/repo
RUN python -m pip install --upgrade pip setuptools wheel{pytest_install}{extra_install} && \
    (python -m pip install -e . || python -m pip install --no-build-isolation -e . || python -m pip install . || true) && \
    if [ -f tests/requirements/py3.txt ]; then python -m pip install -r tests/requirements/py3.txt; fi

WORKDIR /workspace
CMD ["bash"]
'''


def derive_executor_tag(validation_tag: str) -> str:
    """Derive the claude-executor tag from the validation tag.

    swe-env:django__django-11951 -> claude-executor:django__django-11951
    """
    suffix = validation_tag.split(":", 1)[-1] if ":" in validation_tag else validation_tag
    return f"claude-executor:{suffix}"


def build_claude_dockerfile(validation_tag: str) -> str:
    """Dockerfile that layers Node.js + Claude CLI on top of the validation image."""
    return f'''FROM {validation_tag}

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g {CLAUDE_CODE_VERSION}

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
    extra_pip = get_repo_pip_constraints(task)

    print(f"  Python version: {python_version}")
    print(f"  Test framework: {test_framework}")
    if extra_pip:
        print(f"  Extra pip constraints: {extra_pip}")

    dockerfile_content = build_dockerfile(python_version, test_framework, extra_pip=extra_pip)

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

    # Build Claude-enabled executor image if requested
    if args.with_claude:
        executor_tag = derive_executor_tag(image_tag)
        print(f"\nBuilding Claude executor image: {executor_tag}")
        executor_dockerfile = build_claude_dockerfile(image_tag)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            dockerfile_path = tmp_path / "Dockerfile"
            dockerfile_path.write_text(executor_dockerfile)

            subprocess.run(
                ["docker", "build", "-t", executor_tag, str(tmp_path)],
                check=True,
            )

        executor_file = exp_path / "claude-executor-image.txt"
        executor_file.write_text(executor_tag + "\n")
        print(f"Saved executor image tag to {executor_file}")
        print(executor_tag)


if __name__ == "__main__":
    main()
