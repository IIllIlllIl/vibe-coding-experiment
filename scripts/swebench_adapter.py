"""
Thin adapter for SWE-bench evaluation utilities.

Extracts standalone log parser functions and evaluation logic from the vendored
swebench package without triggering its deep dependency chain. Only imports
the pure-Python parser file (which only needs `re`) and the simple enum constants.
"""

import importlib.util
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

_SWEBENCH_ROOT = Path(__file__).resolve().parent.parent / "datasets" / "swe-bench"

# File extensions that are NOT test files (from swebench.harness.constants)
NON_TEST_EXTS = [
    ".json", ".png", "csv", ".txt", ".md", ".jpg", ".jpeg",
    ".pkl", ".yml", ".yaml", ".toml",
]


# --- Minimal TestStatus (avoids importing full swebench.harness.constants) ---

class _TestStatusValue:
    """String enum value that also has a .value attribute (returns itself)."""
    def __init__(self, value: str):
        self.value = value
    def __repr__(self):
        return self.value
    def __eq__(self, other):
        if isinstance(other, _TestStatusValue):
            return self.value == other.value
        return self.value == other
    def __hash__(self):
        return hash(self.value)


class _TestStatusMeta(type):
    """Metaclass that makes TestStatus iterable over its status values."""
    def __iter__(cls):
        return iter([cls.PASSED, cls.FAILED, cls.SKIPPED, cls.ERROR, cls.XFAIL])


class TestStatus(metaclass=_TestStatusMeta):
    PASSED = _TestStatusValue("PASSED")
    FAILED = _TestStatusValue("FAILED")
    SKIPPED = _TestStatusValue("SKIPPED")
    ERROR = _TestStatusValue("ERROR")
    XFAIL = _TestStatusValue("XFAIL")


# --- Lazy-loaded parser registry ---

_parsers_loaded = False
_MAP_REPO_TO_PARSER_PY: Dict[str, Callable] = {}


def _load_parsers():
    """Load parser functions from the vendored swebench log_parsers/python.py."""
    global _parsers_loaded, _MAP_REPO_TO_PARSER_PY
    if _parsers_loaded:
        return

    parser_path = _SWEBENCH_ROOT / "swebench" / "harness" / "log_parsers" / "python.py"
    if not parser_path.exists():
        raise FileNotFoundError(
            f"SWE-bench parser file not found: {parser_path}. "
            "Ensure datasets/swe-bench/ is populated."
        )

    # Read the source and exec it in a namespace that provides TestStatus and re
    source = parser_path.read_text()

    # The parser file uses TestSpec in type annotations (evaluated at runtime in
    # Python <3.10 or when not using `from __future__ import annotations`).
    # We provide a stub class.
    namespace = {
        "re": re,
        "TestStatus": TestStatus,
        "TestSpec": type("TestSpec", (), {}),  # Stub: parsers don't use it
    }

    # Stub out the TestSpec import
    _stub_spec = importlib.util.spec_from_file_location(
        "swebench.harness.test_spec.test_spec",
        str(_SWEBENCH_ROOT / "swebench" / "harness" / "test_spec" / "test_spec.py"),
    )
    # We don't actually need TestSpec — just make the import not crash

    # Replace the import lines so they don't trigger the full dependency chain
    source_modified = source.replace(
        "from swebench.harness.constants import TestStatus",
        "# TestStatus provided by adapter",
    ).replace(
        "from swebench.harness.test_spec.test_spec import TestSpec",
        "# TestSpec stub: not needed for parsing",
    )

    exec(compile(source_modified, str(parser_path), "exec"), namespace)

    # Extract the MAP_REPO_TO_PARSER_PY dict from the namespace
    _MAP_REPO_TO_PARSER_PY = namespace.get("MAP_REPO_TO_PARSER_PY", {})
    _parsers_loaded = True


# --- Public API ---

def get_parser_for_repo(repo: str) -> Optional[Callable]:
    """Return the official SWE-bench log parser for a given repo, or None."""
    _load_parsers()
    return _MAP_REPO_TO_PARSER_PY.get(repo)


def parse_test_output(repo: str, log_output: str) -> Dict[str, str]:
    """Parse test output using the official repo-specific parser.

    Returns a status_map: dict mapping test_name -> status string.
    """
    _load_parsers()
    parser = _MAP_REPO_TO_PARSER_PY.get(repo)
    if parser is None:
        raise ValueError(
            f"No official SWE-bench parser for repo '{repo}'. "
            f"Supported repos: {sorted(_MAP_REPO_TO_PARSER_PY.keys())}"
        )
    # Parser signature: (log: str, test_spec) -> dict
    # We pass None for test_spec — parsers only use it for type checking
    return parser(log_output, None)


def test_passed(case: str, status_map: Dict[str, str]) -> bool:
    """Check if a test case passed (exact match, SWE-bench semantics)."""
    return case in status_map and status_map[case] in [
        TestStatus.PASSED, TestStatus.XFAIL,
    ]


