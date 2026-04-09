# Plan: Allow non-disjoint cycles in Permutation constructor

## Context

`Permutation([[0,1],[0,1]])` raises `ValueError` instead of constructing the identity permutation. Non-disjoint cycles should be applied left-to-right (composed) and the resulting permutation returned. The `Cycle` class already supports this — only the `Permutation.__new__` validation blocks it.

## File: `sympy/combinatorics/permutations.py`

### Change 1: Remove the error for non-disjoint cycles (lines 897-903)

Current code raises `ValueError` when `has_dups(flatten(args))` is true for cycle form. Instead, only raise for **array form** duplicates (which are truly invalid). For cycle form, let execution fall through to the existing composition logic at lines 911-918:

```python
temp = flatten(args)
if has_dups(temp):
    if is_cycle:
        pass  # non-disjoint cycles are handled by composition below
    else:
        raise ValueError('there were repeated elements.')
```

The existing cycle composition code already works correctly:
```python
if is_cycle:
    c = Cycle()
    for ci in args:
        c = c(*ci)
    aform = c.list()
```

## File: `sympy/combinatorics/tests/test_permutations.py`

### Change 2: Update test at line 352

Change:
```python
raises(ValueError, lambda: Permutation([[1], [1, 2]]))
```
To an assertion that verifies the correct result:
```python
assert Permutation([[1], [1, 2]]) == Permutation([0, 2, 1])
```
(`[1]` is identity on element 1, then `[1,2]` swaps 1 and 2, so result is `[0, 2, 1]`)

### Change 3: Add tests for non-disjoint cycles

Add new test cases:
```python
assert Permutation([[0, 1], [0, 1]]) == Permutation([])  # identity (applying same swap twice)
assert Permutation([[1, 2], [2, 3]]) == Permutation([[1, 3, 2]])  # left-to-right composition
```

## Verification

```bash
cd /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481/repo
python -c "from sympy.combinatorics.permutations import Permutation; print(Permutation([[0,1],[0,1]]))"
python -m pytest sympy/combinatorics/tests/test_permutations.py -x -q
```
