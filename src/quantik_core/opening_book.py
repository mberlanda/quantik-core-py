"""
Opening book database implementation for Quantik.

Provides persistent storage and retrieval of analyzed game positions
with support for canonical form deduplication and efficient lookups.
"""

import sqlite3
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
from pathlib import Path

from quantik_core import State, Move


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
        self.conn: Optional[sqlite3.Connection] = None
        self._initialize_database()

    def _initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        self.conn = sqlite3.connect(str(self.db_path))

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

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
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_depth
            ON positions(depth)
        """
        )

        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_visit_count
            ON positions(visit_count DESC)
        """
        )

        self.conn.commit()

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
        """
        canonical_key = state.canonical_key()
        qfen = state.to_qfen()

        # Insert or replace position
        self.conn.execute(
            """
            INSERT OR REPLACE INTO positions
            (canonical_key, qfen, depth, evaluation, visit_count,
             win_count_p0, win_count_p1, draw_count)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
                   win_count_p0, win_count_p1, draw_count
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
        )

    def query_by_depth(
        self, depth: int, limit: int = 100
    ) -> List[OpeningBookEntry]:
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
                   win_count_p0, win_count_p1, draw_count
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
                )
            )

        return entries

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

        # Get file size
        file_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "total_positions": total_positions,
            "unique_depths": unique_depths,
            "total_visits": total_visits,
            "max_depth": max_depth,
            "file_size_bytes": file_size,
        }

    def get_positions_by_depth(self) -> Dict[int, int]:
        """Get count of positions at each depth."""
        cursor = self.conn.execute(
            """
            SELECT depth, COUNT(*) as count
            FROM positions
            GROUP BY depth
            ORDER BY depth
        """
        )

        return {depth: count for depth, count in cursor.fetchall()}

    def export_to_file(self, output_path: str, depth_limit: Optional[int] = None):
        """
        Export positions to a text file.

        Args:
            output_path: Output file path
            depth_limit: Optional depth limit for export
        """
        with open(output_path, "w") as f:
            f.write("# Quantik Opening Book Export\n")
            f.write("# Format: QFEN | Depth | Eval | Visits | P0Wins | P1Wins | Draws\n\n")

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
                cursor = self.conn.execute(
                    """
                    SELECT qfen, depth, evaluation, visit_count,
                           win_count_p0, win_count_p1, draw_count
                    FROM positions
                    ORDER BY depth, visit_count DESC
                """
                )

            for row in cursor.fetchall():
                f.write(
                    f"{row[0]} | {row[1]} | {row[2]:.3f} | {row[3]} | {row[4]} | {row[5]} | {row[6]}\n"
                )

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def __enter__(self):
        """Context manager support."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager cleanup."""
        self.close()
