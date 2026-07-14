import json
from pathlib import Path
import sys

import numpy as np
import pytest

from quantik_core import SUPPORTED_CONTRACTS, SUPPORTED_CONTRACTS_RELEASE
from quantik_core.ml_data import (
    PolicyVisit,
    load_selfplay_parquet,
    load_selfplay_jsonl,
    parse_selfplay_row,
    policy_visits_to_dense,
    policy_visits_to_distribution,
    qfen_to_tensor,
    selfplay_row_to_arrow_parquet_record,
    write_selfplay_parquet,
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
    assert SUPPORTED_CONTRACTS["arrow_parquet_selfplay"] == "arrow-parquet-selfplay.v1"
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


def test_policy_visits_to_dense_uses_arrow_parquet_physical_layout():
    dense = policy_visits_to_dense(
        [PolicyVisit(shape=0, position=0, visits=3), PolicyVisit(1, 5, 1)]
    )

    assert len(dense) == 64
    assert dense[0] == 3
    assert dense[21] == 1
    assert sum(dense) == 4


def test_selfplay_row_to_arrow_parquet_record_keeps_contract_metadata():
    row = parse_selfplay_row(_fixture_record())

    record = selfplay_row_to_arrow_parquet_record(row)

    assert record["logical_schema"] == "selfplay.v1"
    assert record["contract_version"] == SUPPORTED_CONTRACTS_RELEASE
    assert record["game_id"] == row.game_id
    assert record["bitboards"] == (0, 0, 0, 0, 0, 0, 0, 0)
    assert record["policy_visits"][0] == 3
    assert record["policy_visits"][21] == 1
    assert record["value"] == 1
    assert "policy" not in record


def test_selfplay_row_to_arrow_parquet_record_rejects_ply_outside_uint16():
    row = parse_selfplay_row(_fixture_record())
    row = type(row)(
        game_id=row.game_id,
        ply=65536,
        qfen=row.qfen,
        side_to_move=row.side_to_move,
        policy=row.policy,
        value=row.value,
    )

    with pytest.raises(ValueError, match="ply must fit in uint16"):
        selfplay_row_to_arrow_parquet_record(row)


def test_selfplay_row_to_arrow_parquet_record_rejects_non_decisive_value():
    row = parse_selfplay_row(_fixture_record())
    row = type(row)(
        game_id=row.game_id,
        ply=row.ply,
        qfen=row.qfen,
        side_to_move=row.side_to_move,
        policy=row.policy,
        value=0.0,
    )

    with pytest.raises(ValueError, match="value must be exactly"):
        selfplay_row_to_arrow_parquet_record(row)


def test_selfplay_parquet_helpers_report_missing_pyarrow(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "pyarrow", None)
    row = parse_selfplay_row(_fixture_record())

    with pytest.raises(ImportError, match=r"quantik-core\[arrow\]"):
        write_selfplay_parquet([row], tmp_path / "rows.parquet")

    with pytest.raises(ImportError, match=r"quantik-core\[arrow\]"):
        load_selfplay_parquet(tmp_path / "rows.parquet")


def test_selfplay_parquet_roundtrips_rows_and_metadata(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "rows.parquet"
    rows = load_selfplay_jsonl(FIXTURE)

    write_selfplay_parquet(rows, path)

    loaded = load_selfplay_parquet(path)
    table = pq.read_table(path)
    metadata = table.schema.metadata or {}

    assert loaded == rows
    assert metadata[b"physical_schema"] == b"arrow-parquet-selfplay.v1"
    assert metadata[b"logical_schema"] == b"selfplay.v1"
    assert metadata[b"logical_contract"] == b"selfplay.v1"
    assert metadata[b"contracts_release"] == SUPPORTED_CONTRACTS_RELEASE.encode("utf-8")
    assert metadata[b"contract_version"] == SUPPORTED_CONTRACTS_RELEASE.encode("utf-8")
    assert table.schema.field("bitboards").type == pa.list_(pa.uint16(), list_size=8)
    assert table.schema.field("policy_visits").type == pa.list_(
        pa.uint32(), list_size=64
    )


def test_load_selfplay_parquet_rejects_metadata_drift(tmp_path):
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "rows.parquet"
    row = parse_selfplay_row(_fixture_record())
    write_selfplay_parquet([row], path)

    table = pq.read_table(path)
    drifted = table.replace_schema_metadata(
        {
            **(table.schema.metadata or {}),
            b"physical_schema": b"arrow-parquet-selfplay.v2",
        }
    )
    pq.write_table(drifted, path)

    with pytest.raises(ValueError, match="physical schema metadata"):
        load_selfplay_parquet(path)


def test_load_selfplay_parquet_rejects_dense_policy_drift(tmp_path):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    path = tmp_path / "rows.parquet"
    row = parse_selfplay_row(_fixture_record())
    write_selfplay_parquet([row], path)

    table = pq.read_table(path)
    columns = []
    for name in table.column_names:
        if name == "policy_visits":
            columns.append(pa.array([[0] * 64], type=pa.list_(pa.uint32(), 64)))
        else:
            columns.append(table[name])
    pq.write_table(pa.Table.from_arrays(columns, schema=table.schema), path)

    with pytest.raises(ValueError, match="policy must contain at least one visit"):
        load_selfplay_parquet(path)


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
        (
            [
                {"shape": 0, "position": 0, "visits": 1},
                {"shape": 0, "position": 0, "visits": 2},
            ],
            r"policy\[1\] duplicates shape=0, position=0",
        ),
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


def test_policy_visits_to_dense_rejects_empty_policy():
    with pytest.raises(ValueError, match="policy must contain at least one visit"):
        policy_visits_to_dense([])
