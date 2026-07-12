"""Tests for benchmark run-size planning."""

from benchmarks.planner import estimate_volume


def test_estimate_volume_counts_observations_and_h2h_games():
    estimate = estimate_volume(
        positions=36,
        seeds=30,
        h2h_positions=16,
        h2h_seeds=5,
        engines=["minimax", "mcts", "beam", "random"],
        deterministic_engines={"minimax"},
    )

    assert estimate["observations"]["total"] == 3276
    assert estimate["observations"]["by_engine"] == {
        "minimax": 36,
        "mcts": 1080,
        "beam": 1080,
        "random": 1080,
    }
    assert estimate["h2h"]["total_games"] == 960
    assert estimate["h2h"]["games_per_pair"] == 160
    assert estimate["h2h"]["by_engine"]["minimax"] == {
        "games": 480,
        "as_mover": 240,
        "as_responder": 240,
    }
    assert estimate["h2h"]["by_pair"][("minimax", "mcts")] == 160


def test_estimate_volume_caps_h2h_positions_to_available_positions():
    estimate = estimate_volume(
        positions=10,
        seeds=3,
        h2h_positions=12,
        h2h_seeds=2,
        engines=["minimax", "mcts", "beam", "random"],
        deterministic_engines={"minimax"},
    )

    assert estimate["h2h"]["requested_positions"] == 12
    assert estimate["h2h"]["effective_positions"] == 10
    assert estimate["h2h"]["total_games"] == 240
