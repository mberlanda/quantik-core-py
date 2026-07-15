import json
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
import tomllib

import quantik_core.api_portability_report as apr
from quantik_core.api_portability_report import build_report, main


def make_contracts_root(tmp_path: Path) -> Path:
    contracts_root = tmp_path / "contracts"
    fixture_dir = contracts_root / "fixtures" / "api-portability"
    fixture_dir.mkdir(parents=True)
    (contracts_root / "VERSION").write_text("1.1.0\n", encoding="utf-8")
    (contracts_root / "contracts.json").write_text(
        json.dumps(
            {
                "release_version": "1.1.0",
                "contracts": {
                    "qfen": {"id": "qfen.v1"},
                    "bitboard": {"id": "bitboard.v1"},
                    "action_index": {"id": "action-index.v1"},
                },
            }
        ),
        encoding="utf-8",
    )
    (fixture_dir / "game-state-v1.json").write_text(
        json.dumps(
            {
                "schema": "api-portability-fixtures.v1",
                "contract_version": "1.1.0",
                "game_state_cases": [
                    {
                        "case_id": "empty-board",
                        "qfen": "..../..../..../....",
                        "move": {"shape": 0, "position": 0},
                    },
                    {
                        "case_id": "single-p0-corner",
                        "qfen": "A.../..../..../....",
                        "move": {"shape": 1, "position": 5},
                    },
                    {
                        "case_id": "single-p0-occupied-corner",
                        "qfen": "A.../..../..../....",
                        "move": {"shape": 1, "position": 0},
                    },
                    {
                        "case_id": "mixed-asymmetric",
                        "qfen": "Ab../..c./...D/....",
                        "move": {"shape": 2, "position": 12},
                    },
                    {
                        "case_id": "stalemate-p1-blocked",
                        "qfen": "A..C/bbd./CD.A/.adB",
                        "move": {"shape": 0, "position": 0},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return contracts_root


def fixture_path(contracts_root: Path) -> Path:
    return contracts_root / "fixtures" / "api-portability" / "game-state-v1.json"


def load_fixture(contracts_root: Path) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(fixture_path(contracts_root).read_text(encoding="utf-8")),
    )


def write_fixture(contracts_root: Path, fixture: dict[str, Any]) -> None:
    fixture_path(contracts_root).write_text(json.dumps(fixture), encoding="utf-8")


def test_api_portability_report_cli_writes_normalized_report(tmp_path: Path) -> None:
    output = tmp_path / "python-api-portability-report.json"
    contracts_root = make_contracts_root(tmp_path)

    exit_code = main(["--contracts-root", str(contracts_root), "--output", str(output)])

    assert exit_code == 0
    raw = output.read_text(encoding="utf-8")
    assert raw.endswith("\n")
    report = json.loads(raw)
    assert report["schema"] == "api-portability-report.v1"
    assert report["contracts_release"] == "1.1.0"
    assert report["implementation"] == {
        "language": "python",
        "package": "quantik-core",
        "version": "1.1.0",
    }
    assert report["contract_ids"] == {
        "qfen": "qfen.v1",
        "bitboard": "bitboard.v1",
        "action_index": "action-index.v1",
    }
    assert [case["case_id"] for case in report["cases"]] == [
        "empty-board",
        "mixed-asymmetric",
        "single-p0-corner",
        "single-p0-occupied-corner",
        "stalemate-p1-blocked",
    ]

    empty, mixed, single, occupied, stalemate = report["cases"]
    assert empty == {
        "case_id": "empty-board",
        "qfen": "..../..../..../....",
        "bitboards": [0, 0, 0, 0, 0, 0, 0, 0],
        "side_to_move": 0,
        "canonical_qfen": "..../..../..../....",
        "canonical_key": "010200000000000000000000000000000000",
        "orbit_size": 1,
        "legal_action_mask": "0xffffffffffffffff",
        "legal_action_indices": list(range(64)),
        "terminal": False,
        "winner": "none",
        "move": {
            "shape": 0,
            "position": 0,
            "action_index": 0,
            "is_legal": True,
            "after_qfen": "A.../..../..../....",
        },
    }
    assert mixed["case_id"] == "mixed-asymmetric"
    assert mixed["qfen"] == "Ab../..c./...D/...."
    assert mixed["bitboards"] == [1, 0, 0, 2048, 0, 2, 64, 0]
    assert mixed["side_to_move"] == 0
    assert mixed["canonical_qfen"] == "..aD/.b../C.../...."
    assert mixed["canonical_key"] == "010200000000000108000400200000000000"
    assert mixed["orbit_size"] == 192
    assert mixed["legal_action_mask"] == "0xf7bcb300d580f7bc"
    assert mixed["legal_action_indices"] == [
        2,
        3,
        4,
        5,
        7,
        8,
        9,
        10,
        12,
        13,
        14,
        15,
        23,
        24,
        26,
        28,
        30,
        31,
        40,
        41,
        44,
        45,
        47,
        50,
        51,
        52,
        53,
        55,
        56,
        57,
        58,
        60,
        61,
        62,
        63,
    ]
    assert mixed["terminal"] is False
    assert mixed["winner"] == "none"
    assert mixed["move"] == {
        "shape": 2,
        "position": 12,
        "action_index": 44,
        "is_legal": True,
        "after_qfen": "Ab../..c./...D/C...",
    }

    assert single["case_id"] == "single-p0-corner"
    assert single["qfen"] == "A.../..../..../...."
    assert single["bitboards"] == [1, 0, 0, 0, 0, 0, 0, 0]
    assert single["side_to_move"] == 1
    assert single["canonical_qfen"] == "..../..../..../D..."
    assert single["canonical_key"] == "010200000000000000100000000000000000"
    assert single["orbit_size"] == 16
    assert single["legal_action_mask"] == "0xfffefffefffeeec0"
    assert single["legal_action_indices"] == [
        6,
        7,
        9,
        10,
        11,
        13,
        14,
        15,
        17,
        18,
        19,
        20,
        21,
        22,
        23,
        24,
        25,
        26,
        27,
        28,
        29,
        30,
        31,
        33,
        34,
        35,
        36,
        37,
        38,
        39,
        40,
        41,
        42,
        43,
        44,
        45,
        46,
        47,
        49,
        50,
        51,
        52,
        53,
        54,
        55,
        56,
        57,
        58,
        59,
        60,
        61,
        62,
        63,
    ]
    assert single["terminal"] is False
    assert single["winner"] == "none"
    assert single["move"] == {
        "shape": 1,
        "position": 5,
        "action_index": 21,
        "is_legal": True,
        "after_qfen": "A.../.b../..../....",
    }

    assert occupied["case_id"] == "single-p0-occupied-corner"
    assert occupied["move"] == {
        "shape": 1,
        "position": 0,
        "action_index": 16,
        "is_legal": False,
        "after_qfen": None,
    }

    assert stalemate["case_id"] == "stalemate-p1-blocked"
    assert stalemate["side_to_move"] == 1
    assert stalemate["legal_action_indices"] == []
    assert stalemate["legal_action_mask"] == "0x0000000000000000"
    assert stalemate["terminal"] is True
    assert stalemate["winner"] == "player0"
    assert stalemate["move"] == {
        "shape": 0,
        "position": 0,
        "action_index": 0,
        "is_legal": False,
        "after_qfen": None,
    }


def test_api_portability_report_module_execution(tmp_path: Path) -> None:
    output = tmp_path / "module-report.json"
    contracts_root = make_contracts_root(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quantik_core.api_portability_report",
            "--contracts-root",
            str(contracts_root),
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(output.read_text(encoding="utf-8"))["schema"] == (
        "api-portability-report.v1"
    )


def test_api_portability_report_console_script_is_registered() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    pyproject = tomllib.loads(
        (repo_root / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert pyproject["project"]["scripts"]["quantik-api-portability-report"] == (
        "quantik_core.api_portability_report:main"
    )


def test_api_portability_report_rejects_contract_version_drift(
    tmp_path: Path,
) -> None:
    contracts_root = make_contracts_root(tmp_path)
    (contracts_root / "VERSION").write_text("1.0.0\n", encoding="utf-8")

    with pytest.raises(ValueError, match="does not match"):
        build_report(contracts_root)


def test_api_portability_report_requires_version_file(tmp_path: Path) -> None:
    contracts_root = make_contracts_root(tmp_path)
    (contracts_root / "VERSION").unlink()

    with pytest.raises(ValueError, match="VERSION file is required"):
        build_report(contracts_root)

    (contracts_root / "VERSION").write_text("\n", encoding="utf-8")

    with pytest.raises(ValueError, match="VERSION must be non-empty"):
        build_report(contracts_root)


def test_api_portability_report_rejects_fixture_metadata_drift(
    tmp_path: Path,
) -> None:
    contracts_root = make_contracts_root(tmp_path)
    fixture = load_fixture(contracts_root)
    fixture["schema"] = "wrong-schema.v1"
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="schema must be api-portability-fixtures.v1"):
        build_report(contracts_root)

    fixture["schema"] = "api-portability-fixtures.v1"
    fixture["contract_version"] = "1.0.0"
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="contract_version must match 1.1.0"):
        build_report(contracts_root)


def test_api_portability_report_rejects_invalid_case_and_move(
    tmp_path: Path,
) -> None:
    contracts_root = make_contracts_root(tmp_path)
    fixture = load_fixture(contracts_root)
    fixture["game_state_cases"][0]["case_id"] = ""
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="case_id must be a non-empty string"):
        build_report(contracts_root)

    fixture["game_state_cases"][0]["case_id"] = "bad-move"
    fixture["game_state_cases"][0]["move"]["shape"] = 4
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="move.shape must be between 0 and 3"):
        build_report(contracts_root)

    fixture["game_state_cases"][0]["move"]["shape"] = True
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="move.shape must be an integer"):
        build_report(contracts_root)

    fixture["game_state_cases"][0]["move"] = {"shape": 0, "position": -1}
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="move.position must be between 0 and 15"):
        build_report(contracts_root)


def test_api_portability_report_rejects_invalid_qfen_with_case_context(
    tmp_path: Path,
) -> None:
    contracts_root = make_contracts_root(tmp_path)
    fixture = load_fixture(contracts_root)
    fixture["game_state_cases"][0]["qfen"] = "bad"
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="empty-board: qfen parse failed"):
        build_report(contracts_root)

    fixture["game_state_cases"][0]["qfen"] = 12
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="empty-board: qfen must be a string"):
        build_report(contracts_root)

    fixture["game_state_cases"][0]["qfen"] = "..../..../..../...."
    fixture["game_state_cases"][0]["move"] = "bad-move"
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="empty-board: move must be an object"):
        build_report(contracts_root)


