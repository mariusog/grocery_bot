"""Shared fixtures and helpers for game_state tests."""

from grocery_bot.game_state import GameState


def _make_gs_with_dropoff(items=None, walls=None, width=11, height=9, drop_off=None):
    """Create a GameState with dropoff zones precomputed."""
    state = {
        "grid": {
            "width": width,
            "height": height,
            "walls": walls or [],
        },
        "items": items or [],
        "drop_off": drop_off or [1, 8],
    }
    gs = GameState()
    gs.init_static(state)
    return gs
