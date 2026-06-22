"""Tests for shared QFEN fixture consistency."""

import pytest

from quantik_core.qfen import bb_from_qfen
from tests.fixtures import CanonicalBitboardFactory, UnifiedTestCases


@pytest.mark.parametrize(
    "case", UnifiedTestCases.all_cases(), ids=lambda case: case.name
)
def test_unified_test_case_qfen_has_four_ranks_of_four_chars(case):
    ranks = case.qfen.split("/")

    assert len(ranks) == 4
    assert all(len(rank) == 4 for rank in ranks), case.qfen
    bb_from_qfen(case.qfen)


def test_canonical_fixture_factory_cases_are_consistent():
    for fixture in CanonicalBitboardFactory.all_fixtures():
        assert fixture.state.to_qfen() == fixture.qfen
        assert fixture.compact_bitboard.to_tuple() == fixture.bitboard
