## Context
`FilePathField` already stores `path` verbatim in the model field and only uses it later when constructing the form field. The reported problem is that `makemigrations` should preserve a machine-independent callable reference for `path` instead of freezing an environment-specific resolved string into the migration. The main goal is to make callable `path` usage explicit and regression-tested so migrations keep importable callables intact.

## Recommended approach
Treat this as a targeted regression fix centered on migration serialization behavior, with production code changes only if tests expose a real gap.

1. Confirm the current contract in `django/db/models/fields/__init__.py`.
   - Reuse `FilePathField.deconstruct()` at `django/db/models/fields/__init__.py:1688` which already returns `path` unchanged.
   - Reuse the existing runtime behavior in `FilePathField.formfield()` at `django/db/models/fields/__init__.py:1710`, which passes `self.path` through to the form field instead of resolving it during deconstruction.
   - Do not add eager evaluation in `deconstruct()`, since that would recreate the machine-specific migration problem.

2. Add deconstruction coverage for callable `path`.
   - Extend `tests/field_deconstruction/tests.py` near the existing `test_file_path_field` coverage.
   - Add a module-level helper function that returns a path string.
   - Assert that `models.FilePathField(path=helper).deconstruct()` preserves the callable object in `kwargs["path"]`, rather than replacing it with the helper result.

3. Add migration writer regression coverage.
   - Extend `tests/migrations/test_writer.py` with a module-level helper callable.
   - Add a test that serializes `models.FilePathField(path=helper)` and verifies the generated migration code references the helper by dotted path, following the same serializer behavior already covered for other callable values in `tests/migrations/test_writer.py:334` and `tests/migrations/test_writer.py:464`.
   - Round-trip the serialized field and confirm the reconstructed field still has a callable `path`, not a concrete string.

4. Add an unsupported-callable regression test if needed.
   - If there is no direct `FilePathField` coverage for serializer failures, add a focused negative test showing that `lambda` or local functions are still rejected for `path`, matching Django’s existing callable serialization rules.
   - Keep this narrow; rely on the general serializer behavior already covered in `tests/migrations/test_writer.py:334` and `tests/migrations/test_writer.py:468` unless a field-specific test materially improves clarity.

5. Only patch production code if tests uncover an actual serialization bug.
   - If a failure appears, keep the fix minimal and in the serialization/deconstruction path.
   - Preserve the existing invariant: the original callable must survive deconstruction unchanged, and path resolution must remain deferred until runtime/form construction.

## Critical files
- `django/db/models/fields/__init__.py`
- `tests/field_deconstruction/tests.py`
- `tests/migrations/test_writer.py`

## Existing patterns to reuse
- `FilePathField.deconstruct()` in `django/db/models/fields/__init__.py:1688`
- `FilePathField.formfield()` in `django/db/models/fields/__init__.py:1710`
- Callable serializer coverage in `tests/migrations/test_writer.py:334`
- Unbound-method callable serialization pattern in `tests/migrations/test_writer.py:464`
- Existing `FilePathField` deconstruction tests in `tests/field_deconstruction/tests.py:177`

## Verification
- Run the focused deconstruction tests for `FilePathField`.
- Run the focused migration writer tests covering callable serialization and round-trip behavior.
- If production code changes are required, run the `FilePathField`-related form/model tests as a safety check to confirm runtime behavior is unchanged.
- End-to-end expectation: a model using `FilePathField(path=<importable callable>)` should produce migration code that references the callable, not the resolved absolute path from the current machine.
