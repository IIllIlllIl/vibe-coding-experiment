# Fix IndexError in `export_text` with single feature

## Context
`export_text` crashes with `IndexError: list index out of range` when the tree is trained on a single feature and `feature_names` is provided. This is scikit-learn issue #14053.

## Root Cause
In `sklearn/tree/export.py`, line 893:
```python
feature_names_ = [feature_names[i] for i in tree_.feature]
```

`tree_.feature` contains `TREE_UNDEFINED` (= -2) for leaf nodes. When `feature_names` has only 1 element, `feature_names[-2]` is out of range (valid negative index is only `-1`). With more features, `feature_names[-2]` wraps around harmlessly (returning the wrong name but not crashing), so the bug only manifests with a single feature.

The same issue exists in the `else` branch (line 895) where `"feature_{}".format(-2)` would produce `"feature_-2"`, which is incorrect but doesn't crash.

## Fix
In `sklearn/tree/export.py`, replace lines 892-895 with logic that handles `TREE_UNDEFINED`:

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

This is safe because `feature_names_[node]` is only accessed on line 931 when `tree_.feature[node] != _tree.TREE_UNDEFINED` (line 930 guard).

## Files to modify
- `sklearn/tree/export.py` (lines 892-895)

## Test to add
Add a test case in `sklearn/tree/tests/test_export.py` for `export_text` with a single-feature tree and explicit `feature_names`.

## Verification
```bash
python -c "
from sklearn.tree import DecisionTreeClassifier
from sklearn.tree.export import export_text
from sklearn.datasets import load_iris
X, y = load_iris(return_X_y=True)
X = X[:, 0].reshape(-1, 1)
tree = DecisionTreeClassifier().fit(X, y)
print(export_text(tree, feature_names=['sepal_length']))
"
pytest sklearn/tree/tests/test_export.py -xvs
```
