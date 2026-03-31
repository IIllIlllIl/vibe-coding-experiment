# Plan: Allow FilePathField path to accept a callable

## Context

Currently, `FilePathField.path` must be a static string value. When users need dynamic paths based on settings or other runtime values (e.g., `os.path.join(settings.LOCAL_FILE_DIR, 'example_dir')`), the path gets evaluated during migration creation, baking in the value from the machine where `makemigrations` was run. This breaks when migrations are run on different machines with different directory structures.

The solution is to allow `path` to accept a callable (similar to how `FileField.upload_to` works), which will be evaluated at runtime rather than during migration creation.

## Investigation Summary

Django already has well-established patterns for handling callable field arguments:

1. **FileField.upload_to**: Accepts both string and callable values
   - Callables are stored as-is in migrations and serialized automatically
   - Evaluation happens at runtime in `generate_filename()` method

2. **Migration serialization**: The `FunctionTypeSerializer` handles callable arguments automatically
   - Supports methods and functions (not lambdas)
   - Serializes as `"module.path.function_name"`

3. **Deconstruct pattern**: Callables are treated like any other value
   - No special handling needed in `deconstruct()` method
   - Stored directly in kwargs

## Implementation Plan

**Design Philosophy**: Follow Django's established patterns and keep the implementation minimal. The entire feature requires only a one-line change to the `formfield()` method.

### 1. Modify `django/db/models/fields/__init__.py` - FilePathField.formfield()

**Only change needed**: Update line 1712 in the `formfield()` method to evaluate callable paths:

```python
def formfield(self, **kwargs):
    return super().formfield(**{
        'path': self.path() if callable(self.path) else self.path,  # ← Only this line changes
        'match': self.match,
        'recursive': self.recursive,
        'form_class': forms.FilePathField,
        'allow_files': self.allow_files,
        'allow_folders': self.allow_folders,
        **kwargs,
    })
```

**Why this approach**:
- Evaluates callable paths inline when the form field is created
- Follows FileField's pattern of handling callable arguments
- Minimal change - no new methods or complexity needed
- The migration system automatically serializes callables via `FunctionTypeSerializer`

**No changes needed to**:
- `__init__` method - already accepts any value including callables
- `deconstruct` method - already stores `self.path` directly, callables are serialized automatically
- No need for helper methods like `get_path()` - this would be over-engineering

### 2. Add Tests

#### 2.1 Create new test file: `tests/model_fields/test_filepathfield.py`

Follow Django's pattern of having dedicated test files for each field type.

```python
import os
from django.db.models import FilePathField
from django.test import SimpleTestCase


class FilePathFieldTests(SimpleTestCase):

    def test_path(self):
        """FilePathField.path stores string paths correctly."""
        path = os.path.dirname(__file__)
        field = FilePathField(path=path)
        self.assertEqual(field.path, path)
        self.assertEqual(field.formfield().path, path)

    def test_callable_path(self):
        """FilePathField.path may be a callable that's evaluated in formfield()."""
        path = os.path.dirname(__file__)

        def generate_path():
            return path

        field = FilePathField(path=generate_path)
        self.assertEqual(field.path, generate_path)
        # Callable is evaluated when creating form field
        self.assertEqual(field.formfield().path, path)

    def test_callable_path_evaluated_each_time(self):
        """Callable path should be evaluated fresh for each formfield() call."""
        call_count = 0

        def generate_path():
            nonlocal call_count
            call_count += 1
            return os.path.dirname(__file__)

        field = FilePathField(path=generate_path)
        field.formfield()
        field.formfield()
        self.assertEqual(call_count, 2)
```

**Why**: Tests the core functionality - that callable paths are evaluated when form fields are created, and evaluated fresh each time.

#### 2.2 Add deconstruction test to `tests/field_deconstruction/tests.py`

