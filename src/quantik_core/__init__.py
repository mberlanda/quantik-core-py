"""
Quantik Core - High-performance game state manipulation library.

This library provides the foundational components for building Quantik game engines,
Monte Carlo simulations, and AI analysis tools.
"""

from .core import State, VERSION, FLAG_CANON, D4, permute16, ALL_SHAPE_PERMS

__version__ = "0.1.0"
__author__ = "Mauro Berlanda"

__all__ = [
    "State",
    "VERSION", 
    "FLAG_CANON",
    "D4",
    "permute16",
    "ALL_SHAPE_PERMS",
]
