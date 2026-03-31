## Context
`FilePathField(path=...)` is intended to support machine-dependent filesystem locations, but today `makemigrations` resolves whatever value the field exposes at migration-writing time. The goal is to let users pass an importable callable so migrations preserve the callable reference instead of baking in a machine-specific absolute path.

The current code already stores `path` unchanged in `FilePathField.deconstruct()` and passes it through to the form field in `FilePathField.formfield()`. The likely gap is missing regression coverage rather than a missing serializer feature: Django's migration serializer already supports top-level importable callables and already rejects lambdas / local functions.

## Recommended approach
1. Verify the behavior contract in `django/db/models/fields/__init__.py` and keep `FilePathField.deconstruct()` returning `self.path` unchanged.
   - `django/db/models/fields/__init__.py:1664-1719`
   - No eager evaluation should be introduced in `deconstruct()` or `formfield()`.
   - If implementation work reveals any path resolution before serialization, fix only that specific eager-evaluation point.

2. Add deconstruction regression coverage for callable `path`.
   - `tests/field_deconstruction/tests.py`
   - Follow the existing callable-argument pattern used for callable `choices`.
   - Add a test that constructs `models.FilePathField(path=some_top_level_function)` and asserts `deconstruct()` returns `kwargs["path"] is some_top_level_function`, not the evaluated filesystem string.

3. Add migration writer coverage proving callable `path` is preserved in serialized migrations.
   - `tests/migrations/test_writer.py`
   - Add a top-level helper function in the test module that returns a path.
   - Serialize `models.FilePathField(path=helper_function)` and assert the generated field string references the helper by dotted import path, not the helper's return value.
   - This should mirror existing callable serialization expectations in `tests/migrations/test_writer.py:334-340`.

4. Keep the callable constraints aligned with existing migration serialization rules.
   - Supported: top-level importable functions.
   - Not supported: lambdas, nested functions, other non-importable callables.
   - No serializer changes should be needed unless tests expose an unexpected special case.

5. Add a small release note if the patch changes user-visible behavior rather than only documenting already-supported behavior.
   - Likely release notes file under `docs/releases/` for the active branch.
   - Only add API docs if current docs explicitly say `path` must be a concrete string/path and do not mention callable support.

## Reuse / references
- Callable-preserving deconstruction pattern:
  - `tests/field_deconstruction/tests.py:177-187`
  - callable `choices` pattern noted in existing deconstruction tests.
- Migration callable serialization behavior:
  - `tests/migrations/test_writer.py:334-340`
- FilePathField implementation:
  - `django/db/models/fields/__init__.py:1664-1719`
- Forms FilePathField expects a concrete path when instantiated, so the model field should preserve the callable until runtime rather than resolve it during migration generation:
  - `django/forms/fields.py:1078-1079`

## Critical files
- `django/db/models/fields/__init__.py`
- `tests/field_deconstruction/tests.py`
- `tests/migrations/test_writer.py`
- optionally `docs/releases/*`

## Verification
- Run targeted tests for field deconstruction and migration serialization.
  - `tests/field_deconstruction/tests.py`
  - `tests/migrations/test_writer.py`
- Confirm a `FilePathField(path=<top-level callable>)` serializes to a dotted callable reference.
- Confirm lambda / local-function behavior is unchanged and still fails consistently with existing serializer rules.
