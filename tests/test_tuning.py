"""Tests for the solver-labeled weight-fitting pipeline under `tuning/`.

The dataset build itself (which runs the exact solver hundreds of times) is
too slow for the unit suite, so these tests exercise the pure pieces: the
feature/evaluate identity, the deterministic logistic-regression fit, and
`EvalConfig.load` reading fitted weights from JSON.
"""

import json

import numpy as np
import pytest

from quantik_core import State
from quantik_core.evaluation import EvalConfig, evaluate, features
from tuning.fit_weights import fit, sign_accuracy


def test_features_match_evaluate_dot():
    bb = State.from_qfen("AbC./..../d..B/...a").bb
    cfg = EvalConfig()
    assert evaluate(bb, 0, cfg) == pytest.approx(float(cfg.weights @ features(bb, 0)))


def test_fit_is_reproducible():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(200, 6))
    y = np.where(X[:, 0] - X[:, 1] > 0, 1, -1)
    w1 = fit(X, y, seed=42)
    w2 = fit(X, y, seed=42)
    assert np.allclose(w1, w2)


def test_fit_separates_simple_signal():
    rng = np.random.default_rng(1)
    X = rng.normal(size=(500, 6))
    y = np.where(X[:, 0] - X[:, 1] > 0, 1, -1)
    w = fit(X, y, seed=0)
    assert sign_accuracy(w, X, y) > 0.9


def test_sign_accuracy_perfect_and_zero():
    X = np.array([[1.0, 0, 0, 0, 0, 0], [-1.0, 0, 0, 0, 0, 0]])
    y = np.array([1, -1])
    w = np.array([1.0, 0, 0, 0, 0, 0])
    assert sign_accuracy(w, X, y) == pytest.approx(1.0)
    assert sign_accuracy(-w, X, y) == pytest.approx(0.0)


def test_evalconfig_load_from_json(tmp_path):
    p = tmp_path / "weights.json"
    p.write_text(json.dumps({"weights": [1, 2, 3, 4, 5, 6], "win": 12345}))
    cfg = EvalConfig.load(p)
    assert np.allclose(cfg.weights, [1, 2, 3, 4, 5, 6])
    assert cfg.win == pytest.approx(12345)


def test_evalconfig_load_missing_returns_seeded(tmp_path):
    cfg = EvalConfig.load(tmp_path / "does_not_exist.json")
    assert np.allclose(cfg.weights, [100, -100, 20, 3, 2, 0])
    assert cfg.win == pytest.approx(10_000)
