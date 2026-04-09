# Fix: Allow non-disjoint cycles in Permutation constructor

## Context
`Permutation([[0,1],[0,1]])` raises `ValueError` instead of composing the cycles into the identity permutation. Non-disjoint cycles should be applied left-to-right and the result returned.

## File to modify
`sympy/combinatorics/permutations.py` (lines 897-903)

## Change
When `is_cycle` is `True` and duplicates are found, instead of raising `ValueError`, skip the duplicate check and let the existing cycle composition code (lines 911-917) handle it. That code already uses `Cycle.__call__` which correctly composes non-disjoint cycles.

**Before:**
```python
temp = flatten(args)
if has_dups(temp):
    if is_cycle:
        raise ValueError('there were repeated elements; to resolve '
        'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))
    else:
        raise ValueError('there were repeated elements.')
```

**After:**
```python
temp = flatten(args)
if has_dups(temp):
    if not is_cycle:
        raise ValueError('there were repeated elements.')
```

This removes the error for non-disjoint cycles while preserving the duplicate check for array-form input. The existing composition loop (`c = c(*ci)`) already handles overlapping cycles correctly.

## Verification
```bash
python -c "from sympy.combinatorics.permutations import Permutation; print(Permutation([[0,1],[0,1]]))"
# Expected: Permutation([], size=2)  (identity)
```
Then run the existing test suite:
```bash
python -m pytest sympy/combinatorics/tests/test_permutations.py -x
```
