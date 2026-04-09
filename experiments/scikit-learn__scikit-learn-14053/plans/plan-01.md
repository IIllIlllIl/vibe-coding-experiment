# Fix IndexError in `export_text` with single feature

## Context
`export_text` crashes with `IndexError: list index out of range` when the tree has only one feature and `feature_names` is provided. The root cause is on line 893 of `sklearn/tree/export.py`:

```python
feature_names_ = [feature_names[i] for i in tree_.feature]
```

`tree_.feature` contains `-2` (`TREE_UNDEFINED`) for leaf nodes. When `feature_names` has one element, `feature_names[-2]` is out of bounds. With multiple features, `-2` silently wraps around, masking the bug.

## Fix

**File:** `sklearn/tree/export.py` (line 892-895)

Guard against `TREE_UNDEFINED` in both branches of the feature name list comprehension:

```python
if feature_names:
    feature_names_ = [feature_names[i] if i != _tree.TREE_UNDEFINED else None
                      for i in tree_.feature]
else:
    feature_names_ = ["feature_{}".format(i) if i != _tree.TREE_UNDEFINED else None
                      for i in tree_.feature]
```

The value is only used at line 931 inside a `if tree_.feature[node] != _tree.TREE_UNDEFINED` guard, so `None` entries are never accessed.

## Test

**File:** `sklearn/tree/tests/test_export.py`

Add a test reproducing the bug — a single-feature tree with `feature_names`:

```python
def test_export_text_single_feature():
    X, y = load_iris(return_X_y=True)
    X = X[:, 0].reshape(-1, 1)
    tree = DecisionTreeClassifier().fit(X, y)
    result = export_text(tree, feature_names=['sepal_length'])
    assert 'sepal_length' in result
```

## Verification
```bash
python -m pytest sklearn/tree/tests/test_export.py -xvs -k "export_text"
```
