"""Game loop logging and recording helpers for bot.py.

Public functions:
- ``update_expected_positions`` — predict bot positions after issued actions
- ``update_expected_inventories`` — predict inventories after issued actions
- ``build_map_snapshot`` — capture a JSON-serialisable map snapshot
- ``save_recorded_map`` — write a recorded map to disk
- ``build_game_meta`` — build game-level metadata dict for logging
- ``log_round`` — append one round's data to the CSV/JSON log files
- ``log_game_over`` — write final summary row and close the game log
- ``load_matching_map_orders`` — load recorded orders from a matching map file
"""

import csv
import glob
import json
import os
from datetime import datetime
from typing import Any

from grocery_bot.orders import get_needed_items


def update_expected_positions(
    expected: dict[int, tuple[int, int]], data: dict[str, Any], actions: list[dict[str, Any]]
) -> None:
    """Predict where each bot will be next round based on actions sent."""
    bots_by_id = {b["id"]: b for b in data["bots"]}
    for a in actions:
        bid = a["bot"]
        bot = bots_by_id.get(bid)
        if not bot:
            continue
        bx, by = bot["position"]
        action = a["action"]
        if action == "move_up":
            expected[bid] = (bx, by - 1)
        elif action == "move_down":
            expected[bid] = (bx, by + 1)
        elif action == "move_left":
            expected[bid] = (bx - 1, by)
        elif action == "move_right":
            expected[bid] = (bx + 1, by)
        else:
            expected[bid] = (bx, by)


def update_expected_inventories(
    expected: dict[int, list[str] | None],
    data: dict[str, Any],
    actions: list[dict[str, Any]],
) -> None:
    """Predict inventory after actions (for desync detection).

    Note: drop_off only drops items matching the active order, not all items.
    Since we can't perfectly predict which items the server will accept,
    we skip inventory prediction for drop_off.
    """
    bots_by_id = {b["id"]: b for b in data["bots"]}
    items_by_id = {it["id"]: it for it in data.get("items", [])}
    for a in actions:
        bid = a["bot"]
        bot = bots_by_id.get(bid)
        if not bot:
            continue
        inv = list(bot["inventory"])
        action = a["action"]
        if action == "pick_up":
            item_id = a.get("item_id")
            item = items_by_id.get(item_id)
            if item:
                inv.append(item["type"])
            expected[bid] = inv
        elif action == "drop_off":
            expected[bid] = None  # can't predict — server drops only needed items
        else:
            expected[bid] = inv


def build_map_snapshot(data: dict[str, Any], timestamp: str) -> dict[str, Any]:
    """Capture the round-0 game state for map recording."""
    return {
        "version": 1,
        "recorded_at": timestamp,
        "source": "live",
        "grid": data["grid"],
        "drop_off": data["drop_off"],
        "drop_off_zones": data.get("drop_off_zones"),
        "spawn": data["bots"][0]["position"],
        "num_bots": len(data["bots"]),
        "max_rounds": data["max_rounds"],
        "total_orders": data.get("total_orders"),
        "items": [
            {"id": it["id"], "type": it["type"], "position": it["position"]} for it in data["items"]
        ],
    }


def _orders_same_seed(
    existing: list[dict[str, Any]], new: list[dict[str, Any]]
) -> bool:
    """Check if two order lists come from the same game seed."""
    if not existing or not new:
        return True  # Can't compare, assume compatible
    old_first = sorted(existing[0].get("items_required", []))
    new_first = sorted(new[0].get("items_required", []))
    return old_first == new_first


def save_recorded_map(
    map_snapshot: dict[str, Any], recorded_orders: list[dict[str, Any]], timestamp: str
) -> None:
    """Write recorded map + orders to maps/ directory."""
    if not map_snapshot:
        return
    map_snapshot["orders"] = recorded_orders
    os.makedirs("maps", exist_ok=True)
    grid = map_snapshot.get("grid", {})
    w, h = grid.get("width", "?"), grid.get("height", "?")
    n_bots = map_snapshot.get("num_bots", "?")
    date_str = datetime.now().strftime("%Y-%m-%d")
    map_path = f"maps/{date_str}_{w}x{h}_{n_bots}bot.json"
    # Merge orders from previous runs to accumulate the full order list
    if os.path.exists(map_path):
        try:
            with open(map_path) as f:
                existing = json.load(f)
            existing_orders = existing.get("orders", [])
            # Check if order sequences match (same game seed)
            same_seed = _orders_same_seed(existing_orders, recorded_orders)
            if same_seed:
                existing_ids = {o["id"] for o in existing_orders}
                new_count = 0
                for order in recorded_orders:
                    if order["id"] not in existing_ids:
                        existing_orders.append(order)
                        existing_ids.add(order["id"])
                        new_count += 1
                existing_orders.sort(key=lambda o: int(o["id"].split("_")[1]))
                map_snapshot["orders"] = existing_orders
                print(f"  Map merged: {new_count} new orders added (total: {len(existing_orders)})")
            else:
                # Different game seed — replace if we have more orders
                if len(recorded_orders) >= len(existing_orders):
                    map_snapshot["orders"] = recorded_orders
                    print(f"  Map replaced: new seed ({len(recorded_orders)} orders, was {len(existing_orders)})")
                else:
                    map_snapshot["orders"] = existing_orders
                    print(f"  Map kept: existing seed has more orders ({len(existing_orders)} vs {len(recorded_orders)})")
        except (json.JSONDecodeError, KeyError):
            pass
    with open(map_path, "w") as f:
        json.dump(map_snapshot, f, indent=2)
    print(f"  Map saved: {map_path} ({len(map_snapshot['orders'])} orders)")


