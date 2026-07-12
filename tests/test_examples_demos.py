"""Tests for the runnable example scripts under examples/.

These import the demo modules (both are guarded by `if __name__ ==
"__main__":`, so import has no side effects) and pin the pure
formatting helpers they expose, so display bugs like ignoring
`move.player` don't silently regress.
"""

import importlib.util
import sys
from pathlib import Path

import pytest

from quantik_core import Move

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"


def _load_demo_module(filename: str):
    module_name = f"_examples_{filename.removesuffix('.py')}"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, EXAMPLES_DIR / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mcts_demo():
    return _load_demo_module("mcts_demo.py")


@pytest.fixture(scope="module")
def beam_search_demo():
    return _load_demo_module("beam_search_demo.py")


class TestMCTSDemoFormatMove:
    """Pins the player-0/player-1 QFEN case convention for mcts_demo.py."""

    def test_player_0_move_is_uppercase(self, mcts_demo):
        move = Move(player=0, shape=0, position=1)

        formatted = mcts_demo.format_move(move)

        assert formatted.startswith("A ")
        assert "a " not in formatted

    def test_player_1_move_is_lowercase(self, mcts_demo):
        move = Move(player=1, shape=1, position=11)

        formatted = mcts_demo.format_move(move)

        # Mutation guard: prior to the fix this always rendered "B",
        # ignoring move.player entirely.
        assert formatted.startswith("b ")
        assert "B " not in formatted

    def test_includes_row_col_and_position(self, mcts_demo):
        move = Move(player=0, shape=2, position=11)

        formatted = mcts_demo.format_move(move)

        assert "(2, 3)" in formatted
        assert "[pos 11]" in formatted


class TestBeamSearchDemoFormatMove:
    """Same convention, pinned for the sibling demo (regression guard)."""

    def test_player_0_move_is_uppercase(self, beam_search_demo):
        move = Move(player=0, shape=0, position=1)

        formatted = beam_search_demo.format_move(move)

        assert "P0 A " in formatted

    def test_player_1_move_is_lowercase(self, beam_search_demo):
        move = Move(player=1, shape=1, position=11)

        formatted = beam_search_demo.format_move(move)

        assert "P1 b " in formatted


@pytest.fixture(scope="module")
def minimax_demo():
    return _load_demo_module("minimax_demo.py")


@pytest.fixture(scope="module")
def minimax_benchmark():
    return _load_demo_module("minimax_benchmark.py")


class TestMinimaxDemo:
    """Pins the player-aware QFEN case convention for minimax_demo.py and
    smoke-checks that the demo helpers actually run a search."""

    def test_player_0_move_is_uppercase(self, minimax_demo):
        assert minimax_demo.format_move(Move(player=0, shape=0, position=1)).startswith(
            "A "
        )

    def test_player_1_move_is_lowercase(self, minimax_demo):
        # Mutation guard: rendering that ignored move.player would print "B".
        formatted = minimax_demo.format_move(Move(player=1, shape=1, position=11))
        assert formatted.startswith("b ") and "B " not in formatted

    def test_minimax_player_returns_legal_move(self, minimax_demo):
        from quantik_core import State
        from quantik_core.move import generate_legal_moves_list

        state = State.from_qfen("AbC./..../..../....")
        select = minimax_demo.minimax_player(max_depth=2)
        move = select(state)
        assert move in generate_legal_moves_list(state.bb)

    def test_play_game_returns_a_winner(self, minimax_demo):
        from quantik_core.game_utils import WinStatus

        result = minimax_demo.play_game(
            minimax_demo.random_player(seed=1), minimax_demo.random_player(seed=2)
        )
        assert result in (WinStatus.PLAYER_0_WINS, WinStatus.PLAYER_1_WINS)


def test_minimax_benchmark_imports(minimax_benchmark):
    # Importing exercises the module-level `from minimax_demo import ...`; the
    # heavy work is guarded under __main__.
    assert hasattr(minimax_benchmark, "main")


@pytest.fixture(scope="module")
def cross_engine_benchmark():
    return _load_demo_module("cross_engine_benchmark.py")


