import json
from pathlib import Path

import numpy as np
import pytest

from quantik_core import SUPPORTED_CONTRACTS, SUPPORTED_CONTRACTS_RELEASE
from quantik_core.ml_data import (
    PolicyVisit,
    load_selfplay_jsonl,
    parse_selfplay_row,
    policy_visits_to_distribution,
    qfen_to_tensor,
)

FIXTURE = Path(__file__).parent / "fixtures" / "selfplay_v1.jsonl"


def test_load_selfplay_jsonl_fixture():
    rows = load_selfplay_jsonl(FIXTURE)

    assert len(rows) == 2
    assert rows[0].game_id == 0
    assert rows[0].ply == 0
    assert rows[0].qfen == "..../..../..../...."
    assert rows[0].side_to_move == 0
    assert rows[0].value == 1.0
    assert rows[0].policy == (
        PolicyVisit(shape=0, position=0, visits=3),
        PolicyVisit(shape=1, position=5, visits=1),
    )


def test_supported_contracts_are_declared():
    assert SUPPORTED_CONTRACTS_RELEASE == "1.0.0"
    assert SUPPORTED_CONTRACTS["contracts_release"] == "1.0.0"
    assert SUPPORTED_CONTRACTS["selfplay"] == "selfplay.v1"
    assert SUPPORTED_CONTRACTS["action_index"] == "action-index.v1"


def test_qfen_to_tensor_channel_layout():
    tensor = qfen_to_tensor("A.../.b../..../....", side_to_move=1)

    assert tensor.shape == (9, 4, 4)
    assert tensor.dtype == np.float32
    assert tensor[0, 0, 0] == 1.0
    assert tensor[5, 1, 1] == 1.0
    assert tensor[:8].sum() == 2.0
    assert np.all(tensor[8] == 1.0)


def test_policy_visits_to_distribution_uses_shape_major_action_index():
    distribution = policy_visits_to_distribution(
        [PolicyVisit(shape=0, position=0, visits=3), PolicyVisit(1, 5, 1)]
    )

    assert distribution.shape == (64,)
    assert distribution[0] == pytest.approx(0.75)
    assert distribution[21] == pytest.approx(0.25)
    assert distribution.sum() == pytest.approx(1.0)


def test_parse_selfplay_row_rejects_zero_value():
    record = json.loads(FIXTURE.read_text().splitlines()[0])
    record["value"] = 0.0

    with pytest.raises(ValueError, match="value must be exactly"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_schema_mismatch():
    record = json.loads(FIXTURE.read_text().splitlines()[0])
    record["schema"] = "selfplay.v2"

    with pytest.raises(ValueError, match="schema must be selfplay.v1"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_contract_version_mismatch():
    record = json.loads(FIXTURE.read_text().splitlines()[0])
    record["contract_version"] = "9.9.9"

    with pytest.raises(ValueError, match="contract_version must match"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_side_to_move_mismatch():
    record = json.loads(FIXTURE.read_text().splitlines()[0])
    record["side_to_move"] = 1

    with pytest.raises(ValueError, match="side_to_move does not match"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_illegal_policy_action():
    record = json.loads(FIXTURE.read_text().splitlines()[1])
    record["policy"] = [{"shape": 0, "position": 1, "visits": 1}]

    with pytest.raises(ValueError, match="policy action is not legal"):
        parse_selfplay_row(record)