def test_api_portability_report_rejects_empty_or_non_object_cases(
    tmp_path: Path,
) -> None:
    contracts_root = make_contracts_root(tmp_path)
    fixture = load_fixture(contracts_root)
    fixture["game_state_cases"] = []
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match="game_state_cases must be a non-empty list"):
        build_report(contracts_root)

    fixture["game_state_cases"] = ["not-an-object"]
    write_fixture(contracts_root, fixture)

    with pytest.raises(ValueError, match=r"game_state_cases\[0\] must be an object"):
        build_report(contracts_root)


def test_api_portability_report_rejects_malformed_manifest(tmp_path: Path) -> None:
    contracts_root = make_contracts_root(tmp_path)
    (contracts_root / "contracts.json").write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="expected a JSON object"):
        build_report(contracts_root)


def test_api_portability_report_rejects_missing_contract_id(tmp_path: Path) -> None:
    contracts_root = make_contracts_root(tmp_path)
    manifest = json.loads(
        (contracts_root / "contracts.json").read_text(encoding="utf-8")
    )
    del manifest["contracts"]["action_index"]
    (contracts_root / "contracts.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )

    with pytest.raises(ValueError, match="missing contract id for action_index"):
        build_report(contracts_root)


def test_api_portability_report_uses_editable_version_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    contracts_root = make_contracts_root(tmp_path)

    def missing_package(_: str) -> str:
        raise apr.PackageNotFoundError

    monkeypatch.setattr(apr, "version", missing_package)

    assert build_report(contracts_root)["implementation"]["version"] == "0+editable"


def test_api_portability_report_winner_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(apr, "check_game_winner", lambda _: apr.WinStatus.PLAYER_0_WINS)
    assert apr._winner_name((0, 0, 0, 0, 0, 0, 0, 0)) == "player0"

    monkeypatch.setattr(apr, "check_game_winner", lambda _: apr.WinStatus.PLAYER_1_WINS)
    assert apr._winner_name((0, 0, 0, 0, 0, 0, 0, 0)) == "player1"


def test_api_portability_report_rejects_valid_move_without_bitboard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class MissingBitboardValidation:
        is_valid = True
        new_bb = None

    monkeypatch.setattr(apr, "validate_move", lambda *_: MissingBitboardValidation())

    with pytest.raises(ValueError, match="valid move did not return a new bitboard"):
        apr._move_report({"shape": 0, "position": 0}, (0, 0, 0, 0, 0, 0, 0, 0), 0)
