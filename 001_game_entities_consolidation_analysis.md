# QuantikEngine Unified API Design & Implementation Analysis

## Executive Summary

This document provides a comprehensive analysis of the current `quantik-core-py` codebase to design and implement a unified `QuantikEngine` API that serves multiple use cases:

1. **Analytics Models**: Statistical analysis and pattern recognition
2. **MCTS (Monte Carlo Tree Search)**: AI engine support with fast position evaluation  
3. **Move Engine**: Real-time legal move generation and validation
4. **Game Tree Simulation**: Complete game tree expansion from starting positions
5. **Puzzle Generation**: Creation of game puzzles and positions to solve
6. **Opening Book**: Database management for opening sequences and endgame positions

## Current Codebase Status (October 25, 2025)

### ✅ Foundation Completed
- **318 tests passing** with comprehensive coverage
- **CompactBitboard**: Memory-optimized 16-byte representation (vs 104-byte tuples)
- **State class**: Immutable game state with canonical serialization
- **Move operations**: Complete legal move generation and validation
- **QFEN support**: Human-readable position notation
- **Symmetry handling**: 8-fold symmetry reduction for canonical positions
- **Multiple serialization formats**: Binary (18 bytes), QFEN, CBOR

### 🔧 Current Architecture Analysis

**Core Components Inventory**:

| Component | Location | Memory | Purpose | Capabilities |
|-----------|----------|--------|---------|--------------|
| **State** | `core.py` | 48 bytes | Core game state | QFEN, canonical, pack/unpack |
| **CompactBitboard** | `memory/bitboard_compact.py` | 16 bytes | Memory-efficient backend | Direct bit operations |
| **QuantikBoard** | `board.py` | 200+ bytes | High-level wrapper | Move history, inventory tracking |
| **Move operations** | `move.py` | Functions | Move generation/validation | Legal moves, validation |
| **QFEN utilities** | `qfen.py` | Functions | Human-readable format | Position serialization |
| **Symmetry** | `symmetry.py` | Handler | Canonical positions | 8-fold symmetry reduction |
| **Game stats** | `game_stats.py` | Analytics | Position analysis | Statistical analysis |

**Performance Characteristics**:
- **Memory efficiency**: CompactBitboard provides 6.5x reduction vs traditional tuples
- **Canonical processing**: Sub-millisecond symmetry reduction
- **Serialization speed**: 18-byte binary format for fast I/O
- **Move generation**: Optimized legal move enumeration

## QuantikEngine Unified API Design

### Core Design Principles

1. **Single Entry Point**: One interface for all game operations
2. **Immutable Operations**: Functional-style move application with method chaining
3. **Flexible Caching**: Multiple caching strategies (LRU, file system, network)
4. **Batch Processing**: Efficient batch operations for tree analysis
5. **Mode-Based Optimization**: Different modes for different use cases

### Proposed QuantikEngine Interface