class TestCrossEngineBenchmarkCLI:
    """Tiny end-to-end smoke of the dataset -> run -> report pipeline."""

    def test_pipeline_end_to_end(self, cross_engine_benchmark, tmp_path):
        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"
        report_path = tmp_path / "results" / "run.md"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        assert (
            cross_engine_benchmark.main(
                [
                    "run",
                    "--dataset",
                    str(dataset_path),
                    "--family",
                    "native",
                    "--minimax-depth",
                    "2",
                    "--mcts-iterations",
                    "30",
                    "--beam-width",
                    "4",
                    "--beam-depth",
                    "4",
                    "--seeds",
                    "2",
                    "--h2h-positions",
                    "1",
                    "--h2h-seeds",
                    "1",
                    "--checkpoint-dir",
                    str(checkpoint_dir),
                    "--checkpoint-every",
                    "1",
                    "--output",
                    str(bundle_path),
                ]
            )
            == 0
        )

        assert (
            cross_engine_benchmark.main(
                [
                    "report",
                    "--input",
                    str(checkpoint_dir),
                    "--output",
                    str(report_path),
                ]
            )
            == 0
        )

        import json

        bundle = json.loads(bundle_path.read_text())
        manifest = json.loads((checkpoint_dir / "manifest.json").read_text())
        assert bundle["schema_version"] == 1
        assert bundle["observations"]
        assert bundle["dataset"]["checksum"]
        assert bundle["head_to_head"]["records"]
        assert manifest["status"] == "complete"
        assert manifest["counts"]["observations"] == len(bundle["observations"])
        assert manifest["counts"]["h2h_records"] == len(
            bundle["head_to_head"]["records"]
        )
        assert (checkpoint_dir / "observations.jsonl").read_text().strip()
        assert (checkpoint_dir / "h2h.jsonl").read_text().strip()

        markdown = report_path.read_text()
        for heading in (
            "Exact move agreement",
            "Computational cost",
            "Head-to-head",
            "Stability",
        ):
            assert heading in markdown

    def test_checkpoint_manifest_exists_during_preflight(
        self, cross_engine_benchmark, tmp_path, monkeypatch, capsys
    ):
        import json

        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        def fail_after_manifest(_adapters, _positions):
            manifest = json.loads((checkpoint_dir / "manifest.json").read_text())
            assert manifest["status"] == "preflight"
            assert manifest["counts"] == {"observations": 0, "h2h_records": 0}
            return ["synthetic preflight stop"]

        monkeypatch.setattr(
            cross_engine_benchmark, "run_preflight", fail_after_manifest
        )

        assert (
            cross_engine_benchmark.main(
                [
                    "run",
                    "--dataset",
                    str(dataset_path),
                    "--family",
                    "native",
                    "--minimax-depth",
                    "2",
                    "--mcts-iterations",
                    "1",
                    "--beam-width",
                    "2",
                    "--beam-depth",
                    "2",
                    "--seeds",
                    "1",
                    "--h2h-positions",
                    "1",
                    "--h2h-seeds",
                    "1",
                    "--checkpoint-dir",
                    str(checkpoint_dir),
                    "--checkpoint-every",
                    "1",
                    "--output",
                    str(bundle_path),
                ]
            )
            == 1
        )

        manifest = json.loads((checkpoint_dir / "manifest.json").read_text())
        assert manifest["status"] == "preflight_failed"
        assert "preflight: checking" in capsys.readouterr().out

    def test_checkpoint_resume_skips_existing_rows(
        self, cross_engine_benchmark, tmp_path
    ):
        import json

        dataset_path = tmp_path / "positions.json"
        first_bundle_path = tmp_path / "results" / "first.json"
        second_bundle_path = tmp_path / "results" / "second.json"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        base_args = [
            "run",
            "--dataset",
            str(dataset_path),
            "--family",
            "native",
            "--minimax-depth",
            "2",
            "--mcts-iterations",
            "30",
            "--beam-width",
            "4",
            "--beam-depth",
            "4",
            "--seeds",
            "1",
            "--h2h-positions",
            "1",
            "--h2h-seeds",
            "1",
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-every",
            "1",
        ]

        assert (
            cross_engine_benchmark.main(
                [*base_args, "--output", str(first_bundle_path)]
            )
            == 0
        )
        first_bundle = json.loads(first_bundle_path.read_text())
        first_manifest = json.loads((checkpoint_dir / "manifest.json").read_text())
        first_obs_lines = (
            (checkpoint_dir / "observations.jsonl").read_text().splitlines()
        )
        first_h2h_lines = (checkpoint_dir / "h2h.jsonl").read_text().splitlines()

        assert (
            cross_engine_benchmark.main(
                [*base_args, "--resume", "--output", str(second_bundle_path)]
            )
            == 0
        )
        second_bundle = json.loads(second_bundle_path.read_text())
        second_manifest = json.loads((checkpoint_dir / "manifest.json").read_text())
        second_obs_lines = (
            (checkpoint_dir / "observations.jsonl").read_text().splitlines()
        )
        second_h2h_lines = (checkpoint_dir / "h2h.jsonl").read_text().splitlines()

        assert first_bundle["observations"] == second_bundle["observations"]
        assert (
            first_bundle["head_to_head"]["records"]
            == second_bundle["head_to_head"]["records"]
        )
        assert (
            first_bundle["head_to_head"]["aggregates"]
            == second_bundle["head_to_head"]["aggregates"]
        )
        assert first_manifest["counts"] == second_manifest["counts"]
        assert first_obs_lines == second_obs_lines
        assert first_h2h_lines == second_h2h_lines

    def test_resume_skip_h2h_preserves_existing_records(
        self, cross_engine_benchmark, tmp_path
    ):
        import json

        dataset_path = tmp_path / "positions.json"
        first_bundle_path = tmp_path / "results" / "first.json"
        second_bundle_path = tmp_path / "results" / "second.json"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        base_args = [
            "run",
            "--dataset",
            str(dataset_path),
            "--family",
            "native",
            "--minimax-depth",
            "2",
            "--mcts-iterations",
            "30",
            "--beam-width",
            "4",
            "--beam-depth",
            "4",
            "--seeds",
            "1",
            "--h2h-positions",
            "1",
            "--h2h-seeds",
            "1",
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-every",
            "1",
        ]

        assert (
            cross_engine_benchmark.main(
                [*base_args, "--output", str(first_bundle_path)]
            )
            == 0
        )
        first_bundle = json.loads(first_bundle_path.read_text())
        first_h2h_lines = (checkpoint_dir / "h2h.jsonl").read_text().splitlines()

        assert (
            cross_engine_benchmark.main(
                [
                    *base_args,
                    "--resume",
                    "--skip-h2h",
                    "--output",
                    str(second_bundle_path),
                ]
            )
            == 0
        )
        second_bundle = json.loads(second_bundle_path.read_text())
        second_h2h_lines = (checkpoint_dir / "h2h.jsonl").read_text().splitlines()

        assert (
            second_bundle["head_to_head"]["records"]
            == first_bundle["head_to_head"]["records"]
        )
        assert second_h2h_lines == first_h2h_lines

    def test_resume_skip_h2h_rejects_partial_checkpoint(
        self, cross_engine_benchmark, tmp_path
    ):
        import json

        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        base_args = [
            "run",
            "--dataset",
            str(dataset_path),
            "--family",
            "native",
            "--minimax-depth",
            "2",
            "--mcts-iterations",
            "30",
            "--beam-width",
            "4",
            "--beam-depth",
            "4",
            "--seeds",
            "1",
            "--h2h-positions",
            "1",
            "--h2h-seeds",
            "1",
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-every",
            "1",
            "--skip-h2h",
            "--output",
            str(bundle_path),
        ]

        assert cross_engine_benchmark.main(base_args) == 0
        h2h_before = (checkpoint_dir / "h2h.jsonl").read_text().splitlines()
        manifest_before = json.loads((checkpoint_dir / "manifest.json").read_text())

        assert (
            cross_engine_benchmark.main(
                [*base_args[:-2], "--resume", "--output", str(bundle_path)]
            )
            != 0
        )

        assert (checkpoint_dir / "h2h.jsonl").read_text().splitlines() == h2h_before
        assert (
            json.loads((checkpoint_dir / "manifest.json").read_text())
            == manifest_before
        )

    def test_resume_rejects_config_mismatch_without_appending(
        self, cross_engine_benchmark, tmp_path
    ):
        import json

        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        base_args = [
            "run",
            "--dataset",
            str(dataset_path),
            "--family",
            "native",
            "--minimax-depth",
            "2",
            "--mcts-iterations",
            "30",
            "--beam-width",
            "4",
            "--beam-depth",
            "4",
            "--seeds",
            "1",
            "--h2h-positions",
            "1",
            "--h2h-seeds",
            "1",
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-every",
            "1",
            "--output",
            str(bundle_path),
        ]

        assert cross_engine_benchmark.main(base_args) == 0
        obs_before = (checkpoint_dir / "observations.jsonl").read_text().splitlines()
        h2h_before = (checkpoint_dir / "h2h.jsonl").read_text().splitlines()
        manifest_before = json.loads((checkpoint_dir / "manifest.json").read_text())

        assert (
            cross_engine_benchmark.main(
                [
                    *base_args[:-2],
                    "--seed-base",
                    "9",
                    "--resume",
                    "--output",
                    str(bundle_path),
                ]
            )
            != 0
        )

        assert (
            checkpoint_dir / "observations.jsonl"
        ).read_text().splitlines() == obs_before
        assert (checkpoint_dir / "h2h.jsonl").read_text().splitlines() == h2h_before
        assert (
            json.loads((checkpoint_dir / "manifest.json").read_text())
            == manifest_before
        )

    def test_resume_allows_different_worker_count(
        self, cross_engine_benchmark, tmp_path
    ):
        import json

        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"
        checkpoint_dir = tmp_path / "results" / "checkpoint"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        base_args = [
            "run",
            "--dataset",
            str(dataset_path),
            "--family",
            "native",
            "--minimax-depth",
            "2",
            "--mcts-iterations",
            "30",
            "--beam-width",
            "4",
            "--beam-depth",
            "4",
            "--seeds",
            "1",
            "--h2h-positions",
            "1",
            "--h2h-seeds",
            "1",
            "--checkpoint-dir",
            str(checkpoint_dir),
            "--checkpoint-every",
            "1",
            "--output",
            str(bundle_path),
        ]

        assert cross_engine_benchmark.main([*base_args, "--workers", "1"]) == 0
        first_bundle = json.loads(bundle_path.read_text())

        assert (
            cross_engine_benchmark.main([*base_args, "--resume", "--workers", "2"]) == 0
        )
        second_bundle = json.loads(bundle_path.read_text())

        assert second_bundle["observations"] == first_bundle["observations"]

    def test_run_rejects_zero_workers(self, cross_engine_benchmark, tmp_path):
        dataset_path = tmp_path / "positions.json"
        bundle_path = tmp_path / "results" / "run.json"

        assert (
            cross_engine_benchmark.main(
                [
                    "dataset",
                    "--opening",
                    "0",
                    "--early-mid",
                    "0",
                    "--late-mid",
                    "1",
                    "--endgame",
                    "0",
                    "--seed",
                    "7",
                    "--solve-budget",
                    "15.0",
                    "--output",
                    str(dataset_path),
                ]
            )
            == 0
        )

        assert (
            cross_engine_benchmark.main(
                [
                    "run",
                    "--dataset",
                    str(dataset_path),
                    "--workers",
                    "0",
                    "--output",
                    str(bundle_path),
                ]
            )
            == 1
        )

    def test_parser_rejects_unknown_family(self, cross_engine_benchmark):
        with pytest.raises(SystemExit):
            cross_engine_benchmark.build_parser().parse_args(
                [
                    "run",
                    "--dataset",
                    "x.json",
                    "--family",
                    "bogus",
                    "--output",
                    "y.json",
                ]
            )


