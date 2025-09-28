
# QUANTIK SYMMETRY REDUCTION DEMONSTRATION


This document demonstrates how symmetry handling can dramatically reduce
the complexity of the Quantik game search space.


### Empty Board

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

## First Move Canonicalization


In Quantik, the first player has 64 possible moves (4 shapes × 16 positions).
However, due to symmetries, many of these are equivalent.

By applying symmetry reductions, we can map all first moves to just a few
canonical positions.


### Canonical First Move Positions:
```
┌───┬───┬───┬───┐
│     │     │     │     │
├───┼───┼───┼───┤
│     │     │     │     │
├───┼───┼───┼───┤
│  8  │  9  │     │     │
├───┼───┼───┼───┤
│  12 │     │     │     │
└───┴───┴───┴───┘
```

### Position Mappings to Canonical Forms:

#### Positions equivalent to (2,0):
```
┌───┬───┬───┬───┐
│ · │ ● │ ● │ · │
├───┼───┼───┼───┤
│ ● │ · │ · │ ● │
├───┼───┼───┼───┤
│ ● │ · │ · │ ● │
├───┼───┼───┼───┤
│ · │ ● │ ● │ · │
└───┴───┴───┴───┘
```
Total: 8 positions

#### Positions equivalent to (2,1):
```
┌───┬───┬───┬───┐
│ · │ · │ · │ · │
├───┼───┼───┼───┤
│ · │ ● │ ● │ · │
├───┼───┼───┼───┤
│ · │ ● │ ● │ · │
├───┼───┼───┼───┤
│ · │ · │ · │ · │
└───┴───┴───┴───┘
```
Total: 4 positions

#### Positions equivalent to (3,0):
```
┌───┬───┬───┬───┐
│ ● │ · │ · │ ● │
├───┼───┼───┼───┤
│ · │ · │ · │ · │
├───┼───┼───┼───┤
│ · │ · │ · │ · │
├───┼───┼───┼───┤
│ ● │ · │ · │ ● │
└───┴───┴───┴───┘
```
Total: 4 positions

### Visualization of Canonical Position Mapping:
This grid shows where each position maps to in canonical form:
```
┌───┬───┬───┬───┐
│ C │ A │ A │ C │
├───┼───┼───┼───┤
│ A │ B │ B │ A │
├───┼───┼───┼───┤
│ A │ B │ B │ A │
├───┼───┼───┼───┤
│ C │ A │ A │ C │
└───┴───┴───┴───┘
```
Where: A = maps to (2,0), B = maps to (2,1), C = maps to (3,0)

### Total unique first moves after symmetry reduction:
* **Unique positions:** 3
* **Reduction factor:** 5.33x

## Example Canonical Forms


### Position (0,0)

### Original Position

```
  ┌───┬───┬───┬───┐
0 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form SymmetryTransform(d4_index=3, color_swap=True, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ d │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```
Maps to canonical position (3,0)

### Position (1,1)

