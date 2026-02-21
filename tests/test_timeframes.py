"""Unit tests for utils.timeframes."""

import pytest
from trading_bot.utils.timeframes import timeframe_minutes


def test_timeframe_minutes():
    assert timeframe_minutes("5m") == 5
    assert timeframe_minutes("1h") == 60
    assert timeframe_minutes("1d") == 1440


def test_timeframe_invalid():
    with pytest.raises(ValueError):
        timeframe_minutes("1x")
