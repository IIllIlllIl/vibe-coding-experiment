# Plan: Support non-disjoint cycles in `Permutation` constructor

## Context

`Permutation([[0,1],[0,1]])` raises `ValueError: there were repeated elements` instead of constructing the identity permutation. Non-disjoint cycles should be composed left-to-right to produce the correct result. The `Cycle` class already supports this via `Cycle.__call__`, but the `Permutation` constructor has a premature duplicate check that blocks it.

## File to modify

- `sympy/combinatorics/permutations.py` (lines 897-903)

## Change

In the `__new__` method, when `is_cycle` is True, **skip the `has_dups` error** and let the existing `Cycle` composition (lines 911-917) handle non-disjoint cycles. The `Cycle` class already validates individual cycles for internal duplicates, so no invalid input slips through.

Replace lines 897-903:
```python
temp = flatten(args)
if has_dups(temp):
    if is_cycle:
        raise ValueError('there were repeated elements; to resolve '
        'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))
    else:
        raise ValueError('there were repeated elements.')
```

With:
```python
temp = flatten(args)
if has_dups(temp):
    if is_cycle:
        pass  # non-disjoint cycles are handled by Cycle composition below
    else:
        raise ValueError('there were repeated elements.')
```

## Tests to update

- `sympy/combinatorics/tests/test_permutations.py`
  - Add test: `Permutation([[0,1],[0,1]])` should be the identity
  - Add test: `Permutation([[0,1],[1,2]])` == `Permutation([[0,1,2]])`
  - Update line 352: remove the `raises(ValueError, ...)` for `Permutation([[1], [1, 2]])` since it should now produce `Permutation([0, 2, 1])` (cycle `[1,2]` composed with identity `[1]` → `[1,2]`)

## Verification

```bash
python -c "from sympy.combinatorics import Permutation; print(Permutation([[0,1],[0,1]]))"
# Expected: Permutation(1)(0)(2)
```

```bash
./bin/test sympy/combinatorics/tests/test_permutations.py
```
