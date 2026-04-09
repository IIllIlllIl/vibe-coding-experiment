# Fix: Allow non-disjoint cycles in Permutation constructor

## Context

`Permutation([[0,1],[0,1]])` raises `ValueError: there were repeated elements...` instead of computing the identity permutation. Non-disjoint cycles should be composed left-to-right, which is mathematically valid and already supported by the `Cycle` class.

## Root Cause

In `sympy/combinatorics/permutations.py`, lines 897-903, the constructor flattens all cycles into a single list and rejects any with duplicate elements:

```python
temp = flatten(args)
if has_dups(temp):
    if is_cycle:
        raise ValueError('there were repeated elements; to resolve '
        'cycles use Cycle%s.' % ...)
```

This check fires **before** the composition logic at lines 911-919, which already handles non-disjoint cycles correctly:

```python
if is_cycle:
    c = Cycle()
    for ci in args:
        c = c(*ci)
    aform = c.list()
```

## Plan

### 1. Remove the non-disjoint cycle restriction (`permutations.py`)

In `sympy/combinatorics/permutations.py`, modify the duplicate check at lines 897-903 to only reject duplicates for **array form** (not cycle form). Change:

```python
temp = flatten(args)
if has_dups(temp):
    if is_cycle:
        raise ValueError('there were repeated elements; to resolve '
        'cycles use Cycle%s.' % ''.join([str(tuple(c)) for c in args]))
    else:
        raise ValueError('there were repeated elements.')
```

To:

```python
if not is_cycle:
    if has_dups(args):
        raise ValueError('there were repeated elements.')
```

This skips the duplicate check entirely for cycles, letting them fall through to the existing composition logic at lines 911-916.

### 2. Update tests (`test_permutations.py`)

In `sympy/combinatorics/tests/test_permutations.py`:

- **Remove** line 352: `raises(ValueError, lambda: Permutation([[1], [1, 2]]))` — this should now succeed
- **Add** tests verifying non-disjoint cycles produce correct results:
  - `Permutation([[0,1],[0,1]])` should equal identity
  - `Permutation([[1,2],[2,3]])` should compose left-to-right correctly

## Verification

```bash
cd /Users/taoran.wang/Documents/vibe-trust/Planing/vibe-coding-experiment/experiments/sympy__sympy-12481/repo
python -c "from sympy.combinatorics import Permutation; print(Permutation([[0,1],[0,1]]))"
python -m pytest sympy/combinatorics/tests/test_permutations.py -x -q
```
