"""
test_cost_tracking.py — Tests para cost tracking en _cmd_stats.

Verifica:
- Calculo de costos USD
- Stats por periodo (24h, 7d, 30d)
- Display correcto
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from mikalia.notifications.telegram_listener import MikaliaCoreBot


class TestCostEstimation:

    def test_cost_calculation_basic(self):
        """1M tokens = ~$8 USD."""
        cost = MikaliaCoreBot._estimate_cost(1_000_000)
        assert cost == pytest.approx(8.0)

    def test_cost_zero_tokens(self):
        """0 tokens = $0."""
        cost = MikaliaCoreBot._estimate_cost(0)
        assert cost == 0.0

    def test_cost_small_amount(self):
        """10K tokens = ~$0.08."""
        cost = MikaliaCoreBot._estimate_cost(10_000)
        assert cost == pytest.approx(0.08)


class TestStatsCommand:

    def _make_bot(self):
        agent = MagicMock()
        agent.memory.get_last_session.return_value = None
        agent.memory.get_session_stats.return_value = {
            "total_messages": 10, "total_tokens": 5000,
            "user_messages": 5, "assistant_messages": 5,
        }
        agent.memory.get_token_usage.return_value = {
            "total_tokens": 50000, "total_messages": 100, "sessions": 3,
        }
        bot = MikaliaCoreBot(agent)
        bot._session_id = "test-session"
        return bot

    def test_stats_shows_all_periods(self):
        """Stats muestra 24h, 7d y 30d."""
        bot = self._make_bot()
        reply = MagicMock()

        bot._cmd_stats(reply)

        output = reply.call_args[0][0]
        assert "24h" in output
        assert "7 dias" in output
        assert "30 dias" in output

    def test_stats_shows_usd(self):
        """Stats muestra costo en USD."""
        bot = self._make_bot()
        reply = MagicMock()

        bot._cmd_stats(reply)

        output = reply.call_args[0][0]
        assert "USD" in output
        assert "$" in output

    def test_stats_calls_multiple_periods(self):
        """get_token_usage se llama con 24h, 168h y 720h."""
        bot = self._make_bot()
        reply = MagicMock()

        bot._cmd_stats(reply)

        calls = bot._agent.memory.get_token_usage.call_args_list
        hours = [c[1]["hours"] if "hours" in c[1] else c[0][0] for c in calls]
        assert 24 in hours
        assert 168 in hours
        assert 720 in hours
