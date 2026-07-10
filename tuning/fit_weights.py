"""Fit the evaluation weight vector against solver labels by logistic regression.

The handcrafted evaluation is linear in a 6-feature vector, so its "correct"
weights are those whose sign best predicts the exact solver outcome. We fit
them with plain-numpy logistic regression (batch gradient descent + small L2),
which is deterministic given a seed and needs no extra dependency.

Run: `python tuning/fit_weights.py` -> builds/loads `tuning/dataset.npz`,
fits, writes `tuning/weights.json`, and prints seeded-vs-fitted sign accuracy.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

import numpy as np

_TUNING_DIR = Path(__file__).resolve().parent
_DATASET_PATH = _TUNING_DIR / "dataset.npz"
_WEIGHTS_PATH = _TUNING_DIR / "weights.json"

_SEEDED_WEIGHTS = np.array([100.0, -100.0, 20.0, 3.0, 2.0, 0.0])
_WIN = 10_000.0


def _standardize(X: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Zero-mean/unit-std each feature (guard zero-variance columns)."""
    mean = X.mean(axis=0)
    std = X.std(axis=0)
    std = np.where(std < 1e-9, 1.0, std)
    return (X - mean) / std, mean, std


def fit(
    X: np.ndarray,
    y: np.ndarray,
    seed: int,
    iters: int = 4000,
    lr: float = 0.1,
    l2: float = 1e-3,
) -> np.ndarray:
    """Fit length-6 weights so that `sign(w @ features)` predicts the label.

    `y` uses the sign convention +1 (win) / -1 (loss); rows labeled 0 (draw)
    are dropped. Returns weights in the ORIGINAL (unstandardized) feature
    space, so `w @ features(bb, player)` is directly usable as an evaluation.
    """
    mask = y != 0
    Xf = np.asarray(X, dtype=np.float64)[mask]
    yf = np.asarray(y, dtype=np.float64)[mask]
    labels01 = (yf > 0).astype(np.float64)

    if len(yf) == 0:
        return _SEEDED_WEIGHTS.copy()

    Xs, mean, std = _standardize(Xf)
    rng = np.random.default_rng(seed)
    w = rng.normal(scale=0.01, size=Xs.shape[1])
    b = 0.0
    n = len(yf)
    for _ in range(iters):
        z = Xs @ w + b
        p = 1.0 / (1.0 + np.exp(-z))
        grad_w = Xs.T @ (p - labels01) / n + l2 * w
        grad_b = float((p - labels01).mean())
        w -= lr * grad_w
        b -= lr * grad_b

    # Map weights back to the original feature space (drop the intercept: the
    # evaluation is a pure dot product, and a constant offset never changes
    # the argmax over sibling moves).
    return w / std


def sign_accuracy(w: np.ndarray, X: np.ndarray, y: np.ndarray) -> float:
    """Fraction of non-draw rows where `sign(w @ x)` matches `sign(y)`."""
    mask = np.asarray(y) != 0
    if not mask.any():
        return 0.0
    scores = np.asarray(X)[mask] @ np.asarray(w)
    preds = np.sign(scores)
    truth = np.sign(np.asarray(y)[mask])
    return float((preds == truth).mean())


def main(seed: int = 0) -> None:
    if not _DATASET_PATH.exists():
        from tuning.build_dataset import main as build_main

        build_main()
    data = np.load(_DATASET_PATH)
    X, y = data["X"], data["y"]

    w = fit(X, y, seed=seed)
    seeded_acc = sign_accuracy(_SEEDED_WEIGHTS, X, y)
    fitted_acc = sign_accuracy(w, X, y)

    payload = {
        "weights": [float(v) for v in w],
        "win": _WIN,
        "sign_accuracy": fitted_acc,
        "n": int((y != 0).sum()),
    }
    _WEIGHTS_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"seeded sign_accuracy: {seeded_acc:.3f}")
    print(f"fitted sign_accuracy: {fitted_acc:.3f}  (n={payload['n']})")
    print(f"fitted weights: {payload['weights']}")
    print(f"wrote {_WEIGHTS_PATH}")


if __name__ == "__main__":
    main()
