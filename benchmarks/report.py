"""Markdown report generation from benchmark result bundles."""

from __future__ import annotations


def _fmt(value, spec: str = ".3f") -> str:
    if value is None:
        return "-"
    return format(value, spec)


def _table(headers: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join(" --- " for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(cell) for cell in row) + " |")
    return "\n".join(lines)


def _family_note(family: str) -> str:
    if family == "fixed":
        return "same wall-clock budget per move; fair practical-latency comparison"
    return (
        "per-engine native settings; useful for scaling behavior, "
        "not fair head-to-head ranking"
    )


def render_markdown(bundle_dict: dict) -> str:
    """Render the required benchmark Markdown report tables."""
    env = bundle_dict["environment"]
    config = bundle_dict["config"]
    aggregates = bundle_dict["aggregates"]
    dataset = bundle_dict["dataset"]
    family = config.get("family", "?")

    parts = [
        f"# Cross-engine benchmark - `{str(env['git_sha'])[:12]}`",
        "",
        f"- benchmark family: **{family}** ({_family_note(family)})",
        (
            f"- dataset: `{dataset['checksum']}` - {dataset['positions']} positions "
            f"{dataset['phases']}, generation seed {dataset['seed']}"
        ),
        f"- engine seeds: `{config.get('engine_seeds')}`",
        (
            f"- environment: quantik-core {env['quantik_core_version']}, "
            f"python {env['python_version']}, {env['platform']}, "
            f"{env['cpu_count']} CPUs"
        ),
        f"- started: {bundle_dict['started_at']}",
        "",
        "## Exact move agreement",
        "",
        (
            "A hit means the selected move is in the complete optimal set proven "
            "by the exact solver with no cutoff. Positions without exact "
            "references are excluded. For stochastic engines, runs equal "
            "positions times seeds."
        ),
        "",
        _table(
            [
                "Engine",
                "Configuration",
                "Phase",
                "Runs",
                "Optimal selected",
                "Agreement",
                "95% CI",
            ],
            [
                [
                    row["engine"],
                    f"`{row['config_label']}`",
                    row["phase"],
                    row["n"],
                    row["hits"],
                    _fmt(row["agreement"]),
                    f"[{_fmt(row['ci95_low'])}, {_fmt(row['ci95_high'])}]",
                ]
                for row in aggregates["agreement"]
            ],
        ),
        "",
        "## Computational cost",
        "",
        "Measured effective work per move, not just configured limits.",
        "",
        _table(
            [
                "Engine",
                "Configuration",
                "Moves",
                "Median time (s)",
                "p95 time (s)",
                "Median nodes",
                "Peak memory (bytes)",
            ],
            [
                [
                    row["engine"],
                    f"`{row['config_label']}`",
                    row["n"],
                    _fmt(row["median_time_s"], ".4f"),
                    _fmt(row["p95_time_s"], ".4f"),
                    _fmt(row["median_nodes"], ".0f"),
                    _fmt(row["peak_memory_bytes"], ",.0f"),
                ]
                for row in aggregates["cost"]
            ],
        ),
        "",
        "## Head-to-head (paired, side-balanced)",
        "",
        (
            "Each position and seed is played twice, once with each engine as "
            "the side to move. Wins are credited to the actual engine/color "
            "mapping. Quantik cannot draw, so Draws is structurally 0."
        ),
        "",
        _table(
            [
                "Engine A",
                "Engine B",
                "Paired positions",
                "Games",
                "A wins",
                "B wins",
                "Draws",
                "A win rate (95% CI)",
                "A wins as mover",
                "B wins as mover",
            ],
            [
                [
                    row["engine_a"],
                    row["engine_b"],
                    row["paired_positions"],
                    row["games"],
                    row["a_wins"],
                    row["b_wins"],
                    row["draws"],
                    (
                        f"{_fmt(row['a_win_rate'])} "
                        f"[{_fmt(row['a_win_rate_ci95'][0])}, "
                        f"{_fmt(row['a_win_rate_ci95'][1])}]"
                    ),
                    row["a_wins_as_mover"],
                    row["b_wins_as_mover"],
                ]
                for row in bundle_dict["head_to_head"]["aggregates"]
            ],
        ),
        "",
        "### Head-to-head by phase",
        "",
        _table(
            ["Engine A", "Engine B", "Phase", "Games", "A wins", "B wins"],
            [
                [
                    row["engine_a"],
                    row["engine_b"],
                    phase,
                    split["games"],
                    split["a_wins"],
                    split["b_wins"],
                ]
                for row in bundle_dict["head_to_head"]["aggregates"]
                for phase, split in row["by_phase"].items()
            ],
        ),
        "",
        "## Stability across seeds",
        "",
        (
            "Move consistency is the average fraction of seeds choosing the modal "
            "move per position. Agreement mean and std are computed per seed "
            "first, then aggregated."
        ),
        "",
        _table(
            [
                "Engine",
                "Configuration",
                "Seeds",
                "Move consistency",
                "Agreement mean",
                "Agreement std",
            ],
            [
                [
                    row["engine"],
                    f"`{row['config_label']}`",
                    row["seeds"],
                    _fmt(row["move_consistency"]),
                    _fmt(row["agreement_mean"]),
                    _fmt(row["agreement_std"]),
                ]
                for row in aggregates["stability"]
            ],
        ),
        "",
        "## Interpretation guardrails",
        "",
        (
            "- Minimax buys adversarial certainty when the remaining tree is "
            "small enough; MCTS buys empirical confidence through repeated "
            "sampling; beam search buys bounded, selectively deep exploration."
        ),
        (
            "- No engine is universally superior unless the evidence spans "
            "multiple phases, equivalent budgets, repeated seeds, and "
            "statistically meaningful samples."
        ),
        (
            "- Beam search honors its time limit only between depth levels; "
            "compare measured times above, never configured caps."
        ),
        (
            "- Algorithm-native tables explain scaling; only fixed-resource "
            "tables support fair engine-vs-engine claims."
        ),
        "",
    ]
    return "\n".join(parts)