**Important**: Must use module-level function, not local function (local functions can't be serialized in migrations).

```python
# At module level in tests/field_decomposition/tests.py or a helper module:
def generate_test_path():
    return '/test/path'

# In test class:
def test_file_path_field_callable_path(self):
    """Callable path is preserved in deconstruction."""
    # Use module-level function, not local function
    field = models.FilePathField(path=generate_test_path)
    name, path, args, kwargs = field.deconstruct()
    self.assertEqual(path, "django.db.models.FilePathField")
    self.assertEqual(args, [])
    # Callable is stored as-is, not evaluated
    self.assertEqual(kwargs['path'], generate_test_path)
```

**Why**: Tests that deconstruct() correctly preserves callable references for migration serialization.

#### 2.3 Run existing tests
Ensure backward compatibility with existing code:

```bash
python tests/runtests.py tests.forms_tests.field_tests.test_filepathfield
python tests/runtests.py tests.model_fields
```

### 3. Update Documentation

#### 3.1 Update field documentation in `docs/ref/models/fields.txt` (around line 866)

Add documentation for callable paths after the existing `path` attribute documentation:

```rst
.. attribute:: FilePathField.path

    Required. The absolute filesystem path to a directory from which this
    :class:`FilePathField` should get its choices. Example: ``"/home/images"``.

    ``path`` may also be a callable that returns the absolute path. The callable
    will be evaluated when the form field is created. This is useful for
    dynamic paths that vary by machine or environment. Example::

        import os
        from django.conf import settings
        from django.db import models

        def get_image_path():
            return os.path.join(settings.LOCAL_FILE_DIR, 'images')

        class MyModel(models.Model):
            image = models.FilePathField(path=get_image_path)

    .. admonition:: Note

        The callable must be importable (i.e., a module-level function or class
        method, not a local function or lambda). This is required for migration
        serialization.

    .. versionchanged:: VERSION

        ``path`` can now be a callable.
```

**Why**: Provides clear documentation with realistic example matching the user's use case, and notes about callable limitations.

#### 3.2 Add release note

Add to appropriate release notes file (e.g., `docs/releases/3.0.txt` or current version):

```rst
* :class:`~django.db.models.FilePathField` now accepts a callable ``path``.
  This allows dynamic path resolution based on settings or environment.
```

## Critical Files

**Implementation (1 file, 1 line changed)**:
1. `django/db/models/fields/__init__.py` (line 1712)
   - Only change: Update `formfield()` to evaluate callable paths inline

**Tests (2 new files, 1 existing file)**:
2. `tests/model_fields/test_filepathfield.py` (NEW)
   - Core functionality tests for callable paths
3. `tests/field_deconstruction/tests.py`
   - Add deconstruction test for callable paths (using module-level function)

**Documentation (1-2 files)**:
4. `docs/ref/models/fields.txt` (line ~866)
   - Document callable path support with examples and limitations
5. `docs/releases/VERSION.txt`
   - Add release note about new feature

**Reference files (no changes, for understanding patterns)**:
- `django/db/models/fields/files.py` - FileField pattern for callable `upload_to`
- `django/db/migrations/serializer.py` - FunctionTypeSerializer for understanding migration serialization

## Verification

### 1. Run new and existing tests
```bash
# New tests
python tests/runtests.py tests.model_fields.test_filepathfield

# Existing tests to ensure no regressions
python tests/runtests.py tests.forms_tests.field_tests.test_filepathfield
python tests/runtests.py tests.field_decomposition
python tests/runtests.py tests.model_fields
```

### 2. Manual integration test
Create a test model with callable path:

```python
# test_app/models.py
import os
from django.conf import settings
from django.db import models

def get_dynamic_path():
    return os.path.join(settings.BASE_DIR, 'dynamic_files')

class TestModel(models.Model):
    file = models.FilePathField(path=get_dynamic_path)
```

Then verify:
```bash
# Create migration
python manage.py makemigrations test_app

# Check that migration file contains function reference, NOT evaluated path
cat test_app/migrations/0001_initial.py
# Should see: path=test_app.models.get_dynamic_path
# NOT: path='/actual/path/from/this/machine'

# Apply migration
python manage.py migrate

# Test form displays correct choices
python manage.py shell
>>> from test_app.models import TestModel
>>> from django.forms import modelform_factory
>>> Form = modelform_factory(TestModel, fields=['file'])
>>> Form()  # Should show files from the dynamic path
```

### 3. Edge case testing
Test that the feature handles edge cases gracefully:
- Callable returns non-existent path (should fail with clear error)
- Callable returns None (should fail with clear error)
- Callable raises exception (exception should propagate)

## Migration Compatibility

**Backward compatible**: Existing code using string paths continues to work unchanged.

**Forward compatible**: Old migrations work with new code.

**Migration serialization**: Callables are automatically serialized by Django's `FunctionTypeSerializer` as `"module.function_name"` strings.

**Important constraints for callables** (same as FileField.upload_to):
- Must be importable (module-level function or class method)
- Cannot be local functions (would fail with "Cannot serialize: local function")
- Cannot be lambdas (would fail with "Cannot serialize: lambda")
- Must have `__module__` attribute
- Must have `__qualname__` without `<locals>`

## Alternative Approaches Considered

1. **Pass instance to callable**: Like FileField's `upload_to(instance, filename)` - rejected because FilePathField doesn't have access to instance when populating choices
2. **Lazy evaluation**: Defer path resolution until form creation - this is the chosen approach
3. **Path property**: Make path a property that evaluates callable - rejected because it would break deconstruct()
