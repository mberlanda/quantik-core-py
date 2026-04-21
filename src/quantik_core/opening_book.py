"""
Opening book database implementation for Quantik.

Provides persistent storage and retrieval of analyzed game positions
with support for canonical form deduplication and efficient lookups.
"""

import sqlite3
from typing import Any, Optional, List, Dict, Tuple, Type
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType

from quantik_core import State, Move


class TerminalStatus:
    """Terminal status codes for positions in the opening book."""

    INTERIOR = 0  # Non-terminal position (game continues)
    WIN_P0 = 1  # Player 0 has won
    WIN_P1 = 2  # Player 1 has won
    STALEMATE = 3  # No legal moves remaining (draw)


@dataclass
class OpeningBookEntry:
    """Represents a single position in the opening book."""

    canonical_key: bytes  # Canonical state representation (18 bytes)
    qfen: str  # Human-readable QFEN notation
    depth: int  # Ply depth from start
    evaluation: float  # Position evaluation (-1.0 to 1.0)
    visit_count: int  # Number of times position was reached
    best_moves: List[Tuple[int, int]]  # List of (shape, position) for best moves
    win_count_p0: int  # Player 0 wins from this position
    win_count_p1: int  # Player 1 wins from this position
    draw_count: int  # Draws from this position
    is_terminal: int = (
        TerminalStatus.INTERIOR
    )  # 0=interior, 1=win_p0, 2=win_p1, 3=stalemate
    symmetry_count: int = 0  # Number of distinct boards mapping to this canonical form


@dataclass
class OpeningBookConfig:
    """Configuration for opening book database."""

    database_path: str = "quantik_opening_book.db"
    cache_size_mb: int = 100  # SQLite cache size in MB
    enable_wal: bool = True  # Write-Ahead Logging for performance


