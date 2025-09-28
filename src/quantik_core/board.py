"""
Enhanced board representation for Quantik with inventory tracking and game state management.

This module provides a high-level QuantikBoard class that wraps the low-level State
representation with additional functionality including:
- Player inventory tracking (remaining pieces)
- Move history and undo functionality
- Comprehensive legal move generation
- Win/stalemate detection
- QFEN parsing and serialization
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Iterator, cast
from enum import IntEnum

from .core import State
from .move import Move, apply_move, validate_move
from .commons import MAX_PIECES_PER_SHAPE, PlayerId
from .plugins.validation import WinStatus, check_game_winner
from .state_validator import validate_game_state


class GameResult(IntEnum):
    """Enumeration of game results."""

    ONGOING = 0
    PLAYER_0_WINS = 1
    PLAYER_1_WINS = 2


@dataclass(frozen=True)
class PlayerInventory:
    """Tracks remaining pieces for a player."""

    shape_a: int = MAX_PIECES_PER_SHAPE  # Remaining A pieces
    shape_b: int = MAX_PIECES_PER_SHAPE  # Remaining B pieces
    shape_c: int = MAX_PIECES_PER_SHAPE  # Remaining C pieces
    shape_d: int = MAX_PIECES_PER_SHAPE  # Remaining D pieces

    def __post_init__(self) -> None:
        """Validate inventory constraints."""
        for shape_count in [self.shape_a, self.shape_b, self.shape_c, self.shape_d]:
            if not (0 <= shape_count <= MAX_PIECES_PER_SHAPE):
                raise ValueError(f"Invalid piece count: {shape_count}")

    @property
    def total_pieces(self) -> int:
        """Total remaining pieces."""
        return self.shape_a + self.shape_b + self.shape_c + self.shape_d

    def get_shape_count(self, shape: int) -> int:
        """Get remaining count for a specific shape (0=A, 1=B, 2=C, 3=D)."""
        return [self.shape_a, self.shape_b, self.shape_c, self.shape_d][shape]

    def has_shape(self, shape: int) -> bool:
        """Check if player has remaining pieces of given shape."""
        return self.get_shape_count(shape) > 0

    def use_shape(self, shape: int) -> "PlayerInventory":
        """Return new inventory with one piece of given shape used."""
        counts = [self.shape_a, self.shape_b, self.shape_c, self.shape_d]
        if counts[shape] <= 0:
            raise ValueError(f"No remaining pieces of shape {shape}")

        counts[shape] -= 1
        return PlayerInventory(*counts)

    def add_shape(self, shape: int) -> "PlayerInventory":
        """Return new inventory with one piece of given shape added back."""
        counts = [self.shape_a, self.shape_b, self.shape_c, self.shape_d]
        if counts[shape] >= MAX_PIECES_PER_SHAPE:
            raise ValueError(f"Cannot exceed max pieces for shape {shape}")

        counts[shape] += 1
        return PlayerInventory(*counts)


@dataclass
class MoveRecord:
    """Records a move with context for undo functionality."""

    move: Move
    previous_state: State
    previous_inventories: Tuple[PlayerInventory, PlayerInventory]
    move_number: int


class QuantikBoard:
    """
    Enhanced board representation with inventory tracking and game state management.

    This class provides a high-level interface for Quantik game management,
    wrapping the low-level State representation with additional functionality.
    """

    _inventories: Tuple[PlayerInventory, PlayerInventory]

    def __init__(
        self,
        state: Optional[State] = None,
        inventories: Optional[Tuple[PlayerInventory, PlayerInventory]] = None,
    ):
        """
        Initialize board from state and inventories.

        Args:
            state: Game state (defaults to empty board)
            inventories: Player inventories (defaults to full inventories)
        """
        self._state = state or State.empty()

        if inventories is None:
            # Calculate inventories from current state
            self._inventories = self._calculate_inventories_from_state(self._state)
        else:
            self._inventories = inventories

        self._move_history: List[MoveRecord] = []
        current_player_id, _ = validate_game_state(self._state.bb, raise_on_error=True)
        if current_player_id is None:
            # If validation fails but we're not raising on error, default to player 0
            current_player_id = 0
        self._current_player: PlayerId = current_player_id

        # Validate consistency
        self._validate_consistency()

    @classmethod
    def empty(cls) -> "QuantikBoard":
        """Create an empty board with full inventories."""
        return cls()

    @classmethod
    def from_qfen(cls, qfen: str, validate: bool = True) -> "QuantikBoard":
        """
        Create board from QFEN notation.

        Args:
            qfen: QFEN string representation
            validate: Whether to validate the resulting state

        Returns:
            QuantikBoard instance
        """
        state = State.from_qfen(qfen, validate=validate)
        return cls(state)

    @classmethod
    def from_state(cls, state: State) -> "QuantikBoard":
        """Create board from existing State."""
        return cls(state)

    # Properties

    @property
    def state(self) -> State:
        """Current game state."""
        return self._state

    @property
    def current_player(self) -> PlayerId:
        """Current player to move."""
        return self._current_player

    @property
    def player_inventories(self) -> Tuple[PlayerInventory, PlayerInventory]:
        """Player inventories (player 0, player 1)."""
        return self._inventories

    @property
    def move_count(self) -> int:
        """Number of moves played."""
        return len(self._move_history)

    @property
    def last_move(self) -> Optional[Move]:
        """Last move played, if any."""
        return self._move_history[-1].move if self._move_history else None

    # Game state queries

    def to_qfen(self) -> str:
        """Convert board to QFEN notation."""
        return self._state.to_qfen()

    def get_game_result(self) -> GameResult:
        """
        Determine current game result.

        Returns:
            GameResult indicating current state
        """
        # Check for wins
        win_status = check_game_winner(self._state)
        if win_status == WinStatus.PLAYER_0_WINS:
            return GameResult.PLAYER_0_WINS
        elif win_status == WinStatus.PLAYER_1_WINS:
            return GameResult.PLAYER_1_WINS

        # Check for stalemate (no legal moves)
        if not self.has_legal_moves():
            # If a player has no legal moves, the other player wins
            if self._current_player == 0:
                return GameResult.PLAYER_1_WINS
            else:
                return GameResult.PLAYER_0_WINS

        return GameResult.ONGOING

    def is_game_over(self) -> bool:
        """Check if game is finished."""
        return self.get_game_result() != GameResult.ONGOING

    def has_legal_moves(self, player: Optional[PlayerId] = None) -> bool:
        """Check if player has any legal moves."""
        player = player or self._current_player
        # Use next() with a default to avoid generating the full list
        try:
            next(self.generate_legal_moves(player))
            return True
        except StopIteration:
            return False

    def is_move_legal(self, move: Move) -> bool:
        """Check if a move is legal in current position."""
        # Check basic move validation
        result = validate_move(self._state.bb, move)
        if not result.is_valid:
            return False

        # Check if player has the piece in inventory
        inventory = self._inventories[move.player]
        if not inventory.has_shape(move.shape):
            return False

        return True

    # Move generation

    def generate_legal_moves(self, player: Optional[PlayerId] = None) -> Iterator[Move]:
        """
        Generate all legal moves for a player.

        Args:
            player: Player to generate moves for (defaults to current player)

        Yields:
            Legal moves respecting inventory constraints
        """
        player = player or self._current_player
        inventory = self._inventories[player]

        # Get occupied positions once to avoid repeated checks
        occupied_bb = self._state.get_occupied_bb()

        # Only consider moves with pieces we have in inventory
        for shape in range(4):
            if not inventory.has_shape(shape):
                continue

            # Pre-filter empty positions to avoid creating invalid moves
            for position in range(16):
                # Skip occupied positions immediately
                if (occupied_bb >> position) & 1:
                    continue

                # Create move only after basic filtering
                move = Move(player=player, shape=shape, position=position)

                # Full validation still needed for game rules
                result = validate_move(self._state.bb, move)
                if result.is_valid:
                    yield move

    def get_legal_moves(self, player: Optional[PlayerId] = None) -> List[Move]:
        """Get all legal moves as a list."""
        return list(self.generate_legal_moves(player))

    def count_legal_moves(self, player: Optional[PlayerId] = None) -> int:
        """Count legal moves without generating full list."""
        return sum(1 for _ in self.generate_legal_moves(player))

    # Move execution

    def play_move(self, move: Move) -> bool:
        """
        Play a move, updating board state and inventories.

        Args:
            move: Move to play

        Returns:
            True if move was played successfully, False if illegal
        """
        if self.is_game_over():
            raise ValueError("Game is already over")

        if not self.is_move_legal(move):
            return False

        # Record current state for undo
        move_record = MoveRecord(
            move=move,
            previous_state=self._state,
            previous_inventories=self._inventories,
            move_number=self.move_count,
        )

        # Apply move to state
        new_bb = apply_move(self._state.bb, move)
        self._state = State(new_bb)
    
        # Update inventory directly without creating a list
        if move.player == 0:
            self._inventories = (
                self._inventories[0].use_shape(move.shape),
                self._inventories[1],
            )
        else:
            self._inventories = (
                self._inventories[0],
                self._inventories[1].use_shape(move.shape),
            )

        # Update current player
        self._current_player = cast(PlayerId, 1 - self._current_player)

        # Record move
        self._move_history.append(move_record)

        return True

    def undo_move(self) -> bool:
        """
        Undo the last move.

        Returns:
            True if a move was undone, False if no moves to undo
        """
        if not self._move_history:
            return False

        # Restore previous state
        last_record = self._move_history.pop()
        self._state = last_record.previous_state
        self._inventories = last_record.previous_inventories
        self._current_player = last_record.move.player

        return True

    def undo_moves(self, count: int) -> int:
        """
        Undo multiple moves.

        Args:
            count: Number of moves to undo

        Returns:
            Number of moves actually undone
        """
        undone = 0
        for _ in range(count):
            if self.undo_move():
                undone += 1
            else:
                break
        return undone

    # Analysis methods

    def get_piece_counts(self) -> Dict[str, Dict[str, List[int]]]:
        """
        Get comprehensive piece count analysis.

        Returns:
            Dictionary with 'on_board' and 'in_inventory' counts per player/shape
        """
        # Count pieces on board
        on_board = {
            "player_0": [0, 0, 0, 0],  # A, B, C, D
            "player_1": [0, 0, 0, 0],  # a, b, c, d
        }

        for shape in range(4):
            on_board["player_0"][shape] = self._state.bb[shape].bit_count()
            on_board["player_1"][shape] = self._state.bb[shape + 4].bit_count()

        # Count pieces in inventory
        in_inventory = {
            "player_0": [
                self._inventories[0].shape_a,
                self._inventories[0].shape_b,
                self._inventories[0].shape_c,
                self._inventories[0].shape_d,
            ],
            "player_1": [
                self._inventories[1].shape_a,
                self._inventories[1].shape_b,
                self._inventories[1].shape_c,
                self._inventories[1].shape_d,
            ],
        }

        return {"on_board": on_board, "in_inventory": in_inventory}

    def get_mobility_score(self, player: PlayerId) -> int:
        """Get mobility score (number of legal moves) for a player."""
        return self.count_legal_moves(player)

    def copy(self) -> "QuantikBoard":
        """Create a deep copy of the board."""
        return QuantikBoard(self._state, self._inventories)

    # Private methods

    def _calculate_current_player(self) -> PlayerId:
        """Calculate current player from game state based on turn balance."""
        # Count total pieces played by each player
        player_0_pieces = sum(
            self._state.bb[i].bit_count() for i in range(4)
        )  # A, B, C, D
        player_1_pieces = sum(
            self._state.bb[i].bit_count() for i in range(4, 8)
        )  # a, b, c, d

        # In Quantik, player 0 always goes first
        # If pieces are equal, it's player 0's turn
        # If player 0 has 1 more piece, it's player 1's turn
        if player_0_pieces == player_1_pieces:
            return 0  # Player 0's turn
        elif player_0_pieces == player_1_pieces + 1:
            return 1  # Player 1's turn
        else:
            # Invalid state - this should be caught by validation
            raise ValueError(
                f"Invalid turn balance: Player 0 has {player_0_pieces} pieces, "
                f"Player 1 has {player_1_pieces} pieces"
            )

    def _calculate_inventories_from_state(
        self, state: State
    ) -> Tuple[PlayerInventory, PlayerInventory]:
        """Calculate player inventories from current board state."""
        inventories = []

        for player in range(2):
            shape_counts = []
            for shape in range(4):
                bitboard_idx = shape if player == 0 else shape + 4
                used_count = state.bb[bitboard_idx].bit_count()
                remaining = MAX_PIECES_PER_SHAPE - used_count
                shape_counts.append(remaining)

            inventories.append(PlayerInventory(*shape_counts))

        return (inventories[0], inventories[1])

    def _validate_consistency(self) -> None:
        """Validate that board state and inventories are consistent."""
        # Check that inventory + board counts = max pieces per shape
        for player in range(2):
            inventory = self._inventories[player]
            for shape in range(4):
                bitboard_idx = shape if player == 0 else shape + 4
                on_board = self._state.bb[bitboard_idx].bit_count()
                in_inventory = inventory.get_shape_count(shape)

                total = on_board + in_inventory
                if total != MAX_PIECES_PER_SHAPE:
                    raise ValueError(
                        f"Inconsistent piece count for player {player} shape {shape}: "
                        f"{on_board} on board + {in_inventory} in inventory = {total} "
                        f"(expected {MAX_PIECES_PER_SHAPE})"
                    )

    # String representation

    def __str__(self) -> str:
        """String representation showing board and inventories."""
        lines = [f"QFEN: {self.to_qfen()}"]
        lines.append(f"Current player: {self._current_player}")
        lines.append(f"Move count: {self.move_count}")

        # Show inventories
        for player in range(2):
            inv = self._inventories[player]
            lines.append(
                f"Player {player} inventory: A={inv.shape_a} B={inv.shape_b} C={inv.shape_c} D={inv.shape_d}"
            )

        result = self.get_game_result()
        if result != GameResult.ONGOING:
            lines.append(f"Game result: {result.name}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"QuantikBoard('{self.to_qfen()}')"
