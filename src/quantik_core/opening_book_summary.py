"""Export opening-book-summary.v1 metrics from an opening-book SQLite file."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from .contracts import SUPPORTED_CONTRACTS_RELEASE

SUMMARY_SCHEMA = "opening-book-summary.v1"


def _table_names(conn: sqlite3.Connection) -> set[str]:
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    return {str(row[0]) for row in cursor.fetchall()}


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    cursor = conn.execute(f"PRAGMA table_info({table})")
    return {str(row[1]) for row in cursor.fetchall()}


def _edge_table(conn: sqlite3.Connection) -> str:
    tables = _table_names(conn)
    if "edges" in tables:
        return "edges"
    if "position_edges" in tables:
        return "position_edges"
    raise ValueError("opening book must contain edges or position_edges table")


def build_summary(db_path: str | Path, depth: int) -> dict[str, Any]:
    """Build an opening-book-summary.v1 dictionary from a SQLite book."""
    if depth < 0:
        raise ValueError("depth must be non-negative")

    conn = sqlite3.connect(str(db_path))
    try:
        tables = _table_names(conn)
        if "positions" not in tables:
            raise ValueError("opening book must contain positions table")
        edge_table = _edge_table(conn)
        position_columns = _column_names(conn, "positions")
        if "depth" not in position_columns:
            raise ValueError("positions table must contain depth column")
        terminal_expr = (
            "CASE WHEN p.is_terminal != 0 THEN 1 ELSE 0 END"
            if "is_terminal" in position_columns
            else "0"
        )

        per_depth: list[dict[str, int]] = []
        for current_depth in range(depth + 1):
            position_row = conn.execute(
                f"""
                SELECT COUNT(*) AS positions,
                       COALESCE(SUM({terminal_expr}), 0) AS terminal
                FROM positions p
                WHERE p.depth = ?
                """,
                (current_depth,),
            ).fetchone()
            edge_row = conn.execute(
                f"""
                SELECT COUNT(*)
                FROM {edge_table} e
                JOIN positions p ON p.canonical_key = e.parent_key
                WHERE p.depth = ?
                """,
                (current_depth,),
            ).fetchone()
            per_depth.append(
                {
                    "depth": current_depth,
                    "positions": int(position_row[0]),
                    "terminal": int(position_row[1]),
                    "edges": int(edge_row[0]),
                }
            )

        return {
            "schema": SUMMARY_SCHEMA,
            "contract_version": SUPPORTED_CONTRACTS_RELEASE,
            "depth": depth,
            "total_positions": sum(row["positions"] for row in per_depth),
            "terminal_positions": sum(row["terminal"] for row in per_depth),
            "total_edges": sum(row["edges"] for row in per_depth),
            "per_depth": per_depth,
        }
    finally:
        conn.close()


def write_summary(db_path: str | Path, depth: int, output_path: str | Path) -> None:
    """Write opening-book-summary.v1 JSON to output_path."""
    summary = build_summary(db_path, depth)
    Path(output_path).write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--depth", required=True, type=int)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    write_summary(args.db, args.depth, args.output)
    print(f"Wrote {SUMMARY_SCHEMA}: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
