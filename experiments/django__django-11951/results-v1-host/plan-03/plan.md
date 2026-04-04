# Fix: bulk_create batch_size should respect database max_batch_size

## Context

In `bulk_create`, a user-provided `batch_size` completely overrides the database-compatible `max_batch_size` calculated by the backend. This is inconsistent with `bulk_update`, which correctly takes `min(batch_size, max_batch_size)`. A user can pass a `batch_size` larger than the database supports, causing errors (e.g., SQLite's compound select limit).

## Change

**File:** `django/db/models/query.py`, line 1212 (`_batched_insert` method)

**Current code:**
```python
batch_size = (batch_size or max(ops.bulk_batch_size(fields, objs), 1))
```

**New code:**
```python
max_batch_size = max(ops.bulk_batch_size(fields, objs), 1)
batch_size = min(batch_size, max_batch_size) if batch_size else max_batch_size
```

This mirrors the logic already used in `bulk_update` at line 522-523.

## Test

Add a test to `tests/bulk_create/tests.py` verifying that when an explicit `batch_size` exceeds the database's `max_batch_size`, the batch size is capped. We can test this by mocking `bulk_batch_size` to return a small value and asserting the number of queries executed matches the capped batch size.

## Verification

Run the bulk_create tests:
```
./runtests.py bulk_create
```
