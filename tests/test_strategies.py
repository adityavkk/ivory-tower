"""Tests for the strategy registry and protocol."""

from __future__ import annotations

import pytest

from ivory_tower.strategies import get_strategy, list_strategies, STRATEGIES
from ivory_tower.strategies.base import ResearchStrategy
from ivory_tower.strategies.council import CouncilStrategy


class TestGetStrategy:
    """Tests for get_strategy()."""

    def test_get_council_returns_council_strategy(self):
        strategy = get_strategy("council")
        assert isinstance(strategy, CouncilStrategy)

    def test_get_unknown_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown strategy 'unknown'"):
            get_strategy("unknown")

    def test_error_message_lists_available(self):
        with pytest.raises(ValueError, match="Available: "):
            get_strategy("nonexistent")

    def test_returns_fresh_instance_each_call(self):
        a = get_strategy("council")
        b = get_strategy("council")
        assert a is not b


class TestListStrategies:
    """Tests for list_strategies()."""

    def test_returns_list_of_tuples(self):
        result = list_strategies()
        assert isinstance(result, list)
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2

    def test_council_in_list(self):
        result = list_strategies()
        names = [name for name, _desc in result]
        assert "council" in names

    def test_descriptions_are_non_empty(self):
        result = list_strategies()
        for _name, desc in result:
            assert desc  # non-empty string


class TestCouncilStrategyAttributes:
    """Tests for CouncilStrategy stub attributes."""

    def test_name(self):
        s = CouncilStrategy()
        assert s.name == "council"

    def test_description(self):
        s = CouncilStrategy()
        assert s.description  # non-empty
