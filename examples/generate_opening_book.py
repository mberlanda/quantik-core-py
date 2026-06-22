#!/usr/bin/env python3
"""
Generate Quantik opening book database with BFS exploration.

Uses breadth-first search with canonical deduplication to iteratively
explore the game tree from depth 0 to a target depth (default 8).
Positions are stored in a SQLite database with batch inserts.

Features:
- Fully resumable via per-depth checkpoints stored in the DB
- Configurable dropout at deeper depths to keep search tractable
- Multiprocessing parallelization for large frontiers
- Parent-child edge tracking for full DAG reconstruction

Usage:
    python examples/generate_opening_book.py
    python examples/generate_opening_book.py --max-depth 6 --workers 4
    python examples/generate_opening_book.py --dropout-rate 0.7 --dropout-from-depth 6
"""

import argparse
import os
import random
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Tuple

from quantik_core import State, generate_legal_moves, apply_move
from quantik_core.opening_book import OpeningBookDatabase, OpeningBookConfig
from quantik_core.game_utils import check_game_winner, WinStatus

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB = DATA_DIR / "opening_book_depth8.db"
BATCH_SIZE = 1000
PARALLEL_THRESHOLD = 1000

sys.setrecursionlimit(10_000)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def format_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def format_time(s: float) -> str:
    if s < 60:
        return f"{s:.1f}s"
    if s < 3600:
        return f"{s / 60:.1f}m"
    return f"{s / 3600:.1f}h"


# ---------------------------------------------------------------------------
# Checkpoint tables (co-located with the positions DB)
# ---------------------------------------------------------------------------


def _ensure_checkpoint_tables(conn) -> None:
    """Create checkpoint tables if they don't exist."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS generation_meta (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS frontier (
            qfen TEXT PRIMARY KEY
        )
    """)
    conn.commit()


def _load_checkpoint(conn) -> Tuple[int, List[tuple]]:
    """
    Load the last completed depth and its saved frontier.

    Returns (last_completed_depth, frontier_bitboards).
    If no checkpoint exists returns (-1, [initial_bb]).
    """
    row = conn.execute(
        "SELECT value FROM generation_meta WHERE key = 'last_completed_depth'"
    ).fetchone()

    if row is None:
        initial_bb = State.from_qfen("..../..../..../....").bb
        return -1, [initial_bb]

    last_depth = int(row[0])

    frontier_qfens = [
        r[0] for r in conn.execute("SELECT qfen FROM frontier").fetchall()
    ]
    frontier_bbs = [State.from_qfen(q).bb for q in frontier_qfens]
    return last_depth, frontier_bbs


def _save_checkpoint(
    conn, completed_depth: int, next_frontier_qfens: List[str]
) -> None:
    """Persist the completed depth and the frontier for the next depth."""
    conn.execute(
        "INSERT OR REPLACE INTO generation_meta (key, value) VALUES (?, ?)",
        ("last_completed_depth", str(completed_depth)),
    )
    conn.execute("DELETE FROM frontier")
    for i in range(0, len(next_frontier_qfens), BATCH_SIZE):
        chunk = [(q,) for q in next_frontier_qfens[i : i + BATCH_SIZE]]
        conn.executemany("INSERT OR IGNORE INTO frontier (qfen) VALUES (?)", chunk)
    conn.commit()


# ---------------------------------------------------------------------------
# Batch insert
# ---------------------------------------------------------------------------


def _flush_positions(conn, batch: List[dict]) -> None:
    """Insert a batch of positions and their best moves into the database."""
    if not batch:
        return
    conn.executemany(
        "INSERT OR IGNORE INTO positions "
        "(canonical_key, qfen, depth, evaluation, visit_count, "
        "win_count_p0, win_count_p1, draw_count, is_terminal, symmetry_count) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                p["key"],
                p["qfen"],
                p["depth"],
                p["eval"],
                p["visits"],
                p["w0"],
                p["w1"],
                p["draws"],
                p["is_terminal"],
                p["symmetry_count"],
            )
            for p in batch
        ],
    )
    moves_rows = []
    for p in batch:
        for rank, (shape, pos) in enumerate(p["best_moves"][:5], 1):
            moves_rows.append((p["key"], rank, shape, pos))
    if moves_rows:
        conn.executemany(
            "INSERT OR IGNORE INTO best_moves "
            "(canonical_key, move_rank, shape, position) "
            "VALUES (?, ?, ?, ?)",
            moves_rows,
        )
    conn.commit()


