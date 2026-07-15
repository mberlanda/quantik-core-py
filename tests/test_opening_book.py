"""Tests for opening book database, including is_terminal and symmetry_count columns."""

import pytest

from quantik_core import State
from quantik_core.opening_book import (
    OpeningBookDatabase,
    OpeningBookConfig,
    TerminalStatus,
)
from quantik_core.game_utils import check_game_winner, WinStatus


@pytest.fixture
def db(tmp_path):
    config = OpeningBookConfig(database_path=str(tmp_path / "test.db"))
    database = OpeningBookDatabase(config)
    yield database
    database.close()


class TestOpeningBookSchema:
    def test_positions_table_has_new_columns(self, db):
        cursor = db.conn.execute("PRAGMA table_info(positions)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "is_terminal" in columns
        assert "symmetry_count" in columns

    def test_migration_on_existing_db(self, tmp_path):
        """Verify ALTER TABLE migration adds columns to a legacy schema."""
        db_path = str(tmp_path / "legacy.db")
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE positions (
                canonical_key BLOB PRIMARY KEY,
                qfen TEXT NOT NULL,
                depth INTEGER NOT NULL,
                evaluation REAL NOT NULL,
                visit_count INTEGER NOT NULL,
                win_count_p0 INTEGER NOT NULL,
                win_count_p1 INTEGER NOT NULL,
                draw_count INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE best_moves (
                canonical_key BLOB NOT NULL,
                move_rank INTEGER NOT NULL,
                shape INTEGER NOT NULL,
                position INTEGER NOT NULL,
                PRIMARY KEY (canonical_key, move_rank)
            )
        """)
        conn.commit()
        conn.close()

        config = OpeningBookConfig(database_path=db_path)
        database = OpeningBookDatabase(config)

        cursor = database.conn.execute("PRAGMA table_info(positions)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "is_terminal" in columns
        assert "symmetry_count" in columns
        database.close()


class TestTerminalStatus:
    def test_constants(self):
        assert TerminalStatus.INTERIOR == 0
        assert TerminalStatus.WIN_P0 == 1
        assert TerminalStatus.WIN_P1 == 2
        assert TerminalStatus.STALEMATE == 3


class TestAddPositionWithNewFields:
    def test_add_interior_position(self, db):
        state = State.from_qfen("A.../..../..../....", validate=False)
        db.add_position(
            state=state,
            evaluation=0.0,
            visit_count=1,
            win_count_p0=0,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=1,
            is_terminal=TerminalStatus.INTERIOR,
            symmetry_count=state.symmetry_count(),
        )

        entry = db.get_position(state)
        assert entry is not None
        assert entry.is_terminal == TerminalStatus.INTERIOR
        assert entry.symmetry_count > 0

    def test_add_winning_position(self, db):
        state = State.from_qfen("ABCd/a.../..../....", validate=False)
        winner = check_game_winner(state.bb)

        if winner == WinStatus.PLAYER_0_WINS:
            terminal = TerminalStatus.WIN_P0
        elif winner == WinStatus.PLAYER_1_WINS:
            terminal = TerminalStatus.WIN_P1
        else:
            terminal = TerminalStatus.INTERIOR

        db.add_position(
            state=state,
            evaluation=1.0 if terminal == TerminalStatus.WIN_P0 else -1.0,
            visit_count=1,
            win_count_p0=1 if terminal == TerminalStatus.WIN_P0 else 0,
            win_count_p1=1 if terminal == TerminalStatus.WIN_P1 else 0,
            draw_count=0,
            best_moves=[],
            depth=4,
            is_terminal=terminal,
            symmetry_count=state.symmetry_count(),
        )

        entry = db.get_position(state)
        assert entry is not None
        assert entry.is_terminal in (TerminalStatus.WIN_P0, TerminalStatus.WIN_P1)
        assert entry.symmetry_count > 0

    def test_default_values(self, db):
        """When is_terminal/symmetry_count are omitted, defaults are used."""
        state = State.from_qfen("A.../..../..../....", validate=False)
        db.add_position(
            state=state,
            evaluation=0.0,
            visit_count=1,
            win_count_p0=0,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=1,
        )

        entry = db.get_position(state)
        assert entry is not None
        assert entry.is_terminal == 0
        assert entry.symmetry_count == 0


class TestSymmetryCount:
    def test_empty_board_symmetry_count(self):
        state = State.empty()
        count = state.symmetry_count()
        assert count == 1, "Empty board maps to itself under all symmetries"

    def test_single_piece_symmetry_count(self):
        state = State.from_qfen("A.../..../..../....", validate=False)
        count = state.symmetry_count()
        assert count > 1, "Corner piece should have multiple symmetric equivalents"

    def test_symmetry_count_range(self):
        positions = [
            "A.../..../..../....",
            "AB../..../..../....",
            ".A../..../..../....",
            "AB../cd../..../....",
        ]
        for qfen in positions:
            state = State.from_qfen(qfen, validate=False)
            count = state.symmetry_count()
            assert (
                1 <= count <= 192
            ), f"Orbit size must be 1..192, got {count} for {qfen}"


class TestStatisticsWithNewFields:
    def test_statistics_include_terminal_counts(self, db):
        state_interior = State.from_qfen("A.../..../..../....", validate=False)
        db.add_position(
            state=state_interior,
            evaluation=0.0,
            visit_count=1,
            win_count_p0=0,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=1,
            is_terminal=TerminalStatus.INTERIOR,
            symmetry_count=8,
        )

        state_win = State.from_qfen("AB../c.../..../....", validate=False)
        db.add_position(
            state=state_win,
            evaluation=1.0,
            visit_count=1,
            win_count_p0=1,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=3,
            is_terminal=TerminalStatus.WIN_P0,
            symmetry_count=4,
        )

        stats = db.get_statistics()
        assert stats["total_positions"] == 2
        assert stats["terminal_interior"] == 1
        assert stats["terminal_win_p0"] == 1
        assert stats["terminal_win_p1"] == 0
        assert stats["terminal_stalemate"] == 0

    def test_query_by_depth_returns_new_fields(self, db):
        state = State.from_qfen("A.../..../..../....", validate=False)
        db.add_position(
            state=state,
            evaluation=0.0,
            visit_count=5,
            win_count_p0=2,
            win_count_p1=1,
            draw_count=2,
            best_moves=[],
            depth=1,
            is_terminal=TerminalStatus.INTERIOR,
            symmetry_count=16,
        )

        entries = db.query_by_depth(1)
        assert len(entries) == 1
        assert entries[0].is_terminal == TerminalStatus.INTERIOR
        assert entries[0].symmetry_count == 16


class TestDAGEdges:
    def test_add_and_query_edges(self, db):
        state_a = State.from_qfen("A.../..../..../....", validate=False)
        state_b = State.from_qfen("Ab../..../..../....", validate=False)
        db.add_position(
            state=state_a,
            evaluation=0.0,
            visit_count=1,
            win_count_p0=0,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=1,
        )
        db.add_position(
            state=state_b,
            evaluation=0.0,
            visit_count=1,
            win_count_p0=0,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=2,
        )
        key_a = state_a.canonical_key()
        key_b = state_b.canonical_key()
        db.add_edges([(key_a, key_b)])

        assert db.get_children(key_a) == [key_b]
        assert db.get_parents(key_b) == [key_a]
        assert db.get_edge_count() == 1

    def test_add_edges_empty(self, db):
        db.add_edges([])
        assert db.get_edge_count() == 0

    def test_get_positions_by_depth(self, db):
        state = State.from_qfen("A.../..../..../....", validate=False)
        db.add_position(
            state=state,
            evaluation=0.0,
            visit_count=1,
            win_count_p0=0,
            win_count_p1=0,
            draw_count=0,
            best_moves=[],
            depth=1,
        )
        by_depth = db.get_positions_by_depth()
        assert by_depth[1] == 1


class TestContextManager:
    def test_context_manager(self, tmp_path):
        config = OpeningBookConfig(database_path=str(tmp_path / "ctx.db"))
        with OpeningBookDatabase(config) as db:
            state = State.from_qfen("A.../..../..../....", validate=False)
            db.add_position(
                state=state,
                evaluation=0.0,
                visit_count=1,
                win_count_p0=0,
                win_count_p1=0,
                draw_count=0,
                best_moves=[],
                depth=1,
            )


class TestSearchedBookMigration:
    """Opening a bench_bfs "searched book" SQLite file should not crash."""

    def _build_searched_book(self, db_path, canonical_key):
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE positions (
                canonical_key BLOB PRIMARY KEY,
                depth INTEGER NOT NULL,
                is_terminal INTEGER NOT NULL DEFAULT 0,
                winner INTEGER,
                symmetry_count INTEGER NOT NULL,
                searched_depth INTEGER NOT NULL DEFAULT 0,
                score REAL,
                status INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE edges (
                parent_key BLOB,
                child_key BLOB,
                move TEXT,
                PRIMARY KEY (parent_key, child_key)
            )
        """)
        conn.execute("CREATE INDEX idx_edges_child ON edges(child_key)")
        conn.execute("CREATE INDEX idx_pos_depth ON positions(depth)")
        conn.execute("CREATE INDEX idx_pos_status ON positions(status)")
        conn.execute("CREATE INDEX idx_pos_searched ON positions(searched_depth)")
        conn.execute(
            """
            INSERT INTO positions
            (canonical_key, depth, is_terminal, winner, symmetry_count,
             searched_depth, score, status)
            VALUES (?, 0, 0, NULL, 1, 0, NULL, 0)
        """,
            (canonical_key,),
        )
        conn.commit()
        conn.close()

    def test_opens_searched_book_without_crashing(self, tmp_path):
        db_path = str(tmp_path / "searched.db")
        state = State.empty()
        canonical_key = state.canonical_key()
        self._build_searched_book(db_path, canonical_key)

        config = OpeningBookConfig(database_path=db_path)
        database = OpeningBookDatabase(config)

        entry = database.get_position(state)
        assert entry is not None
        assert entry.visit_count == 0
        assert entry.qfen == ""
        assert entry.best_moves == []

        cursor = database.conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='position_edges'
        """)
        position_edges_indexes = {row[0] for row in cursor.fetchall()}
        assert "idx_position_edges_child" in position_edges_indexes

        cursor = database.conn.execute("""
            SELECT count(*) FROM sqlite_master
            WHERE type='index' AND name='idx_edges_child' AND tbl_name='edges'
        """)
        assert cursor.fetchone()[0] == 1

        database.close()

        # Re-opening the same file must be idempotent.
        database2 = OpeningBookDatabase(config)
        entry2 = database2.get_position(state)
        assert entry2 is not None
        database2.close()

    def test_legacy_benchmark_index_is_renamed(self, tmp_path):
        """A legacy benchmark book with idx_edges_child on position_edges
        should have that index renamed to idx_position_edges_child."""
        db_path = str(tmp_path / "legacy_benchmark.db")
        import sqlite3

        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE positions (
                canonical_key BLOB PRIMARY KEY,
                qfen TEXT NOT NULL,
                depth INTEGER NOT NULL,
                evaluation REAL NOT NULL,
                visit_count INTEGER NOT NULL,
                win_count_p0 INTEGER NOT NULL,
                win_count_p1 INTEGER NOT NULL,
                draw_count INTEGER NOT NULL,
                is_terminal INTEGER NOT NULL DEFAULT 0,
                symmetry_count INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("""
            CREATE TABLE position_edges (
                parent_key BLOB NOT NULL,
                child_key  BLOB NOT NULL,
                PRIMARY KEY (parent_key, child_key)
            )
        """)
        conn.execute("CREATE INDEX idx_edges_child ON position_edges(child_key)")
        conn.commit()
        conn.close()

        config = OpeningBookConfig(database_path=db_path)
        database = OpeningBookDatabase(config)

        cursor = database.conn.execute("""
            SELECT name FROM sqlite_master
            WHERE type='index' AND tbl_name='position_edges'
              AND name NOT LIKE 'sqlite_autoindex%'
        """)
        indexes = {row[0] for row in cursor.fetchall()}
        assert indexes == {"idx_position_edges_child"}

        database.close()
