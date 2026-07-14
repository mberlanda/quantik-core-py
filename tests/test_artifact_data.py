import json
from pathlib import Path

import pytest

from quantik_core.artifact_data import (
    GAME_RESULT_SCHEMA,
    MODEL_CHECKPOINT_SCHEMA,
    OBSERVATION_SCHEMA,
    load_game_results_jsonl,
    load_model_checkpoint_manifest,
    load_observations_jsonl,
    parse_game_result_row,
    parse_model_checkpoint_manifest,
    parse_observation_row,
)
from quantik_core.move import generate_legal_moves_list

MODEL_CHECKPOINT_FIXTURE = (
    Path(__file__).parent / "fixtures" / "model-checkpoint-v1.json"
)


def observation_record():
    visits = [0] * 64
    visits[0] = 1
    return {
        "schema": OBSERVATION_SCHEMA,
        "contract_version": "1.1.0",
        "run_id": "run-1",
        "row_id": 0,
        "position_key": "00",
        "ply": 0,
        "side_to_move": 0,
        "bitboards": [0] * 8,
        "qfen": "..../..../..../....",
        "legal_action_mask": (1 << 64) - 1,
        "engine_kind": "mcts",
        "engine_version": "0.1.0",
        "elapsed_ms": 12,
        "policy_visits": visits,
        "value": 0.25,
        "value_source": "heuristic",
        "source_confidence": 0.5,
    }


def game_result_record():
    return {
        "schema": GAME_RESULT_SCHEMA,
        "contract_version": "1.1.0",
        "game_id": "game-1",
        "started_at": "2026-07-14T00:00:00+0200",
        "p0_engine_kind": "mcts",
        "p0_engine_version": "0.1.0",
        "p1_engine_kind": "minimax",
        "p1_engine_version": "0.1.0",
        "initial_position_key": "00",
        "winner": 1,
        "plies": 3,
        "terminal_reason": "win_condition_or_no_legal_moves",
        "move_action_indices": [0, 17, 2],
        "run_id": "run-1",
    }


def model_manifest_record():
    return {
        "schema": MODEL_CHECKPOINT_SCHEMA,
        "contract_version": "1.1.0",
        "model_id": "quantik-qnue-small",
        "model_family": "qnue",
        "created_at": "2026-07-14T00:00:00+0200",
        "input_contracts": ["bitboard.v1", "action-index.v1"],
        "output_contract": "policy-value.v1",
        "weights_format": "safetensors",
        "weights_hash": "sha256:abc",
        "size_bytes": 42,
        "training_data_manifest": "sha256:def",
        "calibration_report": "sha256:ghi",
    }


def model_manifest_fixture_record():
    return json.loads(MODEL_CHECKPOINT_FIXTURE.read_text(encoding="utf-8"))


def test_parse_observation_row_accepts_valid_contract_row():
    row = parse_observation_row(observation_record())

    assert row.run_id == "run-1"
    assert row.row_id == 0
    assert row.bitboards == (0, 0, 0, 0, 0, 0, 0, 0)
    assert row.policy_visits[0] == 1
    assert row.legal_action_mask == (1 << 64) - 1


def test_parse_observation_row_rejects_bad_legal_action_mask():
    record = observation_record()
    record["legal_action_mask"] = 1

    with pytest.raises(ValueError, match="legal_action_mask does not match bitboards"):
        parse_observation_row(record)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("row_id", True, "row_id must be an integer"),
        ("row_id", -1, "row_id must be non-negative"),
        ("ply", -1, "ply must be non-negative"),
        ("side_to_move", 2, "side_to_move must be 0 or 1"),
        ("source_confidence", True, "source_confidence must be numeric"),
        ("source_confidence", 1.5, "source_confidence must be in 0.0..1.0"),
        ("run_id", "", "run_id must be a non-empty string"),
        ("legal_action_mask", -1, "legal_action_mask must be a uint64"),
    ],
)
def test_parse_observation_row_rejects_invalid_scalar_fields(field, value, message):
    record = observation_record()
    record[field] = value

    with pytest.raises(ValueError, match=message):
        parse_observation_row(record)


@pytest.mark.parametrize(
    ("bitboards", "message"),
    [
        ([0] * 7, "bitboards must contain exactly 8 uint16 planes"),
        ([False] + [0] * 7, r"bitboards\[0\] must be an integer"),
        ([0x10000] + [0] * 7, r"bitboards\[0\] must be in 0..65535"),
    ],
)
def test_parse_observation_row_rejects_invalid_bitboards(bitboards, message):
    record = observation_record()
    record["bitboards"] = bitboards

    with pytest.raises(ValueError, match=message):
        parse_observation_row(record)


