"""Tests for log replay verification feature."""

import csv
import json

from grocery_bot.simulator.log_replay import parse_actions, replay_log


def _write_test_log(tmp_path, rounds_data):
    """Write a minimal CSV + JSON pair for testing.

    rounds_data: list of (round, score, actions_list) tuples.
    Each action: dict with bot_id, bot_pos, inventory, action, item_id.
    """
    csv_path = tmp_path / "game_test.csv"
    json_path = tmp_path / "game_test.json"

    rows = []
    for rnd, score, actions in rounds_data:
        for a in actions:
            rows.append(
                {
                    "round": rnd,
                    "score": score,
                    "order_idx": a.get("order_idx", 0),
                    "bot_id": a["bot_id"],
                    "bot_pos": a.get("bot_pos", "10,8"),
                    "inventory": a.get("inventory", ""),
                    "action": a["action"],
                    "item_id": a.get("item_id", ""),
                    "active_needed": "",
                    "active_delivered": "",
                    "preview_needed": "",
                }
            )

    fieldnames = [
        "round",
        "score",
        "order_idx",
        "bot_id",
        "bot_pos",
        "inventory",
        "action",
        "item_id",
        "active_needed",
        "active_delivered",
        "preview_needed",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    meta = {
        "grid": {
            "width": 12,
            "height": 10,
            "walls": 0,
            "wall_positions": [],
        },
        "bots": 1,
        "items_on_map": 4,
        "item_types": ["butter", "cheese", "milk", "yogurt"],
        "item_positions": [
            {"type": "butter", "position": [3, 2]},
            {"type": "cheese", "position": [5, 2]},
            {"type": "milk", "position": [3, 4]},
            {"type": "yogurt", "position": [5, 4]},
        ],
        "drop_off": [1, 8],
        "drop_off_zones": [[1, 8]],
        "max_rounds": 10,
        "total_orders": 2,
        "spawn": [10, 8],
        "orders": [
            {"id": "order_0", "items_required": ["butter", "cheese", "milk"]},
            {"id": "order_1", "items_required": ["yogurt", "milk"]},
        ],
    }
    with open(json_path, "w") as f:
        json.dump(meta, f)

    return str(csv_path), str(json_path)


class TestParseActions:
    def test_parses_single_bot_round(self, tmp_path):
        csv_path, _ = _write_test_log(
            tmp_path,
            [
                (0, 0, [{"bot_id": 0, "action": "move_left"}]),
            ],
        )
        rounds = parse_actions(csv_path)
        assert len(rounds) == 1
        assert rounds[0]["round"] == 0
        assert rounds[0]["live_score"] == 0
        assert len(rounds[0]["actions"]) == 1
        assert rounds[0]["actions"][0]["action"] == "move_left"

    def test_parses_multi_bot_round(self, tmp_path):
        csv_path, _ = _write_test_log(
            tmp_path,
            [
                (
                    0,
                    0,
                    [
                        {"bot_id": 0, "action": "move_left"},
                        {"bot_id": 1, "action": "move_right"},
                    ],
                ),
            ],
        )
        rounds = parse_actions(csv_path)
        assert len(rounds) == 1
        assert len(rounds[0]["actions"]) == 2

    def test_parses_pickup_with_item_id(self, tmp_path):
        csv_path, _ = _write_test_log(
            tmp_path,
            [
                (0, 0, [{"bot_id": 0, "action": "pick_up", "item_id": "item_0"}]),
            ],
        )
        rounds = parse_actions(csv_path)
        assert rounds[0]["actions"][0]["item_id"] == "item_0"


class TestReplayLog:
    def test_move_only_no_divergence(self, tmp_path):
        csv_path, json_path = _write_test_log(
            tmp_path,
            [
                (0, 0, [{"bot_id": 0, "action": "move_left"}]),
                (1, 0, [{"bot_id": 0, "action": "move_left"}]),
            ],
        )
        result = replay_log(csv_path, json_path)
        assert result["sim_final_score"] == 0
        assert result["live_final_score"] == 0
        assert result["first_divergence"] is None
        assert result["total_divergences"] == 0

    def test_detects_score_divergence(self, tmp_path):
        """If live score jumps but sim doesn't, report divergence."""
        csv_path, json_path = _write_test_log(
            tmp_path,
            [
                (0, 0, [{"bot_id": 0, "action": "move_left"}]),
                (1, 5, [{"bot_id": 0, "action": "move_left"}]),  # live says +5
            ],
        )
        result = replay_log(csv_path, json_path)
        # Sim can't score from just moving, so there should be divergence
        assert result["total_divergences"] > 0
        assert result["first_divergence"] is not None

    def test_result_has_per_round_data(self, tmp_path):
        csv_path, json_path = _write_test_log(
            tmp_path,
            [
                (0, 0, [{"bot_id": 0, "action": "wait"}]),
            ],
        )
        result = replay_log(csv_path, json_path)
        assert "rounds" in result
        assert len(result["rounds"]) == 1
        assert "sim_score" in result["rounds"][0]
        assert "live_score" in result["rounds"][0]
