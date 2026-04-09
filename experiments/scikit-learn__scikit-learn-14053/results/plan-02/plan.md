# Fix IndexError in `export_text` with single-feature trees

## Context

`export_text` crashes with `IndexError: list index out of range` when the tree is trained on a single feature and `feature_names` is provided. This is because `tree_.feature` contains `-2` (`TREE_UNDEFINED`) for leaf nodes, and on line 893 the code does `feature_names[i] for i in tree_.feature`, which tries `feature_names[-2]` — invalid for a 1-element list.

## Fix

**File:** `sklearn/tree/export.py` (lines 892–895)

Replace both list comprehensions to guard against `TREE_UNDEFINED`:

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

The leaf-node entries are never accessed (line 930 guards with `tree_.feature[node] != _tree.TREE_UNDEFINED`), so the `None` sentinel is safe.

## Test

**File:** `sklearn/tree/tests/test_export.py`

Add a test reproducing the reported issue:

```python
def test_export_text_single_feature():
    from sklearn.datasets import load_iris
    X, y = load_iris(return_X_y=True)
    X = X[:, 0].reshape(-1, 1)
    tree = DecisionTreeClassifier()
    tree.fit(X, y)
    output = export_text(tree, feature_names=['sepal_length'])
    assert 'sepal_length' in output
```

## Verification

```bash
python -m pytest sklearn/tree/tests/test_export.py -xvs -k "export_text"
```
