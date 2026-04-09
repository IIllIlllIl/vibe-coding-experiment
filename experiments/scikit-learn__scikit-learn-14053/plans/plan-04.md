# Fix IndexError in `export_text` with single-feature trees

## Context

`export_text` crashes with `IndexError: list index out of range` when the decision tree has only one feature and `feature_names` is provided. This is scikit-learn issue #14053.

**Root cause:** In `sklearn/tree/export.py:893`, the list comprehension `[feature_names[i] for i in tree_.feature]` iterates over ALL nodes, including leaf nodes where `tree_.feature` is `-2` (`TREE_UNDEFINED`). For a single-feature tree, `feature_names[-2]` on a length-1 list raises IndexError. For multi-feature trees, `feature_names[-2]` silently returns a wrong value — a latent bug.

Note: the `else` branch (line 895) has the same issue but doesn't crash because `"feature_{}".format(-2)` is valid — it just produces a meaningless string like `"feature_-2"`.

## Plan

### 1. Fix the list comprehension in `export_text`

**File:** `sklearn/tree/export.py` (lines 892-895)

Replace:
```python
if feature_names:
    feature_names_ = [feature_names[i] for i in tree_.feature]
else:
    feature_names_ = ["feature_{}".format(i) for i in tree_.feature]
```

With:
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

The `None` entries for leaf nodes are never accessed — the recurse function (line 930) already checks `tree_.feature[node] != _tree.TREE_UNDEFINED` before using `feature_names_[node]`.

### 2. Add a test for single-feature trees

**File:** `sklearn/tree/tests/test_export.py`

Add a test that creates a `DecisionTreeClassifier` with a single feature, calls `export_text` with `feature_names`, and verifies it completes without error and produces valid output.

## Verification

Run the test:
```
python -m pytest sklearn/tree/tests/test_export.py -xvs -k "single_feature or test_export_text"
```

Also run the reproducer from the issue:
```python
from sklearn.tree import DecisionTreeClassifier
from sklearn.tree.export import export_text
from sklearn.datasets import load_iris

X, y = load_iris(return_X_y=True)
X = X[:, 0].reshape(-1, 1)
tree = DecisionTreeClassifier()
tree.fit(X, y)
print(export_text(tree, feature_names=['sepal_length']))
```