def _flush_edges(conn, edges: List[Tuple[bytes, bytes]]) -> None:
    """Insert parent->child edges into the DAG table."""
    if not edges:
        return
    conn.executemany(
        "INSERT OR IGNORE INTO position_edges (parent_key, child_key) " "VALUES (?, ?)",
        edges,
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Pure-computation worker (no DB access — safe for multiprocessing)
# ---------------------------------------------------------------------------


def _expand_chunk(
    bbs: List[tuple],
    depth: int,
    dropout_rate: float,
    dropout_from_depth: int,
    seed: int,
) -> List[dict]:
    """
    Expand a chunk of frontier positions.

    Each result dict contains:
      key          - canonical key (bytes)
      qfen         - QFEN string
      depth        - current depth
      eval, w0, w1, draws - evaluation data
      best_moves   - list of (shape, position) tuples
      edges        - list of (parent_key, child_key)
      children     - list of (child_key, child_qfen) for next frontier
    """
    results = []
    for bb in bbs:
        state = State(bb)
        key = state.canonical_key()
        winner = check_game_winner(bb)
        sym_count = state.symmetry_count()

        all_moves: list = []
        if winner == WinStatus.NO_WIN:
            _, moves_by_shape = generate_legal_moves(bb)
            for shape_moves in moves_by_shape.values():
                all_moves.extend(shape_moves)

        if winner == WinStatus.PLAYER_0_WINS:
            ev, w0, w1, dr = 1.0, 1, 0, 0
            terminal = 1  # WIN_P0
        elif winner == WinStatus.PLAYER_1_WINS:
            ev, w0, w1, dr = -1.0, 0, 1, 0
            terminal = 2  # WIN_P1
        elif not all_moves:
            ev, w0, w1, dr = 0.0, 0, 0, 1
            terminal = 3  # STALEMATE
        else:
            ev, w0, w1, dr = 0.0, 0, 0, 0
            terminal = 0  # INTERIOR

        # Apply dropout: position-specific deterministic RNG
        moves_for_children = list(all_moves)
        if moves_for_children and depth >= dropout_from_depth and dropout_rate > 0:
            rng = random.Random(seed ^ hash(key))
            keep_count = max(1, int(len(moves_for_children) * (1 - dropout_rate)))
            moves_for_children = rng.sample(moves_for_children, keep_count)

        # Expand children and collect edges
        edges: List[Tuple[bytes, bytes]] = []
        children: List[Tuple[bytes, str]] = []
        for move in moves_for_children:
            child_bb = apply_move(bb, move)
            child_state = State(child_bb)
            child_key = child_state.canonical_key()
            edges.append((key, child_key))
            children.append((child_key, child_state.to_qfen()))

        best_moves = [(m.shape, m.position) for m in all_moves[:3]]

        results.append(
            {
                "key": key,
                "qfen": state.to_qfen(),
                "depth": depth,
                "eval": ev,
                "visits": 1,
                "w0": w0,
                "w1": w1,
                "draws": dr,
                "is_terminal": terminal,
                "symmetry_count": sym_count,
                "best_moves": best_moves,
                "edges": edges,
                "children": children,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Depth processing: serial or parallel
# ---------------------------------------------------------------------------


def _process_depth_serial(
    frontier: List[tuple],
    depth: int,
    dropout_rate: float,
    dropout_from_depth: int,
    seed: int,
) -> List[dict]:
    """Process entire frontier in the main process."""
    return _expand_chunk(frontier, depth, dropout_rate, dropout_from_depth, seed)


def _process_depth_parallel(
    frontier: List[tuple],
    depth: int,
    dropout_rate: float,
    dropout_from_depth: int,
    seed: int,
    num_workers: int,
) -> List[dict]:
    """Split frontier into chunks and process across multiple workers."""
    chunk_size = max(1, len(frontier) // (num_workers * 4))
    chunks = [frontier[i : i + chunk_size] for i in range(0, len(frontier), chunk_size)]

    print(
        f"    Parallel: {num_workers} workers, {len(chunks)} chunks "
        f"({chunk_size:,} positions/chunk)"
    )

    all_results: List[dict] = []
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        futures = [
            executor.submit(
                _expand_chunk,
                chunk,
                depth,
                dropout_rate,
                dropout_from_depth,
                seed,
            )
            for chunk in chunks
        ]
        done = 0
        for future in futures:
            chunk_results = future.result()
            all_results.extend(chunk_results)
            done += 1
            if len(chunks) >= 8 and done % max(1, len(chunks) // 4) == 0:
                print(f"    Chunks: {done}/{len(chunks)} complete")

    return all_results


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def generate(  # noqa: C901
    max_depth: int = 8,
    db_path: Path = DEFAULT_DB,
    dropout_rate: float = 0.0,
    dropout_from_depth: int = 6,
    seed: int = 42,
    num_workers: int = 1,
) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    config = OpeningBookConfig(database_path=str(db_path))
    db = OpeningBookDatabase(config)
    conn = db.conn

    _ensure_checkpoint_tables(conn)

    # -- resume from checkpoint ------------------------------------------------
    last_completed, frontier = _load_checkpoint(conn)

    in_db: set[bytes] = set()
    for (k,) in conn.execute("SELECT canonical_key FROM positions"):
        in_db.add(k)

    existing = db.get_positions_by_depth()
    if existing:
        print(f"Loaded {len(in_db):,} existing positions")
        for d in sorted(existing):
            print(f"  depth {d}: {existing[d]:,}")

    if last_completed >= 0:
        print(
            f"\nCheckpoint: depth {last_completed} complete, "
            f"frontier has {len(frontier):,} positions for depth {last_completed + 1}"
        )

    start_depth = last_completed + 1

    if start_depth > max_depth:
        stats = db.get_statistics()
        print(f"\nAlready complete to depth {last_completed}. Nothing to do.")
        print(
            f"Total: {stats['total_positions']:,} positions, "
            f"{stats['total_edges']:,} edges, "
            f"{format_size(stats['file_size_bytes'])}"
        )
        db.close()
        return

    print(f"\nTarget: depth {max_depth}  |  DB: {db_path}")
    if dropout_rate > 0:
        print(
            f"Dropout: {dropout_rate:.0%} from depth {dropout_from_depth}  |  seed: {seed}"
        )
    if num_workers > 1:
        print(f"Workers: {num_workers}")
    print("=" * 70)

    # -- BFS ------------------------------------------------------------------
    expanded: set[bytes] = set()
    depth_times: list[float] = []
    total_start = time.time()
    interrupted = False

    def on_interrupt(_sig, _frame):
        nonlocal interrupted
        interrupted = True
        print("\n\n>>> Ctrl-C received — finishing current batch …")

    old_handler = signal.signal(signal.SIGINT, on_interrupt)

    try:
        for depth in range(start_depth, max_depth + 1):
            if interrupted or not frontier:
                if not frontier:
                    print(f"\nDepth {depth}: no frontier — game tree fully explored.")
                break

            t0 = time.time()

            if depth >= 6 and len(depth_times) >= 2:
                ratio = depth_times[-1] / max(depth_times[-2], 0.01)
                est = depth_times[-1] * ratio
                print(
                    f"\n  NOTE: Depth {depth} estimated ~{format_time(est)} "
                    f"(×{ratio:.1f} growth from previous depth)"
                )

            use_parallel = num_workers > 1 and len(frontier) >= PARALLEL_THRESHOLD
            mode = f"parallel ({num_workers}w)" if use_parallel else "serial"
            dropout_active = depth >= dropout_from_depth and dropout_rate > 0
            dropout_tag = f"  dropout={dropout_rate:.0%}" if dropout_active else ""
            print(
                f"\nDepth {depth}  |  frontier: {len(frontier):,}  "
                f"|  {mode}{dropout_tag}"
            )

            # -- expand all positions in this frontier -------------------------
            if use_parallel:
                all_results = _process_depth_parallel(
                    frontier,
                    depth,
                    dropout_rate,
                    dropout_from_depth,
                    seed,
                    num_workers,
                )
            else:
                all_results = _process_depth_serial(
                    frontier,
                    depth,
                    dropout_rate,
                    dropout_from_depth,
                    seed,
                )

            if interrupted:
                break

            # -- main-process dedup and DB insertion ---------------------------
            pos_batch: list[dict] = []
            edge_batch: List[Tuple[bytes, bytes]] = []
            next_frontier: Dict[bytes, str] = {}
            new_count = 0
            edge_count = 0

            for r in all_results:
                key = r["key"]

                if key in expanded:
                    continue
                expanded.add(key)

                # Insert position if new
                if key not in in_db:
                    in_db.add(key)
                    new_count += 1
                    pos_batch.append(r)
                    if len(pos_batch) >= BATCH_SIZE:
                        _flush_positions(conn, pos_batch)
                        pos_batch.clear()

                # Collect edges (even for already-seen positions: the edge is new)
                for parent_key, child_key in r["edges"]:
                    edge_batch.append((parent_key, child_key))
                    edge_count += 1
                if len(edge_batch) >= BATCH_SIZE:
                    _flush_edges(conn, edge_batch)
                    edge_batch.clear()

                # Build next frontier from children not yet expanded
                for child_key, child_qfen in r["children"]:
                    if child_key not in expanded and child_key not in next_frontier:
                        next_frontier[child_key] = child_qfen

            # Flush remaining
            _flush_positions(conn, pos_batch)
            _flush_edges(conn, edge_batch)

            # -- checkpoint: save frontier for next depth ----------------------
            if not interrupted:
                _save_checkpoint(conn, depth, list(next_frontier.values()))

            dt = time.time() - t0
            depth_times.append(dt)

            db_sz = db_path.stat().st_size if db_path.exists() else 0
            print(
                f"  -> +{new_count:,} positions, +{edge_count:,} edges  |  "
                f"next frontier: {len(next_frontier):,}  |  "
                f"total: {len(in_db):,}  |  "
                f"{format_time(dt)}  |  DB {format_size(db_sz)}"
                f"  [checkpoint saved]"
            )

            # Rebuild frontier as bitboard tuples from QFENs
            frontier = [State.from_qfen(qfen).bb for qfen in next_frontier.values()]
    finally:
        signal.signal(signal.SIGINT, old_handler)

    # -- summary ---------------------------------------------------------------
    total = time.time() - total_start
    stats = db.get_statistics()
    by_depth = db.get_positions_by_depth()

    print(f"\n{'=' * 70}")
    if interrupted:
        print("GENERATION INTERRUPTED — partial results saved (checkpoint intact)")
    else:
        print("OPENING BOOK GENERATION COMPLETE")
    print(f"{'=' * 70}")
    print(f"Positions : {stats['total_positions']:,}")
    print(f"Edges     : {stats['total_edges']:,}")
    print(f"Max depth : {stats['max_depth']}")
    print(f"Time      : {format_time(total)}")
    print(f"Database  : {db_path}")
    print(f"DB size   : {format_size(stats['file_size_bytes'])}")
    print("\nPositions by depth:")
    for d in sorted(by_depth):
        print(f"  {d:>2}: {by_depth[d]:>10,}")

    db.close()


def main():
    parser = argparse.ArgumentParser(
        description="Generate Quantik opening book database"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=8,
        help="maximum depth to explore (default: 8)",
    )
    parser.add_argument(
        "--dropout-rate",
        type=float,
        default=0.0,
        help="fraction of moves to DROP at deep levels (default: 0 = full width)",
    )
    parser.add_argument(
        "--dropout-from-depth",
        type=int,
        default=6,
        help="depth at which dropout begins (default: 6)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="RNG seed for dropout reproducibility (default: 42)",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=max(1, (os.cpu_count() or 2) - 1),
        help="number of worker processes (default: cpu_count - 1)",
    )
    args = parser.parse_args()

    generate(
        max_depth=args.max_depth,
        db_path=DEFAULT_DB,
        dropout_rate=args.dropout_rate,
        dropout_from_depth=args.dropout_from_depth,
        seed=args.seed,
        num_workers=args.workers,
    )


if __name__ == "__main__":
    main()
