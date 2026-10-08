"""
Refiner Agent - Surgical Email Improvement (Feedback-Focused Iteration).

Takes email + critic feedback and applies targeted fixes.
Preserves original structure, only addresses flagged issues.
Supports loop-back to Critic for re-evaluation (max 3 iterations).

Exports:
- refiner_node: Main LangGraph node function
- MAX_REFINEMENTS: Loop guard constant (3 iterations max)
"""

from app.agents.refiner.node import refiner_node, MAX_REFINEMENTS

__all__ = [
    "refiner_node",
    "MAX_REFINEMENTS",
]
