# Fix: Allow non-disjoint cycles in Permutation constructor

## Context

`Permutation([[0,1],[0,1]])` raises `ValueError('there were repeated elements...')` instead of computing the identity permutation. Non-disjoint cycles should be composed left-to-right (or right-to-left per the existing `Cycle.__call__` convention) and the result returned. The existing composition logic at lines 911-917 already handles this correctly — the only problem is the early validation that rejects duplicates.

## File to modify

`sympy/combinatorics/permutations.py`

## Change

**Remove the duplicate-check block** (lines 898-903):

```python
if has_dups(temp):
    if is_cycle:
        raise ValueError('there were repeated elements; to resolve '
        'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))
    else:
        raise ValueError('there were repeated elements.')
```

The `else` branch (for array form, line 902-903) should be removed too since array form duplicates are actually invalid. But looking at the code, the `else` branch only runs when `is_cycle` is False, meaning the input is array form — and array form with duplicates would be caught later by the `is_valid` check. So the entire `if has_dups(temp)` block can be removed safely.

The code after the block (lines 911-917) already composes cycles correctly via `Cycle`:
```python
c = Cycle()
for ci in args:
    c = c(*ci)
aform = c.list()
```

This will produce the correct result for `[[0,1],[0,1]]` → identity permutation.

## Verification

1. Run the existing permutation tests: `python -m pytest sympy/combinatorics/tests/test_permutations.py -x`
2. Test the specific case:
   ```python
   from sympy.combinatorics.permutations import Permutation
   assert Permutation([[0,1],[0,1]]) == Permutation([0, 1])  # identity
   assert Permutation([[1,2],[2,3]]) == Permutation([[1,2],[2,3]])  # should work
   ```
3. Verify that truly invalid inputs (array form with out-of-range values) are still caught
