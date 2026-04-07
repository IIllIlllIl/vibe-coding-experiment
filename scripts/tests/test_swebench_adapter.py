#!/usr/bin/env python3
"""Tests for swebench_adapter.py — official SWE-bench parser integration."""

import json
import re
import sys
import unittest
from pathlib import Path

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from swebench_adapter import (
    NON_TEST_EXTS,
    TestStatus,
    build_full_test_command,
    eval_test_results,
    get_test_cmd,
    get_test_directives,
    get_parser_for_repo,
    is_repo_supported,
    list_supported_repos,
    parse_test_output,
    test_failed,
    test_passed,
)


# --- Real Django test output snippet (from experiments/django__django-11951) ---
DJANGO_OUTPUT = """\
Testing against Django installed in '/workspace/django' with up to 2 processes
Importing application bulk_create
Skipping setup of unused database(s): other.
test_batch_same_vals (bulk_create.tests.BulkCreateTests) ... ok
test_bulk_insert_expressions (bulk_create.tests.BulkCreateTests) ... ok
test_bulk_insert_nullable_fields (bulk_create.tests.BulkCreateTests) ... ok
test_explicit_batch_size_respects_max_batch_size (bulk_create.tests.BulkCreateTests) ... ok
test_efficiency (bulk_create.tests.BulkCreateTests) ... FAIL
test_empty_model (bulk_create.tests.BulkCreateTests) ... ERROR
"""

DJANGO_FTP = [
    "test_explicit_batch_size_respects_max_batch_size (bulk_create.tests.BulkCreateTests)",
]
DJANGO_PTP = [
    "test_batch_same_vals (bulk_create.tests.BulkCreateTests)",
    "test_bulk_insert_expressions (bulk_create.tests.BulkCreateTests)",
    "test_bulk_insert_nullable_fields (bulk_create.tests.BulkCreateTests)",
    "test_efficiency (bulk_create.tests.BulkCreateTests)",
    "test_empty_model (bulk_create.tests.BulkCreateTests)",
]

# --- Sample pytest -rA output ---
PYTEST_OUTPUT = """\
============================= test session starts ==============================
collected 5 items

tests/test_sample.py F.                                                  [100%]

=================================== FAILURES ===================================
_________________________________ test_fail ____________________________________
tests/test_sample.py:5: AssertionError
=========================== short test summary info ============================
FAILED tests/test_sample.py::test_fail
PASSED tests/test_sample.py::test_pass
PASSED tests/test_sample.py::test_pass2
PASSED tests/test_sample.py::test_pass3
SKIPPED tests/test_sample.py::test_skip
"""


class TestAdapterBasics(unittest.TestCase):
    """Test adapter loading and registry."""

    def test_repos_loaded(self):
        repos = list_supported_repos()
        self.assertGreater(len(repos), 10)

    def test_django_supported(self):
        self.assertTrue(is_repo_supported("django/django"))

    def test_pytest_supported(self):
        self.assertTrue(is_repo_supported("pytest-dev/pytest"))

    def test_unknown_repo_not_supported(self):
        self.assertFalse(is_repo_supported("unknown/repo"))

    def test_parser_returns_callable(self):
        parser = get_parser_for_repo("django/django")
        self.assertIsNotNone(parser)
        self.assertTrue(callable(parser))


class TestDjangoParser(unittest.TestCase):
    """Test Django log parsing with real output format."""

    def test_parse_django_output(self):
        status_map = parse_test_output("django/django", DJANGO_OUTPUT)
        self.assertIsInstance(status_map, dict)
        # Should find our test names
        found_tests = [t for t in status_map if "BulkCreateTests" in t]
        self.assertGreater(len(found_tests), 0)

    def test_django_eval_results(self):
        status_map = parse_test_output("django/django", DJANGO_OUTPUT)
        result = eval_test_results(status_map, DJANGO_FTP, DJANGO_PTP)
        self.assertIn("success", result)
        self.assertIn("fail_to_pass_results", result)
        self.assertIn("pass_to_pass_results", result)


class TestTestStatus(unittest.TestCase):
    """Test status enum and helper functions."""

    def test_passed_status(self):
        self.assertEqual(TestStatus.PASSED, "PASSED")
        self.assertEqual(TestStatus.PASSED.value, "PASSED")

    def test_failed_status(self):
        self.assertEqual(TestStatus.FAILED, "FAILED")

    def test_test_passed_function(self):
        status_map = {"test_a": TestStatus.PASSED, "test_b": TestStatus.FAILED}
        self.assertTrue(test_passed("test_a", status_map))
        self.assertFalse(test_passed("test_b", status_map))

    def test_test_failed_function(self):
        status_map = {"test_a": TestStatus.PASSED, "test_b": TestStatus.FAILED}
        self.assertFalse(test_failed("test_a", status_map))
        self.assertTrue(test_failed("test_b", status_map))
        # Missing test counts as failed
        self.assertTrue(test_failed("test_c", status_map))


