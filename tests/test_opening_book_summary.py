"""Tests for opening-book-summary.v1 export."""

import json
import sqlite3
import subprocess
import sys

import pytest

from quantik_core.opening_book_summary import build_summary, write_summary


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


def create_python_style_book(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE positions (
            canonical_key BLOB PRIMARY KEY,
            depth INTEGER NOT NULL
        )
        """)
    conn.execute("""
        CREATE TABLE position_edges (
            parent_key BLOB NOT NULL,
            child_key BLOB NOT NULL,
            PRIMARY KEY(parent_key, child_key)
        )
        """)
    conn.executemany(
        "INSERT INTO positions (canonical_key, depth) VALUES (?, ?)",
        [(b"root", 0), (b"a", 1), (b"b", 1)],
    )
    conn.executemany(
        "INSERT INTO position_edges (parent_key, child_key) VALUES (?, ?)",
        [(b"root", b"a"), (b"root", b"b")],
    )
    conn.commit()
    conn.close()


def test_build_summary_exports_rust_style_book_metrics(tmp_path):
    db_path = tmp_path / "book.sqlite"
    create_rust_style_book(db_path)

    summary = build_summary(db_path, 2)

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


def test_build_summary_supports_python_position_edges_table(tmp_path):
    db_path = tmp_path / "book.sqlite"
    create_python_style_book(db_path)

    summary = build_summary(db_path, 1)

    assert summary["terminal_positions"] == 0
    assert summary["total_positions"] == 3
    assert summary["total_edges"] == 2
    assert summary["per_depth"] == [
        {"depth": 0, "positions": 1, "terminal": 0, "edges": 2},
        {"depth": 1, "positions": 2, "terminal": 0, "edges": 0},
    ]


def test_write_summary_writes_pretty_json_with_trailing_newline(tmp_path):
    db_path = tmp_path / "book.sqlite"
    output_path = tmp_path / "summary.json"
    create_rust_style_book(db_path)

    write_summary(db_path, 2, output_path)

    text = output_path.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text)["total_edges"] == 3


def test_build_summary_rejects_negative_depth(tmp_path):
    db_path = tmp_path / "book.sqlite"
    create_rust_style_book(db_path)

    with pytest.raises(ValueError, match="depth must be non-negative"):
        build_summary(db_path, -1)


def test_build_summary_requires_positions_table(tmp_path):
    db_path = tmp_path / "book.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE edges (parent_key BLOB, child_key BLOB)")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="positions table"):
        build_summary(db_path, 1)


def test_build_summary_requires_edge_table(tmp_path):
    db_path = tmp_path / "book.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE positions (canonical_key BLOB, depth INTEGER)")
    conn.commit()
    conn.close()

    with pytest.raises(ValueError, match="edges or position_edges table"):
        build_summary(db_path, 1)


def test_opening_book_summary_cli_exports_rust_style_book(tmp_path):
    db_path = tmp_path / "book.sqlite"
    output_path = tmp_path / "summary.json"
    create_rust_style_book(db_path)

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
    assert summary["schema"] == "opening-book-summary.v1"
    assert summary["total_edges"] == 3