@pytest.fixture(scope="module")
def opening_book_demo():
    return _load_demo_module("opening_book_demo.py")


@pytest.fixture(scope="module")
def generate_opening_book():
    return _load_demo_module("generate_opening_book.py")


class TestOpeningBookNoLegalMovesIsAWinNotADraw:
    """Regression: Quantik has no draws. A position with no legal moves
    and no completed line must be scored as a win for whichever player is
    NOT to move (Board.get_game_result()'s own convention), not as a
    stalemate/draw -- see docs/OPENING_BOOK.md's "no-legal-moves case"
    callout and tuning/fill_opening_book.py's exact_entry, which already
    follows this convention.
    """

    # No legal moves, no completed line (found by random self-play search):
    # P0 to move (6 pieces each), every empty cell blocks every remaining
    # shape for P0 via row/col/box constraints. P1 -- who is NOT to move --
    # must be credited with the win.
    _NO_LEGAL_MOVES_NO_WIN = "ca.c/DDbb/BC.a/B.C."

    def test_explore_positions_credits_the_non_mover(self, opening_book_demo):
        from quantik_core import State
        from quantik_core.game_utils import check_game_winner, WinStatus

        bb = State.from_qfen(self._NO_LEGAL_MOVES_NO_WIN).bb
        assert check_game_winner(bb) == WinStatus.NO_WIN  # no completed line

        positions: dict = {}
        opening_book_demo.explore_positions(
            bb, depth=0, max_depth=0, positions=positions
        )

        canonical_key = State(bb).canonical_key()
        data = positions[(canonical_key, 0)]
        assert data["draw_count"] == 0
        assert data["win_count_p0"] == 0
        assert data["win_count_p1"] == 1
        assert data["evaluation"] == -1.0

    def test_expand_chunk_credits_the_non_mover(self, generate_opening_book):
        from quantik_core import State

        bb = State.from_qfen(self._NO_LEGAL_MOVES_NO_WIN).bb

        results = generate_opening_book._expand_chunk(
            [bb], depth=12, dropout_rate=0.0, dropout_from_depth=999, seed=0
        )

        assert len(results) == 1
        result = results[0]
        assert result["draws"] == 0
        assert result["w0"] == 0
        assert result["w1"] == 1
        assert result["eval"] == -1.0
        assert result["is_terminal"] == 2  # WIN_P1


