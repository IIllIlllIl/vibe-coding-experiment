# Fix: bulk_create batch_size should respect max_batch_size

## Context

In `bulk_create`, when a user provides a `batch_size`, the database's `max_batch_size` constraint is completely ignored. The `bulk_update` method correctly uses `min(batch_size, max_batch_size)`, but `_batched_insert` (used by `bulk_create`) uses `or` logic instead. This means a user-provided `batch_size` could exceed what the database can handle (e.g., SQLite's variable limit).

## Change

**File:** `django/db/models/query.py`, line 1212

Replace:
```python
batch_size = (batch_size or max(ops.bulk_batch_size(fields, objs), 1))
```

With (matching `bulk_update` pattern at line 523):
```python
max_batch_size = max(ops.bulk_batch_size(fields, objs), 1)
batch_size = min(batch_size, max_batch_size) if batch_size else max_batch_size
```

## Test

Add a test in `tests/bulk_create/tests.py` that verifies when `batch_size` exceeds the database's `max_batch_size`, the actual batch size is capped at `max_batch_size`. This can be tested by mocking `bulk_batch_size` to return a small value and asserting the number of queries matches the capped size.

## Verification

```bash
python -m django test bulk_create --settings=tests.settings
```
