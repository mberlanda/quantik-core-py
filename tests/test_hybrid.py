import pytest
from quantik_core import State, apply_move
from quantik_core.hybrid import HybridPlayer, HybridConfig
from quantik_core.mcts import MCTSConfig
from quantik_core.beam_search import BeamSearchConfig
from quantik_core.game_utils import has_winning_line
from quantik_core.move import generate_legal_moves_list

# A valid 8-piece (4+4) P0-to-move, non-terminal position -- the plan's
# original "AbC./d.a./B..c/...." was invalid (fails from_qfen(validate=True)).
# This one solves in ~1.3s and happens to be a forced mate-in-1 for P0
# (score 9999 = win - 1 ply), matching the test's name -- asserted below by
# applying the returned move and checking has_winning_line, not just assumed.
_ENDGAME_QFEN = "c.../.aBD/bcD./A..."

# All from_qfen calls below pass validate=True so an accidentally-illegal
# anchor fails loudly (at parse time) rather than silently exercising
# undefined engine behavior on an invalid position.
_OPEN_GAME_QFEN = "A.b./..../..../...."


def test_endgame_uses_exact_solver_and_finds_mate():
    # 8 pieces placed => 8 empty cells => at the handoff threshold => exact.
    state = State.from_qfen(_ENDGAME_QFEN, validate=True)
    player = HybridPlayer(HybridConfig(handoff_empty_cells=8))
    result = player.search(state)
    assert result.exact and result.engine_used == "minimax"
    assert result.best_move in generate_legal_moves_list(state.bb)
    assert has_winning_line(apply_move(state.bb, result.best_move))


def test_open_game_uses_opening_engine():
    # 2 pieces placed => 14 empty cells => above threshold => opening engine.
    state = State.from_qfen(_OPEN_GAME_QFEN, validate=True)
    player = HybridPlayer(
        HybridConfig(
            handoff_empty_cells=8,
            opening_engine="mcts",
            mcts_config=MCTSConfig(max_iterations=100, random_seed=0),
        )
    )
    result = player.search(state)
    assert not result.exact and result.engine_used == "mcts"
    assert result.best_move in generate_legal_moves_list(state.bb)


def test_beam_opening_engine_selected():
    state = State.from_qfen(_OPEN_GAME_QFEN, validate=True)
    player = HybridPlayer(
        HybridConfig(
            handoff_empty_cells=8,
            opening_engine="beam",
            beam_config=BeamSearchConfig(beam_width=8, max_depth=4, random_seed=0),
        )
    )
    result = player.search(state)
    assert result.engine_used == "beam"
    assert result.best_move in generate_legal_moves_list(state.bb)


def test_beam_engine_raises_clearly_instead_of_indexerror_when_no_results():
    # Regression: if BeamSearchEngine ever returns no best_leaf AND no
    # ranked_root_moves() (both empty), the old code did
    # `result.ranked_root_moves()[0].move`, an IndexError with no context.
    # Simulate that with a directly-constructed empty BeamSearchResult.
    from unittest.mock import patch
    from quantik_core.beam_search import BeamSearchResult

    empty_result = BeamSearchResult(
        best_leaf=None,
        terminal_leaves=[],
        reached_terminal=False,
        max_depth_reached=0,
        stats={},
    )
    state = State.from_qfen(_OPEN_GAME_QFEN, validate=True)
    player = HybridPlayer(HybridConfig(handoff_empty_cells=8, opening_engine="beam"))
    with patch(
        "quantik_core.hybrid.BeamSearchEngine.search", return_value=empty_result
    ):
        with pytest.raises(ValueError, match="no best_leaf"):
            player.search(state)


def test_select_move_matches_search():
    state = State.from_qfen(_OPEN_GAME_QFEN, validate=True)
    player = HybridPlayer(
        HybridConfig(mcts_config=MCTSConfig(max_iterations=50, random_seed=3))
    )
    assert player.select_move(state) == player.search(state).best_move


def test_invalid_engine_raises():
    with pytest.raises(ValueError):
        HybridPlayer(HybridConfig(opening_engine="nope")).search(
            State.from_qfen(_OPEN_GAME_QFEN, validate=True)
        )


def test_search_raises_on_already_terminal_state_minimax_path():
    # Regression: a position with a completed winning line but empty
    # cells remaining elsewhere previously fell through to
    # MinimaxEngine.solve() (which only checks "no legal moves", not
    # "already won") and silently returned a meaningless move with
    # exact=True. Confirmed concretely: pre-fix, this returned
    # HybridResult(best_move=..., engine_used="minimax", exact=True)
    # instead of raising.
    state = State.from_qfen("AbCd/..../..../....", validate=True)
    assert has_winning_line(state.bb) and generate_legal_moves_list(state.bb)
    player = HybridPlayer(HybridConfig(handoff_empty_cells=16))  # force minimax path
    with pytest.raises(ValueError, match="terminal"):
        player.search(state)


def test_search_raises_on_already_terminal_state_mcts_path():
    # Same regression, opening-engine side: MCTSEngine.search() also
    # didn't validate terminality and silently returned a move.
    state = State.from_qfen("AbCd/..../..../....", validate=True)
    player = HybridPlayer(
        HybridConfig(
            handoff_empty_cells=0,
            opening_engine="mcts",
            mcts_config=MCTSConfig(max_iterations=10, random_seed=0),
        )
    )
    with pytest.raises(ValueError, match="terminal"):
        player.search(state)
