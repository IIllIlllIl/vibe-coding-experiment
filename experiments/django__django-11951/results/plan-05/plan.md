# Fix: bulk_create batch_size overrides DB-compatible batch size

## Context

`bulk_create`'s `batch_size` parameter ignores the database's max batch size limit, while `bulk_update` correctly takes the minimum of the two. This is inconsistent and can cause errors when a user-specified `batch_size` exceeds what the database can handle.

## Problem

In `_batched_insert` (line 1212 of `django/db/models/query.py`):

```python
batch_size = (batch_size or max(ops.bulk_batch_size(fields, objs), 1))
```

If `batch_size` is provided, it's used directly, ignoring `ops.bulk_batch_size()`.

Meanwhile, `bulk_update` (line 523) correctly uses:
```python
batch_size = min(batch_size, max_batch_size) if batch_size else max_batch_size
```

## Fix

**File**: `django/db/models/query.py`, line 1212 in `_batched_insert`

Change:
```python
batch_size = (batch_size or max(ops.bulk_batch_size(fields, objs), 1))
```

To:
```python
max_batch_size = max(ops.bulk_batch_size(fields, objs), 1)
batch_size = min(batch_size, max_batch_size) if batch_size else max_batch_size
```

## Verification

Run the existing bulk_create tests:
```bash
python -m django test bulk_create --settings=tests.settings
```

Also run bulk_update tests to confirm no regression:
```bash
python -m django test queries.test_bulk_update --settings=tests.settings
```
