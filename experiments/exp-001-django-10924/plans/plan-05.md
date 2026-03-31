# Context
`FilePathField(path=...)` currently stores whatever is passed in `self.path` and `deconstruct()` writes that value straight into migrations (`django/db/models/fields/__init__.py:1664-1702`). That means when callers compute a machine-specific absolute path before field construction, migrations freeze the resolved path. The goal is to support passing an importable callable/`functools.partial` so migrations preserve the callable reference while runtime form generation still receives a concrete filesystem path.

# Recommended approach
1. Update `FilePathField` in `django/db/models/fields/__init__.py`.
   - Preserve the original `path` argument on a private attribute dedicated to deconstruction.
   - Add a small helper for runtime resolution (e.g. return `callable(raw_path) and raw_path() or raw_path`).
   - Keep `formfield()` responsible for evaluating the callable immediately before constructing `forms.FilePathField`, since the forms layer expects a concrete path string (`django/forms/fields.py:1078-1119`).
   - Keep plain string behavior unchanged.

2. Change `FilePathField.deconstruct()` in the same file.
   - Serialize the original `path` argument rather than any evaluated runtime value.
   - Rely on the existing migration serializer support for importable callables and `functools.partial`; no serializer changes should be needed.

3. Extend deconstruction coverage in `tests/field_deconstruction/tests.py`.
   - Add a module-level callable returning a path.
   - Assert `FilePathField(path=callable).deconstruct()` keeps the callable in `kwargs["path"]`.
   - Add a `functools.partial` case if convenient, since Django already supports serializing partials.

4. Add migration serialization coverage in `tests/migrations/test_writer.py`.
   - Add module-level helpers and verify a `FilePathField(path=<callable>)` round-trips through `MigrationWriter.serialize()`.
   - Include a failure case expectation for non-importable/local callables only if an adjacent pattern already exists and the test stays narrowly scoped.

5. Add autodetector regression coverage in `tests/migrations/test_autodetector.py`.
   - Mirror the existing `FileField(upload_to=functools.partial(...))` pattern.
   - Verify identical callable/partial paths produce no migration.
   - Verify changed callable arguments produce `AlterField`.

6. Add a runtime behavior test for `formfield()`.
   - Place it in the most relevant existing model-field test module for `FilePathField`.
   - Assert callable `path` is evaluated when building the form field and yields usable choices from the resolved directory.

# Critical files
- `django/db/models/fields/__init__.py`
- `tests/field_deconstruction/tests.py`
- `tests/migrations/test_writer.py`
- `tests/migrations/test_autodetector.py`
- existing FilePathField runtime test module under `tests/model_fields/` (to locate before implementation)

# Reuse
- Follow the callable-preservation pattern already used for migration-safe field arguments such as `FileField.upload_to`/serializer support in `tests/migrations/test_writer.py` and `tests/migrations/test_autodetector.py`.
- Keep forms behavior aligned with `django/forms/fields.py:1078-1119`, which requires a concrete path at form-field construction time.

# Verification
- Run targeted tests for:
  - `tests/field_deconstruction/tests.py`
  - `tests/migrations/test_writer.py`
  - `tests/migrations/test_autodetector.py`
  - the chosen `tests/model_fields/...` FilePathField runtime test module
- If needed, add a focused migration-writing assertion that the serialized migration contains the callable reference rather than a resolved absolute path.
