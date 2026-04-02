# Fix: bulk_create batch_size should respect max_batch_size

## Context

In `_batched_insert` (the helper for `bulk_create`), the user-provided `batch_size` is used as-is if provided, ignoring the database-compatible max batch size. In contrast, `bulk_update` correctly takes `min(batch_size, max_batch_size)`. This means `bulk_create` can produce queries that exceed the database's limits when a large `batch_size` is explicitly passed.

## Change

**File:** `django/db/models/query.py`, line 1212

**Current code:**
```python
batch_size = (batch_size or max(ops.bulk_batch_size(fields, objs), 1))
```

**New code:**
```python
max_batch_size = max(ops.bulk_batch_size(fields, objs), 1)
batch_size = min(batch_size, max_batch_size) if batch_size else max_batch_size
```

This mirrors the logic in `bulk_update` at line 523.

## Verification

Run the existing bulk_create tests to confirm no regressions:
```bash
python tests/runtests.py bulk_create
```
