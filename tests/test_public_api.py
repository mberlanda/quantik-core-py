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