class TestEvalTestResults(unittest.TestCase):
    """Test eval_test_results logic."""

    def test_all_pass(self):
        status_map = {"test_a": TestStatus.PASSED, "test_b": TestStatus.PASSED}
        result = eval_test_results(status_map, ["test_a"], ["test_b"])
        self.assertTrue(result["success"])
        self.assertEqual(result["fail_to_pass_results"]["test_a"], "PASSED")

    def test_ftp_fails(self):
        status_map = {"test_a": TestStatus.FAILED, "test_b": TestStatus.PASSED}
        result = eval_test_results(status_map, ["test_a"], ["test_b"])
        self.assertFalse(result["success"])
        self.assertEqual(result["fail_to_pass_results"]["test_a"], "FAILED")

    def test_ptp_fails(self):
        status_map = {"test_a": TestStatus.PASSED, "test_b": TestStatus.FAILED}
        result = eval_test_results(status_map, ["test_a"], ["test_b"])
        self.assertFalse(result["success"])

    def test_missing_test_fails(self):
        status_map = {"test_a": TestStatus.PASSED}
        result = eval_test_results(status_map, ["test_a"], ["test_missing"])
        self.assertFalse(result["success"])
        # Missing test is treated as FAILED by test_failed()
        self.assertEqual(result["pass_to_pass_results"]["test_missing"], "FAILED")

    def test_empty_lists(self):
        status_map = {"test_a": TestStatus.PASSED}
        result = eval_test_results(status_map, [], [])
        self.assertTrue(result["success"])


class TestGetTestCmd(unittest.TestCase):
    """Test official test command lookup."""

    def test_django_has_test_cmd(self):
        cmd = get_test_cmd("django/django", "3.1")
        self.assertIsNotNone(cmd)
        self.assertIn("runtests.py", cmd)

    def test_pytest_has_test_cmd(self):
        cmd = get_test_cmd("pytest-dev/pytest", "7.1")
        self.assertIsNotNone(cmd)
        self.assertIn("pytest", cmd)

    def test_unknown_repo_no_cmd(self):
        cmd = get_test_cmd("unknown/repo", "1.0")
        self.assertIsNone(cmd)


class TestGetTestDirectives(unittest.TestCase):
    """Test test directive extraction from test_patch."""

    DJANGO_TEST_PATCH = """\
diff --git a/tests/bulk_create/tests.py b/tests/bulk_create/tests.py
index abcdef..123456 100644
--- a/tests/bulk_create/tests.py
+++ b/tests/bulk_create/tests.py
@@ -0,0 +1,5 @@
+class BulkCreateTests(TestCase):
+    def test_new_feature(self):
+        pass
"""

    PYTEST_TEST_PATCH = """\
diff --git a/testing/test_capture.py b/testing/test_capture.py
index abcdef..123456 100644
--- a/testing/test_capture.py
+++ b/testing/test_capture.py
@@ -0,0 +1,5 @@
+def test_new_thing():
+    pass
"""

    MULTI_FILE_PATCH = """\
diff --git a/tests/test_a.py b/tests/test_a.py
--- a/tests/test_a.py
+++ b/tests/test_a.py
@@ -0,0 +1,3 @@
+def test_a(): pass
diff --git a/tests/test_b.py b/tests/test_b.py
--- a/tests/test_b.py
+++ b/tests/test_b.py
@@ -0,0 +1,3 @@
+def test_b(): pass
diff --git a/tests/data.json b/tests/data.json
--- a/tests/data.json
+++ b/tests/data.json
@@ -0,0 +1,3 @@
+{"key": "value"}
"""

    def test_django_directives(self):
        directives = get_test_directives(self.DJANGO_TEST_PATCH, "django/django")
        self.assertEqual(directives, ["bulk_create.tests"])

    def test_pytest_directives(self):
        directives = get_test_directives(self.PYTEST_TEST_PATCH, "pytest-dev/pytest")
        self.assertEqual(directives, ["testing/test_capture.py"])

    def test_filters_non_test_files(self):
        directives = get_test_directives(self.MULTI_FILE_PATCH, "scikit-learn/scikit-learn")
        self.assertIn("tests/test_a.py", directives)
        self.assertIn("tests/test_b.py", directives)
        self.assertNotIn("tests/data.json", directives)

    def test_empty_patch(self):
        directives = get_test_directives("", "django/django")
        self.assertEqual(directives, [])


class TestBuildFullTestCommand(unittest.TestCase):
    """Test full test command construction."""

    def test_django_command(self):
        patch = "diff --git a/tests/auth_tests/test_views.py b/tests/auth_tests/test_views.py\n"
        cmd = build_full_test_command("django/django", "3.1", patch)
        self.assertIn("runtests.py", cmd)
        self.assertIn("auth_tests.test_views", cmd)
        self.assertIn("pip install", cmd)

    def test_pytest_command(self):
        patch = "diff --git a/testing/test_capture.py b/testing/test_capture.py\n"
        cmd = build_full_test_command("pytest-dev/pytest", "7.1", patch)
        self.assertIn("pytest", cmd)
        self.assertIn("test_capture.py", cmd)

    def test_unknown_repo_raises(self):
        with self.assertRaises(ValueError):
            build_full_test_command("unknown/repo", "1.0", "")

    def test_empty_directives(self):
        cmd = build_full_test_command("django/django", "3.1", "")
        self.assertIn("runtests.py", cmd)


class TestNonTestExts(unittest.TestCase):
    """Test NON_TEST_EXTS filtering."""

    def test_json_excluded(self):
        self.assertIn(".json", NON_TEST_EXTS)

    def test_py_not_excluded(self):
        self.assertNotIn(".py", NON_TEST_EXTS)


if __name__ == "__main__":
    unittest.main()