@pytest.fixture(scope="module")
def generate_puzzles():
    return _load_demo_module("generate_puzzles.py")


class TestGeneratePuzzlesComputeSolutionLine:
    # P0 to move, mate-in-one: D at pos 3 completes row 0 (A b C .).
    _MATE_IN_ONE = "AbC./d.../..../...."

    def test_finds_forced_win_for_the_actual_mover(self, generate_puzzles):
        from quantik_core import State

        bb = State.from_qfen(self._MATE_IN_ONE).bb
        steps = generate_puzzles.compute_solution_line(
            bb, winning_player=0, depth_limit=2
        )

        assert steps is not None
        assert len(steps) == 1
        move, qfen_after, is_terminal = steps[0]
        assert move.player == 0
        assert is_terminal is True

    def test_returns_none_when_the_named_player_does_not_win(self, generate_puzzles):
        # P0 has the forced mate-in-one here, not P1: asking for a forced
        # win credited to P1 must return None rather than reporting P0's
        # winning line as if it belonged to P1.
        from quantik_core import State

        bb = State.from_qfen(self._MATE_IN_ONE).bb
        steps = generate_puzzles.compute_solution_line(
            bb, winning_player=1, depth_limit=2
        )

        assert steps is None

    # P1 to move; shape=0 at position=0 leaves P0 with zero legal replies --
    # a forced win WITHOUT completing a line. Deterministically the move
    # MinimaxEngine.search picks among the tied-optimal candidates here
    # (sorted (shape, position) ascending; this one sorts first). See
    # TestCrossEngineBenchmark._ANCHOR in this file for the same position
    # and its full derivation.
    _NO_LEGAL_REPLY_WIN = ".ba./..CC/DcbD/cA.A"

    def test_marks_no_legal_reply_terminal_as_a_win_not_a_draw(self, generate_puzzles):
        # Regression: check_game_winner() alone doesn't see a win here (no
        # line is completed), so is_final must also check whether the
        # resulting side has zero legal moves -- matching
        # MinimaxEngine._negamax's own terminal convention (no legal moves
        # is a win for whoever just moved; Quantik has no draws). Before
        # this check existed, a genuine forced win reached via a no-legal-
        # reply terminal was reported as unverified (None).
        from quantik_core import State, apply_move
        from quantik_core.game_utils import WinStatus, check_game_winner

        bb = State.from_qfen(self._NO_LEGAL_REPLY_WIN).bb
        steps = generate_puzzles.compute_solution_line(
            bb, winning_player=1, depth_limit=1
        )

        assert steps is not None
        assert len(steps) == 1
        move, qfen_after, is_terminal = steps[0]
        assert move.shape == 0 and move.position == 0
        assert is_terminal is True
        final_bb = apply_move(bb, move)
        assert check_game_winner(final_bb) == WinStatus.NO_WIN

    def test_returns_none_for_an_already_won_root(self, generate_puzzles):
        # Regression: generate_legal_moves_list does not stop returning
        # moves once a line is already completed elsewhere on the board
        # (it only reflects piece availability + placement legality), so
        # without an explicit check_game_winner(bb) guard at the top,
        # MinimaxEngine.search would silently search from an already-
        # decided position as if it were a normal interior node.
        from quantik_core import State
        from quantik_core.game_utils import WinStatus, check_game_winner
        from quantik_core.move import generate_legal_moves_list

        # Row 0 = A b C d: a completed line (4 distinct shapes), reached by
        # P0,P1,P0,P1 alternating and thus a valid, balanced piece count --
        # yet 40 legal moves remain on the rest of the empty board.
        bb = State.from_qfen("AbCd/..../..../....").bb
        assert check_game_winner(bb) != WinStatus.NO_WIN
        assert generate_legal_moves_list(bb)  # moves still "look" legal

        assert generate_puzzles.compute_solution_line(bb, winning_player=1) is None