```python
from enum import Enum
from typing import Optional, List, Dict, Iterator, Union, Callable
from dataclasses import dataclass
import time

class EngineMode(Enum):
    """Engine operation modes for different use cases."""
    PERFORMANCE = "performance"  # Maximum speed for MCTS
    COMPATIBILITY = "compatibility"  # Full backward compatibility
    ANALYSIS = "analysis"  # Rich analytics and debugging info

@dataclass
class CacheConfig:
    """Configuration for caching strategies."""
    strategy: str  # "lru", "filesystem", "network"
    max_size: int = 1000000
    ttl_seconds: Optional[int] = None
    batch_size: int = 1000
    cache_dir: Optional[str] = None
    network_url: Optional[str] = None

@dataclass
class EngineStats:
    """Engine performance and usage statistics."""
    positions_evaluated: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_move_generation_time: float = 0.0
    average_moves_per_position: float = 0.0
    symmetry_reductions: int = 0

class QuantikEngine:
    """
    Unified game engine supporting analytics, MCTS, move generation,
    tree simulation, puzzle generation, and opening book management.
    """
    
    def __init__(
        self, 
        state: Optional[Union[State, str]] = None,
        mode: EngineMode = EngineMode.PERFORMANCE,
        cache_config: Optional[CacheConfig] = None
    ):
        """
        Initialize the unified Quantik engine.
        
        Args:
            state: Initial game state (State object or QFEN string)
            mode: Engine operation mode
            cache_config: Caching configuration
        """
        
    # === CORE GAME OPERATIONS ===
    
    def validate_move(self, move: Move) -> bool:
        """Validate if a move is legal in current position."""
        
    def apply_move(self, move: Move) -> 'QuantikEngine':
        """Apply move and return new engine instance (immutable)."""
        
    def generate_legal_moves(self, player: Optional[PlayerId] = None) -> List[Move]:
        """Generate all legal moves for the specified player."""
        
    def get_game_result(self) -> GameResult:
        """Get current game result (ongoing, player win, draw)."""
        
    def get_current_player(self) -> PlayerId:
        """Get the player to move in current position."""
        
    # === ANALYTICS SUPPORT ===
    
    def analyze_position(self) -> Dict[str, Any]:
        """
        Comprehensive position analysis for analytics models.
        
        Returns:
            Dictionary with:
            - piece_counts: Pieces on board by player/shape
            - mobility_scores: Number of legal moves per player  
            - positional_features: Board control metrics
            - symmetry_class: Canonical position data
            - endgame_distance: Estimated moves to game end
        """
        
    def get_position_features(self) -> np.ndarray:
        """Extract numeric features for ML models (analytics)."""
        
    def calculate_position_hash(self) -> bytes:
        """Get canonical hash for position caching/lookup."""
        
    # === MCTS SUPPORT ===
    
    def expand_node(self) -> List['QuantikEngine']:
        """Fast expansion for MCTS - return all child positions."""
        
    def evaluate_position(self, evaluator: Callable[['QuantikEngine'], float]) -> float:
        """Apply position evaluation function (for MCTS rollouts)."""
        
    def get_mcts_prior(self) -> Dict[Move, float]:
        """Get move priors for MCTS (based on heuristics)."""
        
    # === GAME TREE SIMULATION ===
    
    def simulate_game_tree(
        self, 
        max_depth: int, 
        pruning: bool = True,
        canonical_only: bool = True
    ) -> 'GameTreeNode':
        """
        Generate complete game tree from current position.
        
        Args:
            max_depth: Maximum search depth
            pruning: Enable position pruning for efficiency
            canonical_only: Use canonical positions to reduce tree size
            
        Returns:
            Root node of the generated game tree
        """
        
    def count_terminal_positions(self, max_depth: int) -> Dict[GameResult, int]:
        """Count game outcomes reachable from current position."""
        
    # === PUZZLE GENERATION ===
    
    def generate_puzzle(
        self, 
        difficulty: str = "medium",
        unique_solution: bool = True
    ) -> 'PuzzleConfiguration':
        """
        Generate puzzle from current position.
        
        Args:
            difficulty: "easy", "medium", "hard", "expert"
            unique_solution: Ensure puzzle has only one solution
            
        Returns:
            Puzzle configuration with position and metadata
        """
        
    def find_forced_sequences(self, max_depth: int = 10) -> List[List[Move]]:
        """Find forcing move sequences (for puzzle creation)."""
        
    # === OPENING BOOK SUPPORT ===
    
    def save_to_opening_book(self, book_path: str, metadata: Dict[str, Any] = None):
        """Save current position to opening book database."""
        
    def lookup_opening_book(self, book_path: str) -> Optional[Dict[str, Any]]:
        """Look up current position in opening book."""
        
    def get_book_moves(self, book_path: str, top_n: int = 5) -> List[Tuple[Move, float]]:
        """Get top moves from opening book with scores."""
        
    # === SERIALIZATION & PERSISTENCE ===
    
    def to_qfen(self) -> str:
        """Export position as QFEN string."""
        
    def to_compact(self) -> bytes:
        """Export as compact binary format (18 bytes)."""
        
    def to_json(self, include_metadata: bool = True) -> str:
        """Export as JSON for analytics/debugging."""
        
    @classmethod
    def from_qfen(cls, qfen: str, **kwargs) -> 'QuantikEngine':
        """Create engine from QFEN string."""
        
    @classmethod
    def from_compact(cls, data: bytes, **kwargs) -> 'QuantikEngine':
        """Create engine from compact binary data."""
        
    # === BATCH OPERATIONS ===
    
    def process_position_batch(
        self, 
        positions: List[Union[str, bytes, State]], 
        operation: str
    ) -> List[Any]:
        """
        Process multiple positions efficiently.
        
        Args:
            positions: List of positions (QFEN, binary, or State objects)
            operation: "analyze", "legal_moves", "evaluate", etc.
            
        Returns:
            List of operation results for each position
        """
        
    # === STATISTICS & MONITORING ===
    
    def get_stats(self) -> EngineStats:
        """Get engine performance statistics."""
        
    def reset_stats(self):
        """Reset performance counters."""
        
    def cache_info(self) -> Dict[str, Any]:
        """Get cache performance information."""

# Supporting Classes

@dataclass
class GameTreeNode:
    """Node in the generated game tree."""
    engine: QuantikEngine
    move_from_parent: Optional[Move]
    children: List['GameTreeNode']
    is_terminal: bool
    game_result: Optional[GameResult]
    evaluation: Optional[float] = None
    
@dataclass
class PuzzleConfiguration:
    """Configuration for a generated puzzle."""
    position: QuantikEngine
    target_moves: List[Move]
    difficulty_rating: float
    solution_unique: bool
    hints: List[str]
    metadata: Dict[str, Any]
```

