"""Strategy registry for ivory-tower research strategies."""

from __future__ import annotations

from ivory_tower.strategies.base import ResearchStrategy
from ivory_tower.strategies.council import CouncilStrategy
from ivory_tower.strategies.adversarial import AdversarialStrategy
from ivory_tower.strategies.debate import DebateStrategy
from ivory_tower.strategies.map_reduce import MapReduceStrategy
from ivory_tower.strategies.red_blue import RedBlueStrategy

STRATEGIES: dict[str, type] = {
    "council": CouncilStrategy,
    "adversarial": AdversarialStrategy,
    "debate": DebateStrategy,
    "map-reduce": MapReduceStrategy,
    "red-blue": RedBlueStrategy,
}


def get_strategy(name: str) -> ResearchStrategy:
    """Return an instantiated strategy by name.

    Raises ValueError for unknown strategy names.
    """
    cls = STRATEGIES.get(name)
    if cls is None:
        available = ", ".join(sorted(STRATEGIES.keys()))
        raise ValueError(
            f"Unknown strategy '{name}'. Available: {available}"
        )
    return cls()


def list_strategies() -> list[tuple[str, str]]:
    """Return list of (name, description) for all registered strategies."""
    return [(cls.name, cls.description) for cls in STRATEGIES.values()]
