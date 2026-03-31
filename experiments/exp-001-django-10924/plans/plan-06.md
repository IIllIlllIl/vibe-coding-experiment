## Context
`FilePathField(path=...)` currently stores whatever is passed in, but the user case is about using a callable so migrations preserve a portable reference instead of a machine-specific absolute path. The intended outcome is that `makemigrations` can serialize a supported callable for `path`, while runtime form behavior still receives a resolved filesystem path.

## Recommended approach
1. Update `FilePathField.formfield()` in `django/db/models/fields/__init__.py` so it resolves `self.path` only at runtime: pass `self.path()` when `self.path` is callable, otherwise pass `self.path` unchanged.
2. Keep `FilePathField.deconstruct()` in `django/db/models/fields/__init__.py` preserving `self.path` unchanged in `kwargs["path"]` so migration serialization can keep a top-level callable reference instead of an evaluated path string.
3. Extend deconstruction coverage in `tests/field_deconstruction/tests.py` with a module-level callable and assert `FilePathField(path=callable).deconstruct()` returns that callable in `kwargs["path"]`.
4. Add focused runtime coverage in `tests/model_fields/test_filepathfield.py` to verify a callable `path` is evaluated for the generated form field but retained on the model field itself.
5. Add migration writer coverage in `tests/migrations/test_writer.py` for `models.FilePathField(path=<module-level function>)` so serialization emits the callable import path. Optionally add one failure case showing lambda/local functions are rejected through the normal migration serializer rules.

## Critical files
- `django/db/models/fields/__init__.py`
  - `FilePathField.__init__()`, `deconstruct()`, `formfield()`
- `tests/field_deconstruction/tests.py`
  - existing `test_file_path_field()` should gain callable-path assertions
- `tests/model_fields/test_filepathfield.py`
  - extend with callable runtime behavior test
- `tests/migrations/test_writer.py`
  - add `FilePathField(path=callable)` migration serialization coverage
- Reuse existing migration serializer behavior in `django/db/migrations/serializer.py` rather than adding field-specific serializer logic

## Reuse / existing behavior
- `FilePathField.deconstruct()` already preserves `self.path` as-is; that behavior should remain the migration boundary.
- Django’s migration serializer already knows how to serialize supported top-level functions and reject lambdas/local functions; rely on that generic behavior instead of special-casing `FilePathField`.

## Verification
- Run targeted tests:
  - `tests/model_fields/test_filepathfield.py`
  - `tests/field_deconstruction/tests.py`
  - `tests/migrations/test_writer.py`
- Confirm end-to-end that a top-level callable used in `FilePathField(path=...)` is preserved in deconstruction/migration serialization, while `formfield()` resolves it to a concrete path at runtime.
- Confirm unsupported callables still fail via the existing migration serializer rules.
