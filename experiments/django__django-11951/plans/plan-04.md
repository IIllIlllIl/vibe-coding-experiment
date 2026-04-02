# Fix: bulk_create batch_size should respect max_batch_size

## Context

In `_batched_insert` (the helper for `bulk_create`), the `batch_size` parameter overrides the database-compatible batch size calculated by `bulk_batch_size()`. This is a bug — if a user passes `batch_size=1000` but the database only supports batches of 100, the query will fail. The `bulk_update` method already handles this correctly by taking `min(batch_size, max_batch_size)`.

## Changes

### 1. Fix `_batched_insert` in `django/db/models/query.py` (line 1212)

**Current:**
```python
batch_size = (batch_size or max(ops.bulk_batch_size(fields, objs), 1))
```

**New:**
```python
max_batch_size = max(ops.bulk_batch_size(fields, objs), 1)
batch_size = min(batch_size, max_batch_size) if batch_size else max_batch_size
```

This mirrors the logic already used in `bulk_update` at line 523.

### 2. Add test in `tests/bulk_create/tests.py`

Add a test that verifies when `batch_size` exceeds the `bulk_batch_size` limit, it gets clamped. This can be done by mocking `bulk_batch_size` to return a small value and asserting the correct number of queries.

## Verification

Run the bulk_create tests:
```
python tests/runtests.py bulk_create
```
