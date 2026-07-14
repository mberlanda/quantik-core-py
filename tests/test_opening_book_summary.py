"""Tests for opening-book-summary.v1 export."""

import json
import sqlite3
import subprocess
import sys

from quantik_core.opening_book_summary import build_summary


def create_rust_style_book(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE positions (
            canonical_key BLOB PRIMARY KEY,
            depth INTEGER NOT NULL,
            is_terminal INTEGER NOT NULL,
            winner INTEGER,
            symmetry_count INTEGER NOT NULL,
            searched_depth INTEGER NOT NULL,
            score INTEGER,
            status TEXT NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE edges (
            parent_key BLOB NOT NULL,
            child_key BLOB NOT NULL,
            move TEXT NOT NULL,
            PRIMARY KEY(parent_key, child_key)
        )
        """)
    rows = [
        (b"root", 0, 0),
        (b"a", 1, 0),
        (b"b", 1, 0),
        (b"c", 2, 1),
    ]
    for key, depth, terminal in rows:
        conn.execute(
            """
            INSERT INTO positions
            (canonical_key, depth, is_terminal, winner, symmetry_count,
             searched_depth, score, status)
            VALUES (?, ?, ?, NULL, 1, 1, NULL, 'ok')
            """,
            (key, depth, terminal),
        )
    conn.executemany(
        "INSERT INTO edges (parent_key, child_key, move) VALUES (?, ?, ?)",
        [
            (b"root", b"a", "A@0"),
            (b"root", b"b", "B@1"),
            (b"a", b"c", "a@2"),
        ],
    )
    conn.commit()
    conn.close()


def test_opening_book_summary_cli_exports_rust_style_book(tmp_path):
    db_path = tmp_path / "book.sqlite"
    output_path = tmp_path / "summary.json"
    create_rust_style_book(db_path)

    assert build_summary(db_path, 2)["total_edges"] == 3

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "quantik_core.opening_book_summary",
            "--db",
            str(db_path),
            "--depth",
            "2",
            "--output",
            str(output_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    assert summary == {
        "schema": "opening-book-summary.v1",
        "contract_version": "1.1.0",
        "depth": 2,
        "total_positions": 4,
        "terminal_positions": 1,
        "total_edges": 3,
        "per_depth": [
            {"depth": 0, "positions": 1, "terminal": 0, "edges": 2},
            {"depth": 1, "positions": 2, "terminal": 0, "edges": 1},
            {"depth": 2, "positions": 1, "terminal": 1, "edges": 0},
        ],
    }
