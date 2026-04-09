# Fix IndexError in `export_text` with single feature

## Context

`export_text` crashes with `IndexError: list index out of range` when the tree has only one feature and `feature_names` is provided.

**Root cause:** In `sklearn/tree/export.py:893`, the list comprehension `[feature_names[i] for i in tree_.feature]` iterates over all nodes, including leaf nodes where `tree_.feature[node]` is `-2` (`TREE_UNDEFINED`). When `feature_names` has only one element (e.g., `['sepal_length']`), accessing `feature_names[-2]` causes an IndexError.

The leaf-node entries in `feature_names_` are never actually used — line 930 guards access with `if tree_.feature[node] != _tree.TREE_UNDEFINED:`. The bug is purely in the list construction.

## Fix

**File:** `sklearn/tree/export.py` (lines 892-895)

Replace the unconditional indexing with a conditional that handles `TREE_UNDEFINED`:

```python
if feature_names:
    feature_names_ = [
        feature_names[i] if i != _tree.TREE_UNDEFINED else None
        for i in tree_.feature
    ]
else:
    feature_names_ = [
        "feature_{}".format(i) if i != _tree.TREE_UNDEFINED else None
        for i in tree_.feature
    ]
```

`_tree` is already imported at line 24.

## Test

**File:** `sklearn/tree/tests/test_export.py`

Add a test case for the single-feature scenario from the bug report:

```python
def test_export_text_single_feature():
    from sklearn.datasets import load_iris
    X, y = load_iris(return_X_y=True)
    X = X[:, 0].reshape(-1, 1)
    tree = DecisionTreeClassifier()
    tree.fit(X, y)
    result = export_text(tree, feature_names=['sepal_length'])
    assert 'sepal_length' in result
```

## Verification

```bash
python -m pytest sklearn/tree/tests/test_export.py -xvs -k "export_text"
```
