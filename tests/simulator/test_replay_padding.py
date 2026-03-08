"""Tests for ReplaySimulator synthetic tail padding."""

import json

from benchmark_reporting import run_replay_game
from grocery_bot.simulator import ReplaySimulator


def _write_recorded_map(tmp_path, total_orders=5):
    map_path = tmp_path / "2026-03-07_22x14_5bot.json"
    recorded = {
        "version": 1,
        "recorded_at": "2026-03-07T00:00:00Z",
        "source": "live",
        "grid": {
            "width": 22,
            "height": 14,
            "walls": [],
        },
        "drop_off": [1, 12],
        "spawn": [20, 12],
        "num_bots": 5,
        "max_rounds": 0,
        "total_orders": total_orders,
        "items": [
            {"id": "item_0", "type": "milk", "position": [3, 2]},
            {"id": "item_1", "type": "bread", "position": [5, 2]},
            {"id": "item_2", "type": "cheese", "position": [7, 2]},
            {"id": "item_3", "type": "yogurt", "position": [9, 2]},
        ],
        "orders": [
            {"id": "order_0", "items_required": ["milk", "bread", "cheese"]},
            {"id": "order_1", "items_required": ["bread", "milk", "yogurt"]},
        ],
    }
    map_path.write_text(json.dumps(recorded))
    return map_path


def test_replay_simulator_pads_unknown_orders(tmp_path):
    map_path = _write_recorded_map(tmp_path, total_orders=5)

    sim = ReplaySimulator(str(map_path))

    assert sim.recorded_order_count == 2
    assert sim.synthetic_order_count == 3
    assert len(sim.orders) == 5
    assert sim.orders[0]["items_required"] == ["milk", "bread", "cheese"]
    assert sim.orders[1]["items_required"] == ["bread", "milk", "yogurt"]
    assert [order["id"] for order in sim.orders[2:]] == [
        "order_2",
        "order_3",
        "order_4",
    ]
    assert all(3 <= len(order["items_required"]) <= 5 for order in sim.orders[2:])


def test_replay_simulator_can_disable_padding(tmp_path):
    map_path = _write_recorded_map(tmp_path, total_orders=5)

    sim = ReplaySimulator(str(map_path), pad_orders=False)

    assert sim.recorded_order_count == 2
    assert sim.synthetic_order_count == 0
    assert len(sim.orders) == 2


def test_run_replay_game_reports_recorded_and_padded_order_counts(tmp_path):
    map_path = _write_recorded_map(tmp_path, total_orders=5)

    result = run_replay_game(str(map_path))

    assert result["recorded_orders"] == 2
    assert result["synthetic_orders"] == 3
    assert result["total_orders"] == 5


def test_replay_simulator_uses_nightmare_default_total_when_missing(tmp_path):
    map_path = tmp_path / "2026-03-07_30x18_20bot.json"
    recorded = {
        "version": 1,
        "recorded_at": "2026-03-07T00:00:00Z",
        "source": "live",
        "grid": {
            "width": 30,
            "height": 18,
            "walls": [],
        },
        "drop_off": [1, 16],
        "spawn": [28, 16],
        "num_bots": 20,
        "max_rounds": 500,
        "items": [
            {"id": "item_0", "type": "milk", "position": [3, 2]},
            {"id": "item_1", "type": "bread", "position": [5, 2]},
            {"id": "item_2", "type": "cheese", "position": [7, 2]},
            {"id": "item_3", "type": "yogurt", "position": [9, 2]},
        ],
        "orders": [
            {"id": "order_0", "items_required": ["milk", "bread", "cheese"]},
        ],
    }
    map_path.write_text(json.dumps(recorded))

    sim = ReplaySimulator(str(map_path))

    assert sim.recorded_order_count == 1
    assert sim.total_orders == 100
    assert sim.synthetic_order_count == 99
