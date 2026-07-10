"""Tests for the stable top-level public API."""

from importlib.metadata import version

import quantik_core


def test_public_all_exports_are_bound():
    missing = [name for name in quantik_core.__all__ if not hasattr(quantik_core, name)]

    assert missing == []


def test_wildcard_import_contract():
    namespace = {}
    exec("from quantik_core import *", namespace)

    for name in quantik_core.__all__:
        assert name in namespace


def test_runtime_version_matches_installed_distribution():
    assert quantik_core.__version__ == version("quantik-core")


def test_minimax_and_evaluation_are_top_level_exports():
    # The classical-search engine is surfaced at the top level (unlike the
    # module-only MCTS/beam engines) as the headline classical-search API.
    for name in (
        "MinimaxEngine",
        "MinimaxConfig",
        "MinimaxResult",
        "evaluate",
        "EvalConfig",
    ):
        assert name in quantik_core.__all__
        assert hasattr(quantik_core, name)
