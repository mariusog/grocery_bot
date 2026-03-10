"""Difficulty presets for the grocery bot simulator."""

from typing import Any

DIFFICULTY_PRESETS: dict[str, dict[str, Any]] = {
    "Easy": {
        "num_bots": 1,
        "width": 12,
        "height": 10,
        "num_item_types": 4,
        "items_per_order": (3, 4),
        "max_rounds": 300,
    },
    "Medium": {
        "num_bots": 3,
        "width": 16,
        "height": 12,
        "num_item_types": 8,
        "items_per_order": (3, 5),
        "max_rounds": 300,
    },
    "Hard": {
        "num_bots": 5,
        "width": 22,
        "height": 14,
        "num_item_types": 12,
        "items_per_order": (3, 5),
        "max_rounds": 300,
    },
    "Expert": {
        "num_bots": 10,
        "width": 28,
        "height": 18,
        "num_item_types": 16,
        "items_per_order": (4, 6),
        "max_rounds": 300,
    },
    "Nightmare": {
        "num_bots": 20,
        "width": 30,
        "height": 18,
        "num_item_types": 21,
        "items_per_order": (4, 6),
        "max_rounds": 500,
    },
}