def build_game_meta(data: dict[str, Any], timestamp: str) -> dict[str, Any]:
    grid = data["grid"]
    return {
        "timestamp": timestamp,
        "grid": {
            "width": grid["width"],
            "height": grid["height"],
            "walls": len(grid["walls"]),
            "wall_positions": grid["walls"],
        },
        "bots": len(data["bots"]),
        "items_on_map": len(data["items"]),
        "item_types": sorted({it["type"] for it in data["items"]}),
        "item_positions": [
            {"type": it["type"], "position": it["position"]} for it in data["items"]
        ],
        "drop_off": data["drop_off"],
        "drop_off_zones": data.get("drop_off_zones", [data["drop_off"]]),
        "max_rounds": data["max_rounds"],
        "total_orders": data.get("total_orders", "?"),
        "spawn": data["bots"][0]["position"],
    }


def log_round(data: dict[str, Any], actions: list[dict[str, Any]], log_rows: list[dict]) -> None:
    active_o = next(
        (o for o in data["orders"] if o.get("status") == "active" and not o["complete"]),
        None,
    )
    preview_o = next((o for o in data["orders"] if o.get("status") == "preview"), None)
    for a in actions:
        b = next(bt for bt in data["bots"] if bt["id"] == a["bot"])
        log_rows.append(
            {
                "round": data["round"],
                "score": data["score"],
                "order_idx": data.get("active_order_index", ""),
                "bot_id": a["bot"],
                "bot_pos": f"{b['position'][0]},{b['position'][1]}",
                "inventory": ";".join(b["inventory"]) if b["inventory"] else "",
                "action": a["action"],
                "item_id": a.get("item_id", ""),
                "active_needed": (
                    ";".join(f"{k}:{v}" for k, v in get_needed_items(active_o).items())
                    if active_o
                    else ""
                ),
                "active_delivered": (";".join(active_o["items_delivered"]) if active_o else ""),
                "preview_needed": (
                    ";".join(f"{k}:{v}" for k, v in get_needed_items(preview_o).items())
                    if preview_o
                    else ""
                ),
            }
        )


_LOG_FIELDNAMES = [
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


def log_game_over(
    data: dict[str, Any],
    game_meta: dict[str, Any],
    log_rows: list[dict],
    log_path: str,
    meta_path: str,
    blacklisted_items: set[str] | None = None,
) -> None:
    print("\nGame Over!")
    print(f"  Score: {data['score']}")
    print(f"  Rounds: {data['rounds_used']}")
    print(f"  Items delivered: {data['items_delivered']}")
    print(f"  Orders completed: {data['orders_completed']}")

    game_meta["result"] = {
        "score": data["score"],
        "rounds_used": data["rounds_used"],
        "items_delivered": data["items_delivered"],
        "orders_completed": data["orders_completed"],
    }
    if blacklisted_items:
        game_meta["blacklisted_items"] = list(blacklisted_items)

    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_LOG_FIELDNAMES)
        writer.writeheader()
        writer.writerows(log_rows)
    with open(meta_path, "w") as f:
        json.dump(game_meta, f, indent=2)
    print(f"  Log: {log_path}")
    print(f"  Meta: {meta_path}")


def load_matching_map_orders(data: dict[str, Any]) -> list[dict[str, Any]] | None:
    """Match round-0 game state against recorded maps and return orders.

    Matches by grid dimensions, item count, and first-order items (if visible).
    Returns the recorded order list if a match is found, None otherwise.
    """
    grid = data["grid"]
    w, h = grid["width"], grid["height"]
    num_bots = len(data["bots"])
    game_orders = data.get("orders", [])

    # Build a fingerprint from item positions + types for exact matching
    game_items = sorted((it["position"][0], it["position"][1], it["type"]) for it in data["items"])

    map_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "maps")
    if not os.path.isdir(map_dir):
        return None

    pattern = os.path.join(map_dir, f"*_{w}x{h}_{num_bots}bot.json")
    best_match: list[dict[str, Any]] | None = None
    best_count = 0

    for path in sorted(glob.glob(pattern)):
        try:
            with open(path) as f:
                recorded = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue

        # Verify item layout matches (same map)
        rec_items = sorted(
            (it["position"][0], it["position"][1], it["type"]) for it in recorded.get("items", [])
        )
        if rec_items != game_items:
            continue

        orders = recorded.get("orders", [])

        # Verify order sequence matches by checking first visible order
        if orders and game_orders:
            rec_first = sorted(orders[0].get("items_required", []))
            live_first = sorted(game_orders[0].get("items_required", []))
            if rec_first != live_first:
                continue

        if len(orders) > best_count:
            best_count = len(orders)
            best_match = orders

    if best_match:
        print(f"  Oracle: loaded {len(best_match)} recorded orders from maps/")
    else:
        print("  Oracle: no matching order sequence found in recorded maps")
    return best_match
