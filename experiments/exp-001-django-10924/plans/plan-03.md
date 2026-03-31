## Context
`FilePathField(path=...)` currently stores whatever is passed in and uses that same value during `deconstruct()`. That breaks the migration use case when `path` is machine-specific and should be provided by an importable callable instead of a resolved absolute string. The goal is to let `FilePathField(path=<callable>)` remain runtime-evaluated for forms while preserving the original callable for migration serialization.

## Recommended approach
1. Update `FilePathField` in `django/db/models/fields/__init__.py`.
   - Keep the original `path` argument on the field for deconstruction.
   - Continue evaluating callable `path` only when building the form field in `FilePathField.formfield()`.
   - Change `FilePathField.deconstruct()` to emit the original constructor argument for `path`, so top-level callables serialize via Django's existing migration serializer instead of being replaced by an evaluated filesystem path.
   - Reuse the existing Django pattern already used for callable-backed field options such as `FileField(storage=callable)`.

2. Add deconstruction coverage in `tests/field_deconstruction/tests.py`.
   - Add a module-level helper function returning a path.
   - Assert that `models.FilePathField(path=helper).deconstruct()` preserves the original callable in `kwargs["path"]`.

3. Add migration writer coverage in `tests/migrations/test_writer.py`.
   - Add a module-level helper function for a valid importable callable path.
   - Assert that serializing `models.FilePathField(path=helper)` produces a migration value that references the callable by import path.
   - Add a negative test showing lambdas still fail with the normal serializer error, since only importable top-level callables are migration-safe.

4. Keep runtime behavior covered.
   - Existing form behavior tests in `tests/forms_tests/field_tests/test_filepathfield.py` already cover `FilePathField` path usage.
   - If needed, add a focused assertion that callable `path` is still resolved when creating the form field, not at field initialization time.

## Critical files
- `django/db/models/fields/__init__.py`
- `tests/field_deconstruction/tests.py`
- `tests/migrations/test_writer.py`
- `tests/forms_tests/field_tests/test_filepathfield.py`

## Reused existing behavior
- `django/db/models/fields/__init__.py` — current `FilePathField` implementation and `deconstruct()` behavior.
- `django/db/models/fields/files.py` — existing callable-preservation pattern in `FileField(storage=callable)`.
- `django/db/migrations/serializer.py` — existing function serialization rules for top-level callables and rejection of lambdas/local functions.

## Verification
- Run the `FilePathField` deconstruction tests.
- Run migration writer serialization tests.
- Run `FilePathField` form tests to confirm callable runtime resolution still works.
- Confirm end-to-end that a model using `FilePathField(path=<module-level callable>)` would serialize the callable reference in migrations rather than a machine-specific resolved path.