@pytest.mark.parametrize(
    ("policy_visits", "message"),
    [
        ([1] * 63, "policy_visits must contain exactly 64 integers"),
        ([False] + [0] * 63, r"policy_visits\[0\] must be an integer"),
        ([-1] + [0] * 63, r"policy_visits\[0\] must be non-negative"),
        ([0] * 64, "policy_visits must contain at least one visit"),
    ],
)
def test_parse_observation_row_rejects_invalid_policy_visits(policy_visits, message):
    record = observation_record()
    record["policy_visits"] = policy_visits

    with pytest.raises(ValueError, match=message):
        parse_observation_row(record)


def test_parse_observation_row_rejects_schema_and_version_mismatch():
    record = observation_record()
    record["schema"] = "other.v1"
    with pytest.raises(ValueError, match="schema must be observation.v1"):
        parse_observation_row(record)

    record = observation_record()
    record["contract_version"] = "0.0.0"
    with pytest.raises(ValueError, match="contract_version must match"):
        parse_observation_row(record)


def test_parse_observation_row_rejects_side_to_move_mismatch():
    record = observation_record()
    record["bitboards"] = [1, 0, 0, 0, 0, 0, 0, 0]
    record["qfen"] = None

    with pytest.raises(ValueError, match="side_to_move does not match bitboards"):
        parse_observation_row(record)


def test_parse_observation_row_rejects_policy_on_illegal_action():
    bitboards = (1, 0, 0, 0, 0, 0, 0, 0)
    legal_action_mask = 0
    for move in generate_legal_moves_list(bitboards):
        legal_action_mask |= 1 << (move.shape * 16 + move.position)

    record = observation_record()
    record["bitboards"] = list(bitboards)
    record["qfen"] = None
    record["side_to_move"] = 1
    record["legal_action_mask"] = legal_action_mask
    record["policy_visits"] = [0] * 64
    record["policy_visits"][0] = 1

    with pytest.raises(ValueError, match=r"policy_visits\[0\] is not legal"):
        parse_observation_row(record)


def test_parse_observation_row_rejects_bad_qfen_match():
    record = observation_record()
    record["qfen"] = "A.../..../..../...."

    with pytest.raises(ValueError, match="qfen does not match bitboards"):
        parse_observation_row(record)


def test_parse_game_result_row_accepts_valid_contract_row():
    row = parse_game_result_row(game_result_record())

    assert row.game_id == "game-1"
    assert row.p0_engine_kind == "mcts"
    assert row.p1_engine_kind == "minimax"
    assert row.winner == 1
    assert row.move_action_indices == (0, 17, 2)


def test_parse_game_result_row_rejects_ply_mismatch():
    record = game_result_record()
    record["plies"] = 2

    with pytest.raises(ValueError, match="plies must match"):
        parse_game_result_row(record)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema", "other.v1", "schema must be game-result.v1"),
        ("winner", 2, "winner must be 0 or 1"),
        ("plies", -1, "plies must be non-negative"),
        ("game_id", "", "game_id must be a non-empty string"),
    ],
)
def test_parse_game_result_row_rejects_invalid_scalar_fields(field, value, message):
    record = game_result_record()
    record[field] = value

    with pytest.raises(ValueError, match=message):
        parse_game_result_row(record)


@pytest.mark.parametrize(
    ("moves", "message"),
    [
        ("0,1,2", "move_action_indices must be a list"),
        ([True, 1, 2], r"move_action_indices\[0\] must be an integer"),
        ([64, 1, 2], r"move_action_indices\[0\] must be in 0..63"),
    ],
)
def test_parse_game_result_row_rejects_invalid_moves(moves, message):
    record = game_result_record()
    record["move_action_indices"] = moves

    with pytest.raises(ValueError, match=message):
        parse_game_result_row(record)


def test_parse_model_checkpoint_manifest_accepts_valid_manifest():
    manifest = parse_model_checkpoint_manifest(model_manifest_record())

    assert manifest.schema == MODEL_CHECKPOINT_SCHEMA
    assert manifest.contract_version == "1.1.0"
    assert manifest.model_id == "quantik-qnue-small"
    assert manifest.created_at == "2026-07-14T00:00:00+0200"
    assert manifest.input_contracts == ("bitboard.v1", "action-index.v1")
    assert manifest.size_bytes == 42