### Original Position

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form SymmetryTransform(d4_index=3, color_swap=True, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ d │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```
Maps to canonical position (2,1)

### Position (3,3)

### Original Position

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ A │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form SymmetryTransform(d4_index=1, color_swap=True, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ d │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```
Maps to canonical position (3,0)

## Second and Third Move Canonicalization


### Second Move After First Move at (2,0)

### Position after first move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 1
Move: Player 1, Shape 3 at position (0,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ c │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

##### Third Move Example After Above
Move: Player 0, Shape 3 at position (3,1)

### After third move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ D │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ c │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ d │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 2
Move: Player 1, Shape 0 at position (3,3)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ a │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ d │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 3
Move: Player 1, Shape 0 at position (0,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ a │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Second Move After First Move at (2,1)

### Position after first move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 1
Move: Player 1, Shape 1 at position (2,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ A │ b │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(2, 3, 1, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ c │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

##### Third Move Example After Above
Move: Player 0, Shape 0 at position (2,0)

### After third move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ A │ b │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ c │ c │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 2
Move: Player 1, Shape 1 at position (1,3)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ b │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=2, color_swap=True, shape_perm=(2, 3, 0, 1))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ c │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 3
Move: Player 1, Shape 1 at position (1,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ b │ . │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(2, 3, 1, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ c │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Second Move After First Move at (3,0)

### Position after first move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 1
Move: Player 1, Shape 3 at position (2,1)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ d │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=True, shape_perm=(1, 2, 0, 3))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ c │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

##### Third Move Example After Above
Move: Player 0, Shape 3 at position (1,3)

### After third move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ D │
  ├───┼───┼───┼───┤
2 │ . │ d │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ c │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 2
Move: Player 1, Shape 0 at position (2,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ a │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=4, color_swap=True, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ d │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 3
Move: Player 1, Shape 3 at position (1,1)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ d │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=3, color_swap=True, shape_perm=(1, 2, 0, 3))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ c │
  └───┴───┴───┴───┘
    0   1   2   3  
```

## Is Canonical Representation Deterministic?


A critical property of any canonical representation system is determinism -
the same game state must always map to the same canonical form, regardless of
how that state was reached. Let's verify this property:


### Testing Determinism

### State 1

```
  ┌───┬───┬───┬───┐
0 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ b │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ C │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### State 2

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ A │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ C │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ b │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form of State 1 - SymmetryTransform(d4_index=3, color_swap=True, shape_perm=(3, 0, 2, 1))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ c │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ b │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form of State 2 - SymmetryTransform(d4_index=1, color_swap=True, shape_perm=(3, 0, 2, 1))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ c │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ b │
  └───┴───┴───┴───┘
    0   1   2   3  
```

**Result:** The canonical representation is NOT deterministic! This is a serious issue that needs to be fixed.
Canonical QFEN 1: `..../..c./.D../b...`
Canonical QFEN 2: `..../.c../D.../...b`

### Implications for Game Search

The deterministic property of our canonical representation is crucial for:

1. **Transposition Tables:** We can safely use canonical positions as keys in our
   transposition tables, knowing that equivalent positions will always hash to the same key.

2. **Learning Algorithms:** When training reinforcement learning agents or building
   opening books, we can properly aggregate data from equivalent positions.

3. **Consistency:** Game analysis and search will be consistent and reliable across
   different move sequences that lead to equivalent positions.


## CONCLUSION


We've demonstrated how symmetry handling can dramatically reduce the complexity
of the Quantik game search space. The main benefits are:

1. First move: From 64 possible moves to just 3 canonical positions
2. Entire game tree reduction by a factor of 24 (8 spatial symmetries × 3 shape permutations)
3. Second and third move canonicalization continues to reduce the branching factor

**IMPORTANT FINDING:** Our determinism test revealed that the current canonical
representation is NOT deterministic! This is a critical issue that needs to be addressed
before using the symmetry reduction in production, as it could lead to inconsistent behavior in:
- Transposition tables
- Opening books
- Learning algorithms

This indicates a potential bug in the symmetry handling implementation that should be fixed.

Once fixed, this approach will enable much more efficient game analysis, as we can:
- Store evaluations for canonical positions only
- Analyze a much smaller search space
- Still recover the actual moves through symmetry transformations
- Build reliable opening books and transposition tables


### Position Mappings to Canonical Forms:

#### Positions equivalent to (2,0):
```
┌───┬───┬───┬───┐
│ · │ ● │ ● │ · │
├───┼───┼───┼───┤
│ ● │ · │ · │ ● │
├───┼───┼───┼───┤
│ ● │ · │ · │ ● │
├───┼───┼───┼───┤
│ · │ ● │ ● │ · │
└───┴───┴───┴───┘
```
Total: 16 positions

#### Positions equivalent to (2,1):
```
┌───┬───┬───┬───┐
│ · │ · │ · │ · │
├───┼───┼───┼───┤
│ · │ ● │ ● │ · │
├───┼───┼───┼───┤
│ · │ ● │ ● │ · │
├───┼───┼───┼───┤
│ · │ · │ · │ · │
└───┴───┴───┴───┘
```
Total: 8 positions

#### Positions equivalent to (3,0):
```
┌───┬───┬───┬───┐
│ ● │ · │ · │ ● │
├───┼───┼───┼───┤
│ · │ · │ · │ · │
├───┼───┼───┼───┤
│ · │ · │ · │ · │
├───┼───┼───┼───┤
│ ● │ · │ · │ ● │
└───┴───┴───┴───┘
```
Total: 8 positions

### Visualization of Canonical Position Mapping:
This grid shows where each position maps to in canonical form:
```
┌───┬───┬───┬───┐
│ C │ A │ A │ C │
├───┼───┼───┼───┤
│ A │ B │ B │ A │
├───┼───┼───┼───┤
│ A │ B │ B │ A │
├───┼───┼───┼───┤
│ C │ A │ A │ C │
└───┴───┴───┴───┘
```
Where: A = maps to (2,0), B = maps to (2,1), C = maps to (3,0)

### Total unique first moves after symmetry reduction:
* **Unique positions:** 3
* **Reduction factor:** 5.33x

## Example Canonical Forms


### Position (0,0)

### Original Position

```
  ┌───┬───┬───┬───┐
0 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ d │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```
Maps to canonical position (3,0)

### Position (1,1)

### Original Position

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ d │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```
Maps to canonical position (2,1)

### Position (3,3)

### Original Position

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ A │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ d │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```
Maps to canonical position (3,0)

## Second and Third Move Canonicalization


### Second Move After First Move at (2,0)

### Position after first move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 1
Move: Player 1, Shape 2 at position (3,0)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ c │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 3, 2, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ c │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

##### Third Move Example After Above
Move: Player 0, Shape 1 at position (3,3)

### After third move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ c │ . │ . │ B │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=True, shape_perm=(3, 0, 1, 2))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ b │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ D │ . │ . │ c │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 2
Move: Player 1, Shape 0 at position (1,3)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ a │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ d │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 3
Move: Player 1, Shape 2 at position (3,3)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ c │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 3, 2, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ c │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Second Move After First Move at (2,1)

### Position after first move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 1
Move: Player 1, Shape 0 at position (0,3)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ a │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=False, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ d │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

##### Third Move Example After Above
Move: Player 0, Shape 1 at position (1,3)

### After third move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ a │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ B │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=2, color_swap=True, shape_perm=(2, 3, 1, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
2 │ c │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ D │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 2
Move: Player 1, Shape 0 at position (0,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ a │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=6, color_swap=True, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 3
Move: Player 1, Shape 0 at position (1,3)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ a │
  ├───┼───┼───┼───┤
2 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=2, color_swap=True, shape_perm=(1, 2, 3, 0))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ d │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Second Move After First Move at (3,0)

### Position after first move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 1
Move: Player 1, Shape 1 at position (1,2)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ b │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=2, color_swap=True, shape_perm=(2, 3, 0, 1))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ c │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

##### Third Move Example After Above
Move: Player 0, Shape 0 at position (0,1)

### After third move

```
  ┌───┬───┬───┬───┐
0 │ . │ A │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ b │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=2, color_swap=True, shape_perm=(2, 3, 0, 1))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ c │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ c │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 2
Move: Player 1, Shape 2 at position (2,1)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ c │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=0, color_swap=True, shape_perm=(1, 3, 0, 2))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ c │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

#### Second Move Example 3
Move: Player 1, Shape 3 at position (0,0)

### After second move

```
  ┌───┬───┬───┬───┐
0 │ d │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ A │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical form SymmetryTransform(d4_index=3, color_swap=True, shape_perm=(1, 2, 0, 3))

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ D │ . │ . │ c │
  └───┴───┴───┴───┘
    0   1   2   3  
```

## Is Canonical Representation Deterministic?


A critical property of any canonical representation system is determinism -
the same game state must always map to the same canonical form, regardless of
how that state was reached. Let's verify this property:


### Testing Determinism

### State 1

```
  ┌───┬───┬───┬───┐
0 │ A │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ b │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ . │ C │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### State 2

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ A │
  ├───┼───┼───┼───┤
1 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
2 │ . │ C │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ b │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form of State 1

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ . │ c │ . │
  ├───┼───┼───┼───┤
2 │ . │ D │ . │ . │
  ├───┼───┼───┼───┤
3 │ b │ . │ . │ . │
  └───┴───┴───┴───┘
    0   1   2   3  
```

### Canonical Form of State 2

```
  ┌───┬───┬───┬───┐
0 │ . │ . │ . │ . │
  ├───┼───┼───┼───┤
1 │ . │ c │ . │ . │
  ├───┼───┼───┼───┤
2 │ D │ . │ . │ . │
  ├───┼───┼───┼───┤
3 │ . │ . │ . │ b │
  └───┴───┴───┴───┘
    0   1   2   3  
```

**Result:** The canonical representation is NOT deterministic! This is a serious issue that needs to be fixed.
Canonical QFEN 1: `..../..c./.D../b...`
Canonical QFEN 2: `..../.c../D.../...b`

### Implications for Game Search

The deterministic property of our canonical representation is crucial for:

1. **Transposition Tables:** We can safely use canonical positions as keys in our
   transposition tables, knowing that equivalent positions will always hash to the same key.

2. **Learning Algorithms:** When training reinforcement learning agents or building
   opening books, we can properly aggregate data from equivalent positions.

3. **Consistency:** Game analysis and search will be consistent and reliable across
   different move sequences that lead to equivalent positions.


## CONCLUSION


We've demonstrated how symmetry handling can dramatically reduce the complexity
of the Quantik game search space. The main benefits are:

1. First move: From 64 possible moves to just 3 canonical positions
2. Entire game tree reduction by a factor of 24 (8 spatial symmetries × 3 shape permutations)
3. Second and third move canonicalization continues to reduce the branching factor

**IMPORTANT FINDING:** Our determinism test revealed that the current canonical
representation is NOT deterministic! This is a critical issue that needs to be addressed
before using the symmetry reduction in production, as it could lead to inconsistent behavior in:
- Transposition tables
- Opening books
- Learning algorithms

This indicates a potential bug in the symmetry handling implementation that should be fixed.

Once fixed, this approach will enable much more efficient game analysis, as we can:
- Store evaluations for canonical positions only
- Analyze a much smaller search space
- Still recover the actual moves through symmetry transformations
- Build reliable opening books and transposition tables