### Caching Strategies Implementation

The engine will support multiple caching strategies:

**1. LRU Cache (In-Memory)**
```python
class LRUCacheStrategy:
    """Least Recently Used cache for frequently accessed positions."""
    
    def __init__(self, max_size: int = 1000000):
        self._cache = {}  # Using functools.lru_cache internally
        self._max_size = max_size
        
    def get(self, key: bytes) -> Optional[Any]:
        """Retrieve cached value by canonical position hash."""
        
    def set(self, key: bytes, value: Any):
        """Store value with automatic LRU eviction."""
        
    def batch_get(self, keys: List[bytes]) -> Dict[bytes, Any]:
        """Efficient batch retrieval."""
        
    def batch_set(self, items: Dict[bytes, Any]):
        """Efficient batch storage."""
```

**2. File System Cache**
```python
class FileSystemCacheStrategy:
    """Persistent file-based cache for large datasets."""
    
    def __init__(self, cache_dir: str, max_size_gb: float = 10.0):
        self._cache_dir = Path(cache_dir)
        self._max_size_bytes = int(max_size_gb * 1024**3)
        
    def get(self, key: bytes) -> Optional[Any]:
        """Load from disk using canonical hash as filename."""
        
    def set(self, key: bytes, value: Any):
        """Save to disk with compression."""
        
    def cleanup_old_entries(self):
        """Remove oldest files when size limit exceeded."""
```

**3. Network Cache (Future Extension)**
```python
class NetworkCacheStrategy:
    """Network-based cache for distributed systems."""
    
    def __init__(self, base_url: str, auth_token: Optional[str] = None):
        self._base_url = base_url
        self._auth_token = auth_token
        
    async def get(self, key: bytes) -> Optional[Any]:
        """Retrieve from remote cache server."""
        
    async def set(self, key: bytes, value: Any):
        """Store in remote cache server."""
        
    async def batch_operations(self, operations: List[Tuple[str, bytes, Any]]):
        """Efficient batch operations over network."""
```

## Implementation Strategy

### Phase 1: Core Engine Structure (Week 1)

**Tasks**:
1. Create `src/quantik_core/engine.py` with basic QuantikEngine class
2. Implement core methods using existing components:
   - `validate_move()` → delegate to `move.validate_move()`
   - `apply_move()` → use `move.apply_move()` with State wrapper
   - `generate_legal_moves()` → delegate to `move.generate_legal_moves()`
   - `get_game_result()` → use existing game result detection
3. Add comprehensive test suite in `tests/test_engine.py`
4. Ensure backward compatibility with existing APIs

**Success Criteria**:
- All existing tests continue passing
- Basic engine operations functional
- Memory usage optimized (using CompactBitboard backend)

