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


def _fixture_record(index: int = 0):
    return json.loads(FIXTURE.read_text().splitlines()[index])


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
    assert SUPPORTED_CONTRACTS_RELEASE == "1.1.0"
    assert SUPPORTED_CONTRACTS["contracts_release"] == "1.1.0"
    assert SUPPORTED_CONTRACTS["selfplay"] == "selfplay.v1"
    assert SUPPORTED_CONTRACTS["action_index"] == "action-index.v1"
    assert SUPPORTED_CONTRACTS["opening_book"] == "opening-book.v1"
    assert SUPPORTED_CONTRACTS["opening_book_summary"] == "opening-book-summary.v1"
    assert SUPPORTED_CONTRACTS["observation"] == "observation.v1"
    assert SUPPORTED_CONTRACTS["game_result"] == "game-result.v1"
    assert SUPPORTED_CONTRACTS["model_checkpoint"] == "model-checkpoint.v1"


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


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("game_id", True, "game_id must be an integer"),
        ("game_id", -1, "game_id must be non-negative"),
        ("ply", -1, "ply must be non-negative"),
        ("side_to_move", 2, "side_to_move must be 0 or 1"),
        ("value", True, "value must be numeric"),
    ],
)
def test_parse_selfplay_row_rejects_invalid_scalar_fields(field, value, message):
    record = _fixture_record()
    record[field] = value

    with pytest.raises(ValueError, match=message):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_non_string_qfen():
    record = _fixture_record()
    record["qfen"] = 123

    with pytest.raises(ValueError, match="qfen must be a string"):
        parse_selfplay_row(record)


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        ([], "policy must be a non-empty list"),
        ("bad", "policy must be a non-empty list"),
        ([123], r"policy\[0\] must be an object"),
        ([{"shape": 4, "position": 0, "visits": 1}], r"policy\[0\].shape"),
        ([{"shape": 0, "position": 16, "visits": 1}], r"policy\[0\].position"),
        ([{"shape": 0, "position": 0, "visits": 0}], r"policy\[0\].visits"),
    ],
)
def test_parse_selfplay_row_rejects_invalid_policy_shapes(policy, message):
    record = _fixture_record()
    record["policy"] = policy

    with pytest.raises(ValueError, match=message):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_zero_value():
    record = _fixture_record()
    record["value"] = 0.0

    with pytest.raises(ValueError, match="value must be exactly"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_schema_mismatch():
    record = _fixture_record()
    record["schema"] = "selfplay.v2"

    with pytest.raises(ValueError, match="schema must be selfplay.v1"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_contract_version_mismatch():
    record = _fixture_record()
    record["contract_version"] = "9.9.9"

    with pytest.raises(ValueError, match="contract_version must match"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_side_to_move_mismatch():
    record = _fixture_record()
    record["side_to_move"] = 1

    with pytest.raises(ValueError, match="side_to_move does not match"):
        parse_selfplay_row(record)


def test_parse_selfplay_row_rejects_illegal_policy_action():
    record = _fixture_record(1)
    record["policy"] = [{"shape": 0, "position": 1, "visits": 1}]

    with pytest.raises(ValueError, match="policy action is not legal"):
        parse_selfplay_row(record)


def test_load_selfplay_jsonl_skips_blank_lines(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text("\n" + FIXTURE.read_text() + "\n", encoding="utf-8")

    assert len(load_selfplay_jsonl(path)) == 2


def test_load_selfplay_jsonl_reports_bad_json_line(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text('{"bad"\n', encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON on line 1"):
        load_selfplay_jsonl(path)


def test_load_selfplay_jsonl_rejects_non_object_line(tmp_path):
    path = tmp_path / "rows.jsonl"
    path.write_text("[1, 2, 3]\n", encoding="utf-8")

    with pytest.raises(ValueError, match="line 1 must contain a JSON object"):
        load_selfplay_jsonl(path)


def test_load_selfplay_jsonl_wraps_invalid_row_with_line_number(tmp_path):
    path = tmp_path / "rows.jsonl"
    record = _fixture_record()
    record["value"] = 0.0
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid self-play row on line 1"):
        load_selfplay_jsonl(path)


def test_qfen_to_tensor_rejects_invalid_side_to_move():
    with pytest.raises(ValueError, match="side_to_move must be 0 or 1"):
        qfen_to_tensor("..../..../..../....", side_to_move=2)


def test_policy_visits_to_distribution_rejects_non_positive_visits():
    with pytest.raises(ValueError, match="policy visits must be positive"):
        policy_visits_to_distribution([PolicyVisit(shape=0, position=0, visits=0)])


def test_policy_visits_to_distribution_rejects_empty_policy():
    with pytest.raises(ValueError, match="policy must contain at least one visit"):
        policy_visits_to_distribution([])
