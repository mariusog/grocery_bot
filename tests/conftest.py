"""Shared fixtures and helpers for grocery bot tests."""

import sys
import os

# Ensure project root is on the import path so tests can import bot, simulator, etc.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import bot


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


def make_planner(
    bots=None,
    items=None,
    orders=None,
    drop_off=None,
    walls=None,
    width=11,
    height=9,
    round_num=0,
    max_rounds=300,
):
    """Create a RoundPlanner with full state initialized for unit testing.

    Calls bot.decide_actions() to initialize GameState, then constructs
    a fresh RoundPlanner and runs plan() so all internal state
    (net_active, bot_assignments, predicted, etc.) is populated.

    Returns the planner object for inspection.
    """
    from round_planner import RoundPlanner

    state = make_state(
        bots=bots or [],
        items=items or [],
        orders=orders or [],
        drop_off=drop_off or [1, 8],
        walls=walls or [],
        width=width,
        height=height,
        round_num=round_num,
        max_rounds=max_rounds,
    )

    # Initialize GameState via bot module (sets blocked_static, caches, etc.)
    bot.reset_state()
    bot.decide_actions(state)

    # Re-create a fresh planner for inspection
    gs = bot._gs
    planner = RoundPlanner(gs, state, full_state=state)
    planner.plan()
    return planner


def make_gs_with_state(
    items=None,
    walls=None,
    width=11,
    height=9,
):
    """Create a bare GameState with init_static called for unit testing.

    Returns (gs, state_dict) so callers can use gs.dist_static(), etc.
    """
    from game_state import GameState

    state = {
        "grid": {
            "width": width,
            "height": height,
            "walls": walls or [],
        },
        "items": items or [],
    }
    gs = GameState()
    gs.init_static(state)
    return gs