### Phase 2: Analytics & MCTS Support (Week 2)

**Tasks**:
1. Implement `analyze_position()` using `game_stats.py` functionality
2. Add `get_position_features()` for ML models
3. Implement efficient `expand_node()` for MCTS
4. Add position evaluation framework
5. Create comprehensive position hashing with canonical forms

**Success Criteria**:
- Rich analytics data extraction
- Fast MCTS node expansion (<1ms per node)
- Canonical position matching for transposition tables

### Phase 3: Advanced Features (Week 3)

**Tasks**:
1. Implement `simulate_game_tree()` with parallel processing support
2. Add puzzle generation algorithms
3. Create opening book management system
4. Implement batch processing operations
5. Add comprehensive caching strategies

**Success Criteria**:
- Complete game tree generation for reasonable depths
- Functional puzzle generation
- Opening book save/load operations
- Efficient batch processing

### Phase 4: Performance & Polish (Week 4)

**Tasks**:
1. Performance optimization and profiling
2. Comprehensive documentation and examples
3. Integration with existing examples
4. Benchmarking against individual components
5. Memory usage optimization

**Success Criteria**:
- Performance parity or improvement vs individual components
- Complete API documentation
- Working examples for all use cases
- Memory usage within targets

## Integration Points

### With Existing Codebase

**1. State Management**
- Engine wraps `State` class as primary representation
- Uses `CompactBitboard` backend for memory efficiency
- Maintains immutability for functional-style operations

**2. Move Operations**
- Delegates to existing `move.py` functions
- Wraps results in Engine objects for method chaining
- Optimizes for bulk operations

**3. Serialization**
- Uses existing QFEN, pack/unpack, and CBOR formats
- Adds JSON export for debugging/analytics
- Maintains canonical position handling

**4. Analytics Integration**
- Incorporates `game_stats.py` functionality
- Adds ML-friendly feature extraction
- Supports statistical analysis workflows

### External Integration

**1. MCTS Libraries**
- Compatible with existing MCTS implementations
- Provides fast node expansion and evaluation
- Supports transposition tables via canonical hashing

**2. Database Systems**
- Opening book storage in SQLite/PostgreSQL
- Efficient position lookup and storage
- Batch import/export capabilities

**3. Analytics Pipelines**
- NumPy array export for ML models
- JSON export for data analysis
- Statistical aggregation support

## Risk Assessment & Mitigation

### Technical Risks

**1. Performance Regression**
- *Risk*: Wrapper overhead impacts performance
- *Mitigation*: Direct delegation to optimized functions, benchmark-driven development

**2. Memory Usage**
- *Risk*: Additional wrapper objects increase memory usage
- *Mitigation*: Use `__slots__`, minimize object creation, profile memory usage

**3. API Complexity**
- *Risk*: Too many methods make API confusing
- *Mitigation*: Group methods by use case, comprehensive documentation, clear examples

### Development Risks

**1. Backward Compatibility**
- *Risk*: Breaking existing code during integration
- *Mitigation*: Maintain existing APIs, add deprecation warnings, provide migration guide

**2. Testing Complexity**
- *Risk*: Comprehensive testing becomes unwieldy
- *Mitigation*: Modular test design, focus on integration tests, reuse existing test fixtures

## Success Metrics

### Functional Requirements
- [ ] All 6 use cases (analytics, MCTS, etc.) supported with dedicated methods
- [ ] Multiple caching strategies implemented and configurable
- [ ] Batch operations support for efficient processing
- [ ] Complete backward compatibility maintained

### Performance Requirements  
- [ ] Move generation: <1ms for typical positions
- [ ] Position analysis: <5ms for comprehensive analytics
- [ ] Memory usage: ≤10% overhead vs direct State usage
- [ ] Cache hit ratio: >80% for repeated position access

### Quality Requirements
- [ ] 100% test coverage for new engine functionality
- [ ] Complete API documentation with examples
- [ ] Performance benchmarks vs individual components
- [ ] Memory profiling and optimization verification

This design provides a comprehensive foundation for implementing the unified QuantikEngine while leveraging the existing optimized codebase components.