import pytest
from quantik_core import State
from quantik_core.hybrid import HybridPlayer, HybridConfig
from quantik_core.mcts import MCTSConfig
from quantik_core.beam_search import BeamSearchConfig
from quantik_core.move import generate_legal_moves_list

# A valid 8-piece (4+4) P0-to-move, non-terminal position -- the plan's
# original "AbC./d.a./B..c/...." was invalid (fails from_qfen(validate=True)).
# This one solves in ~1.3s and happens to be a forced mate-in-1 for P0
# (score 9999 = win - 1 ply), matching the test's name.
_ENDGAME_QFEN = "c.../.aBD/bcD./A..."


def test_endgame_uses_exact_solver_and_finds_mate():
    # 8 pieces placed => 8 empty cells => at the handoff threshold => exact.
    state = State.from_qfen(_ENDGAME_QFEN)
    player = HybridPlayer(HybridConfig(handoff_empty_cells=8))
    result = player.search(state)
    assert result.exact and result.engine_used == "minimax"
    assert result.best_move in generate_legal_moves_list(state.bb)


def test_open_game_uses_opening_engine():
    # 2 pieces placed => 14 empty cells => above threshold => opening engine.
    state = State.from_qfen("A.b./..../..../....")
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
    state = State.from_qfen("A.b./..../..../....")
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


def test_select_move_matches_search():
    state = State.from_qfen("A.b./..../..../....")
    player = HybridPlayer(
        HybridConfig(mcts_config=MCTSConfig(max_iterations=50, random_seed=3))
    )
    assert player.select_move(state) == player.search(state).best_move


def test_invalid_engine_raises():
    with pytest.raises(ValueError):
        HybridPlayer(HybridConfig(opening_engine="nope")).search(
            State.from_qfen("A.b./..../..../....")
        )