def test_failed(case: str, status_map: Dict[str, str]) -> bool:
    """Check if a test case failed (exact match, SWE-bench semantics).

    Note: If a test name is NOT in status_map, it counts as failed.
    """
    return case not in status_map or status_map[case] in [
        TestStatus.FAILED, TestStatus.ERROR,
    ]


def eval_test_results(
    status_map: Dict[str, str],
    fail_to_pass: List[str],
    pass_to_pass: List[str],
) -> Dict[str, Any]:
    """Evaluate test results using SWE-bench's exact matching logic."""
    ftp_results = {}
    ftp_success = True
    for test in fail_to_pass:
        if test_passed(test, status_map):
            ftp_results[test] = "PASSED"
        elif test_failed(test, status_map):
            ftp_results[test] = status_map.get(test, "FAILED")
            ftp_success = False
        else:
            ftp_results[test] = status_map.get(test, "NOT_FOUND")
            ftp_success = False

    ptp_results = {}
    ptp_success = True
    for test in pass_to_pass:
        if test_passed(test, status_map):
            ptp_results[test] = "PASSED"
        elif test_failed(test, status_map):
            ptp_results[test] = status_map.get(test, "FAILED")
            ptp_success = False
        else:
            ptp_results[test] = status_map.get(test, "NOT_FOUND")
            ptp_success = False

    return {
        "fail_to_pass_results": ftp_results,
        "pass_to_pass_results": ptp_results,
        "success": ftp_success and ptp_success,
    }


def is_repo_supported(repo: str) -> bool:
    """Check if a repo has an official SWE-bench log parser."""
    _load_parsers()
    return repo in _MAP_REPO_TO_PARSER_PY


def list_supported_repos() -> List[str]:
    """Return sorted list of repos with official parsers."""
    _load_parsers()
    return sorted(_MAP_REPO_TO_PARSER_PY.keys())


def get_test_cmd(repo: str, version: str) -> Optional[str]:
    """Return the official test command for a repo+version, or None.

    Reads from the vendored swebench constants without importing the full package.
    """
    constants_path = _SWEBENCH_ROOT / "swebench" / "harness" / "constants" / "python.py"
    if not constants_path.exists():
        return None

    source = constants_path.read_text()
    # Find MAP_REPO_VERSION_TO_SPECS_PY definition
    # It's a large dict literal — exec it and extract
    namespace = {}
    try:
        exec(compile(source, str(constants_path), "exec"), namespace)
    except Exception:
        return None

    specs = namespace.get("MAP_REPO_VERSION_TO_SPECS_PY", {})
    version_specs = specs.get(repo, {}).get(version, {})
    return version_specs.get("test_cmd")


def get_test_directives(test_patch: str, repo: str) -> List[str]:
    """Extract test directives from test_patch diff, mirroring SWE-bench's official logic.

    For Django repos, converts file paths to module format.
    """
    if not test_patch:
        return []

    # Extract file paths from diff headers
    diff_pat = r"diff --git a/.* b/(.*)"
    directives = re.findall(diff_pat, test_patch)

    # Filter out non-test files
    directives = [
        d for d in directives
        if not any(d.endswith(ext) for ext in NON_TEST_EXTS)
    ]

    # For Django: strip extension, remove tests/ prefix, convert / to .
    if repo == "django/django":
        transformed = []
        for d in directives:
            if d.endswith(".py"):
                d = d[:-len(".py")]
            if d.startswith("tests/"):
                d = d[len("tests/"):]
            d = d.replace("/", ".")
            transformed.append(d)
        directives = transformed

    return directives


def build_full_test_command(repo: str, version: str, test_patch: str) -> str:
    """Build the complete test command: install step + official test_cmd + directives.

    Returns empty string if no official test_cmd is available.
    """
    test_cmd = get_test_cmd(repo, version)
    if not test_cmd:
        raise ValueError(
            f"No official test_cmd for repo='{repo}' version='{version}'. "
            "This repo/version combination is not supported."
        )

    directives = get_test_directives(test_patch, repo)
    directive_args = " ".join(shlex.quote(d) for d in directives) if directives else ""

    # Install step: pip install the patched repo from /workspace
    # The Docker image already has the package installed from /opt/repo.
    # We do a lightweight reinstall from /workspace (which has patches applied).
    install_step = (
        "python -m pip install --disable-pip-version-check -e . 2>/dev/null || true"
    )

    # Append directives as arguments to test_cmd (not as separate && chain)
    full_test = f"{test_cmd} {directive_args}" if directive_args else test_cmd

    # Fix: use 'python' prefix for scripts that may lack execute permission
    # after being copied/mounted in Docker (e.g., Django's tests/runtests.py)
    full_test = full_test.replace("./tests/runtests.py", "python tests/runtests.py")

    return f"{install_step} && {full_test}"
