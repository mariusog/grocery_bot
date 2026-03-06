"""Shared fixtures and helpers for grocery bot tests."""

import sys
import os

# Ensure project root is on the import path so tests can import bot, simulator, etc.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import bot
from simulator import GameSimulator, run_benchmark, DIFFICULTY_PRESETS, profile_congestion


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "slow: marks tests as slow (deselect with '-m \"not slow\"')")


@pytest.fixture(autouse=True)
def _reset_bot():
    """Auto-reset bot state before every test."""
    bot.reset_state()


def make_state(
    bots=None,
    items=None,
    orders=None,
    drop_off=None,
    walls=None,
    width=11,
    height=9,
    round_num=0,
    max_rounds=300,
    score=0,
):
    """Build a minimal game state dict for testing."""
    return {
        "type": "game_state",
        "round": round_num,
        "max_rounds": max_rounds,
        "grid": {
            "width": width,
            "height": height,
            "walls": walls or [],
        },
        "bots": bots or [],
        "items": items or [],
        "orders": orders or [],
        "drop_off": drop_off or [1, 8],
        "score": score,
        "active_order_index": 0,
        "total_orders": 5,
    }


def reset_bot():
    """Reset global state between tests."""
    bot.reset_state()


def get_action(actions, bot_id=0):
    """Extract action for a specific bot."""
    for a in actions:
        if a["bot"] == bot_id:
            return a
    return None