def test_parse_model_checkpoint_manifest_accepts_opening_book_summary_input():
    record = model_manifest_record()
    record["input_contracts"] = ["opening-book-summary.v1"]

    manifest = parse_model_checkpoint_manifest(record)

    assert manifest.input_contracts == ("opening-book-summary.v1",)


def test_load_model_checkpoint_manifest_fixture():
    manifest = load_model_checkpoint_manifest(MODEL_CHECKPOINT_FIXTURE)

    assert manifest.model_id == "quantik-policy-value-fixture"
    assert manifest.input_contracts == ("observation.v1",)
    assert manifest.weights_format == "safetensors"
    assert manifest.feature_hash == "sha256:abcdef0123456789"
    assert manifest.quantization == "float32"
    assert manifest.parameter_count == 123456
    assert manifest.architecture == "tiny-transformer"
    assert manifest.legal_action_mask_required is True
    assert manifest.recommended_engine_order == ("rust", "python")
    assert (
        manifest.notes
        == "Small metadata-only fixture for model-checkpoint.v1 parser tests."
    )


def test_parse_model_checkpoint_manifest_rejects_empty_input_contracts():
    record = model_manifest_record()
    record["input_contracts"] = []

    with pytest.raises(ValueError, match="input_contracts must be a non-empty list"):
        parse_model_checkpoint_manifest(record)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("schema", "other.v1", "schema must be model-checkpoint.v1"),
        (
            "contract_version",
            "1.0.0",
            "contract_version must match supported contracts release 1.1.0",
        ),
        ("model_id", "   ", "model_id must be a non-empty string"),
        ("input_contracts", "bitboard.v1", "input_contracts must be a non-empty list"),
        (
            "input_contracts",
            ["bitboard.v1", "   "],
            r"input_contracts\[1\] must be a non-empty string",
        ),
        (
            "input_contracts",
            ["unknown.v1"],
            "unsupported input contract: unknown.v1",
        ),
        ("size_bytes", 0, "size_bytes must be positive"),
        ("weights_format", "", "weights_format must be a non-empty string"),
        ("weights_format", "pickle", "unsupported weights_format: pickle"),
        ("feature_hash", "   ", "feature_hash must be a non-empty string"),
        ("parameter_count", 0, "parameter_count must be positive"),
        (
            "legal_action_mask_required",
            "yes",
            "legal_action_mask_required must be a boolean",
        ),
        (
            "recommended_engine_order",
            ["rust", "   "],
            r"recommended_engine_order\[1\] must be a non-empty string",
        ),
    ],
)
def test_parse_model_checkpoint_manifest_rejects_invalid_fields(field, value, message):
    record = model_manifest_record()
    record[field] = value

    with pytest.raises(ValueError, match=message):
        parse_model_checkpoint_manifest(record)


def test_jsonl_loaders_report_line_numbers(tmp_path):
    observations = tmp_path / "observations.jsonl"
    observations.write_text(json.dumps(observation_record()) + "\n", encoding="utf-8")
    assert len(load_observations_jsonl(observations)) == 1

    games = tmp_path / "games.jsonl"
    bad_game = game_result_record()
    bad_game["winner"] = 3
    games.write_text(json.dumps(bad_game) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid game-result row on line 1"):
        load_game_results_jsonl(games)


def test_jsonl_loader_rejects_bad_json_and_non_object_rows(tmp_path):
    observations = tmp_path / "observations.jsonl"
    observations.write_text("{bad json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="invalid JSON on line 1"):
        load_observations_jsonl(observations)

    observations.write_text("[1, 2, 3]\n", encoding="utf-8")
    with pytest.raises(ValueError, match="line 1 must contain a JSON object"):
        load_observations_jsonl(observations)

    bad_observation = observation_record()
    bad_observation["row_id"] = -1
    observations.write_text(json.dumps(bad_observation), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid observation row on line 1"):
        load_observations_jsonl(observations)


def test_load_model_checkpoint_manifest(tmp_path):
    path = tmp_path / "model.json"
    path.write_text(json.dumps(model_manifest_record()), encoding="utf-8")

    assert load_model_checkpoint_manifest(path).weights_format == "safetensors"


def test_load_model_checkpoint_manifest_rejects_non_object(tmp_path):
    path = tmp_path / "model.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")

    with pytest.raises(
        ValueError, match="model checkpoint manifest must be a JSON object"
    ):
        load_model_checkpoint_manifest(path)