class OpeningBookDatabase:
    """
    Opening book database with SQLite backend.

    Uses canonical state representations for automatic deduplication
    of symmetric positions. Provides efficient lookup and bulk import.
    """

    def __init__(self, config: OpeningBookConfig):
        """Initialize opening book database."""
        self.config = config
        self.db_path = Path(config.database_path)
        self.conn: sqlite3.Connection = sqlite3.connect(str(self.db_path))
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Create database tables if they don't exist."""

        # Set performance pragmas
        self.conn.execute(f"PRAGMA cache_size = -{self.config.cache_size_mb * 1024}")
        if self.config.enable_wal:
            self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")

        # Create positions table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS positions (
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

        # Migrate existing databases: add new columns if missing
        self._migrate_add_column(
            "positions", "is_terminal", "INTEGER NOT NULL DEFAULT 0"
        )
        self._migrate_add_column(
            "positions", "symmetry_count", "INTEGER NOT NULL DEFAULT 0"
        )

        # Create best_moves table
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS best_moves (
                canonical_key BLOB NOT NULL,
                move_rank INTEGER NOT NULL,
                shape INTEGER NOT NULL,
                position INTEGER NOT NULL,
                FOREIGN KEY (canonical_key) REFERENCES positions(canonical_key),
                PRIMARY KEY (canonical_key, move_rank)
            )
        """)

        # Create indices for efficient queries
        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_depth
            ON positions(depth)
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_visit_count
            ON positions(visit_count DESC)
        """)

        # DAG edges: parent -> child canonical key relationships
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS position_edges (
                parent_key BLOB NOT NULL,
                child_key  BLOB NOT NULL,
                PRIMARY KEY (parent_key, child_key),
                FOREIGN KEY (parent_key) REFERENCES positions(canonical_key),
                FOREIGN KEY (child_key)  REFERENCES positions(canonical_key)
            )
        """)

        self.conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_edges_child
            ON position_edges(child_key)
        """)

        self.conn.commit()

    def _migrate_add_column(self, table: str, column: str, col_type: str) -> None:
        """Add a column to an existing table if it doesn't already exist."""
        cursor = self.conn.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")

    def add_position(
        self,
        state: State,
        evaluation: float,
        visit_count: int,
        win_count_p0: int,
        win_count_p1: int,
        draw_count: int,
        best_moves: List[Move],
        depth: int,
        is_terminal: int = TerminalStatus.INTERIOR,
        symmetry_count: int = 0,
    ) -> None:
        """
        Add or update a position in the opening book.

        Args:
            state: Game state (will be canonicalized)
            evaluation: Position evaluation (-1.0 to 1.0)
            visit_count: Number of visits
            win_count_p0: Player 0 wins
            win_count_p1: Player 1 wins
            draw_count: Draw count
            best_moves: List of best moves (up to 5)
            depth: Ply depth
            is_terminal: Terminal status (0=interior, 1=win_p0, 2=win_p1, 3=stalemate)
            symmetry_count: Number of distinct boards mapping to this canonical form
        """
        canonical_key = state.canonical_key()
        qfen = state.to_qfen()

        # Insert or replace position
        self.conn.execute(
            """
            INSERT OR REPLACE INTO positions
            (canonical_key, qfen, depth, evaluation, visit_count,
             win_count_p0, win_count_p1, draw_count, is_terminal, symmetry_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                canonical_key,
                qfen,
                depth,
                evaluation,
                visit_count,
                win_count_p0,
                win_count_p1,
                draw_count,
                is_terminal,
                symmetry_count,
            ),
        )

        # Delete old best moves
        self.conn.execute(
            """
            DELETE FROM best_moves WHERE canonical_key = ?
        """,
            (canonical_key,),
        )

        # Insert new best moves (limit to top 5)
        for rank, move in enumerate(best_moves[:5], 1):
            self.conn.execute(
                """
                INSERT INTO best_moves
                (canonical_key, move_rank, shape, position)
                VALUES (?, ?, ?, ?)
            """,
                (canonical_key, rank, move.shape, move.position),
            )

        self.conn.commit()

    def get_position(self, state: State) -> Optional[OpeningBookEntry]:
        """
        Retrieve position from opening book.

        Args:
            state: Game state (will be canonicalized)

        Returns:
            OpeningBookEntry if found, None otherwise
        """
        canonical_key = state.canonical_key()

        # Query position
        cursor = self.conn.execute(
            """
            SELECT qfen, depth, evaluation, visit_count,
                   win_count_p0, win_count_p1, draw_count,
                   is_terminal, symmetry_count
            FROM positions
            WHERE canonical_key = ?
        """,
            (canonical_key,),
        )

        row = cursor.fetchone()
        if not row:
            return None

        # Query best moves
        cursor = self.conn.execute(
            """
            SELECT shape, position
            FROM best_moves
            WHERE canonical_key = ?
            ORDER BY move_rank
        """,
            (canonical_key,),
        )

        best_moves = [(shape, position) for shape, position in cursor.fetchall()]

        return OpeningBookEntry(
            canonical_key=canonical_key,
            qfen=row[0],
            depth=row[1],
            evaluation=row[2],
            visit_count=row[3],
            win_count_p0=row[4],
            win_count_p1=row[5],
            draw_count=row[6],
            best_moves=best_moves,
            is_terminal=row[7],
            symmetry_count=row[8],
        )

    def query_by_depth(self, depth: int, limit: int = 100) -> List[OpeningBookEntry]:
        """
        Query positions at specific depth.

        Args:
            depth: Target depth
            limit: Maximum number of results

        Returns:
            List of opening book entries
        """
        cursor = self.conn.execute(
            """
            SELECT canonical_key, qfen, depth, evaluation, visit_count,
                   win_count_p0, win_count_p1, draw_count,
                   is_terminal, symmetry_count
            FROM positions
            WHERE depth = ?
            ORDER BY visit_count DESC
            LIMIT ?
        """,
            (depth, limit),
        )

        entries = []
        for row in cursor.fetchall():
            canonical_key = row[0]

            # Get best moves
            moves_cursor = self.conn.execute(
                """
                SELECT shape, position
                FROM best_moves
                WHERE canonical_key = ?
                ORDER BY move_rank
            """,
                (canonical_key,),
            )

            best_moves = [
                (shape, position) for shape, position in moves_cursor.fetchall()
            ]

            entries.append(
                OpeningBookEntry(
                    canonical_key=canonical_key,
                    qfen=row[1],
                    depth=row[2],
                    evaluation=row[3],
                    visit_count=row[4],
                    win_count_p0=row[5],
                    win_count_p1=row[6],
                    draw_count=row[7],
                    best_moves=best_moves,
                    is_terminal=row[8],
                    symmetry_count=row[9],
                )
            )

        return entries

    # ----- DAG edge queries ---------------------------------------------------

    def add_edges(self, edges: List[Tuple[bytes, bytes]]) -> None:
        """
        Bulk-insert parent -> child edges.

        Args:
            edges: list of (parent_canonical_key, child_canonical_key)
        """
        if not edges:
            return
        self.conn.executemany(
            "INSERT OR IGNORE INTO position_edges (parent_key, child_key) "
            "VALUES (?, ?)",
            edges,
        )
        self.conn.commit()

    def get_children(self, canonical_key: bytes) -> List[bytes]:
        """Return canonical keys of all children reachable from *canonical_key*."""
        cursor = self.conn.execute(
            "SELECT child_key FROM position_edges WHERE parent_key = ?",
            (canonical_key,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_parents(self, canonical_key: bytes) -> List[bytes]:
        """Return canonical keys of all parents that lead to *canonical_key*."""
        cursor = self.conn.execute(
            "SELECT parent_key FROM position_edges WHERE child_key = ?",
            (canonical_key,),
        )
        return [row[0] for row in cursor.fetchall()]

    def get_edge_count(self) -> int:
        """Return total number of edges in the DAG."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM position_edges")
        result: Any = cursor.fetchone()[0]
        return int(result)

    # ----- statistics --------------------------------------------------------

    def get_statistics(self) -> Dict[str, int]:
        """Get database statistics."""
        cursor = self.conn.execute("SELECT COUNT(*) FROM positions")
        total_positions = cursor.fetchone()[0]

        cursor = self.conn.execute("SELECT COUNT(DISTINCT depth) FROM positions")
        unique_depths = cursor.fetchone()[0]

        cursor = self.conn.execute("SELECT SUM(visit_count) FROM positions")
        total_visits = cursor.fetchone()[0] or 0

        cursor = self.conn.execute("SELECT MAX(depth) FROM positions")
        max_depth = cursor.fetchone()[0] or 0

        # Terminal position breakdown
        cursor = self.conn.execute(
            "SELECT is_terminal, COUNT(*) FROM positions GROUP BY is_terminal"
        )
        terminal_counts = dict(cursor.fetchall())

        # Get file size
        file_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        edge_count = self.get_edge_count()

        return {
            "total_positions": total_positions,
            "unique_depths": unique_depths,
            "total_visits": total_visits,
            "max_depth": max_depth,
            "total_edges": edge_count,
            "terminal_interior": terminal_counts.get(TerminalStatus.INTERIOR, 0),
            "terminal_win_p0": terminal_counts.get(TerminalStatus.WIN_P0, 0),
            "terminal_win_p1": terminal_counts.get(TerminalStatus.WIN_P1, 0),
            "terminal_stalemate": terminal_counts.get(TerminalStatus.STALEMATE, 0),
            "file_size_bytes": file_size,
        }

    def get_positions_by_depth(self) -> Dict[int, int]:
        """Get count of positions at each depth."""
        cursor = self.conn.execute("""
            SELECT depth, COUNT(*) as count
            FROM positions
            GROUP BY depth
            ORDER BY depth
        """)

        return {depth: count for depth, count in cursor.fetchall()}

    def export_to_file(
        self, output_path: str, depth_limit: Optional[int] = None
    ) -> None:
        """
        Export positions to a text file.

        Args:
            output_path: Output file path
            depth_limit: Optional depth limit for export
        """
        with open(output_path, "w") as f:
            f.write("# Quantik Opening Book Export\n")
            f.write(
                "# Format: QFEN | Depth | Eval | Visits | P0Wins | P1Wins | Draws\n\n"
            )

            if depth_limit:
                cursor = self.conn.execute(
                    """
                    SELECT qfen, depth, evaluation, visit_count,
                           win_count_p0, win_count_p1, draw_count
                    FROM positions
                    WHERE depth <= ?
                    ORDER BY depth, visit_count DESC
                """,
                    (depth_limit,),
                )
            else:
                cursor = self.conn.execute("""
                    SELECT qfen, depth, evaluation, visit_count,
                           win_count_p0, win_count_p1, draw_count
                    FROM positions
                    ORDER BY depth, visit_count DESC
                """)

            for row in cursor.fetchall():
                f.write(
                    f"{row[0]} | {row[1]} | {row[2]:.3f} | {row[3]} | {row[4]} | {row[5]} | {row[6]}\n"
                )

    def close(self) -> None:
        """Close database connection."""
        self.conn.close()

    def __enter__(self) -> "OpeningBookDatabase":
        """Context manager support."""
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Context manager cleanup."""
        self.close()
