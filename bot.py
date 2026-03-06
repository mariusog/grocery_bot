"""Grocery bot — thin orchestrator and backward-compatible API.

Classes live in their own modules:
  pathfinding.py  — pure BFS/movement functions
  game_state.py   — GameState (persistent caches)
  round_planner.py — RoundPlanner (per-round decisions)
"""

import asyncio
import csv
import json
import os
import sys
from datetime import datetime

# Re-export everything tests and simulator access via `bot.xxx`
from pathfinding import (  # noqa: F401
    DIRECTIONS,
    bfs,
    bfs_all,
    direction_to,
    find_adjacent_positions,
    get_needed_items,
    _predict_pos,
)
from game_state import GameState  # noqa: F401
from round_planner import RoundPlanner  # noqa: F401


# ---------------------------------------------------------------------------
# Module-level singleton and backward-compatible API
# ---------------------------------------------------------------------------

_gs = GameState()

# Module globals kept for test introspection
_blocked_static = None
_dist_cache = {}
_adj_cache = {}
_last_pickup = {}
_pickup_fail_count = {}
_blacklisted_items = set()


def _sync_globals_from_gs():
    global _blocked_static, _dist_cache, _adj_cache
    global _last_pickup, _pickup_fail_count, _blacklisted_items
    _blocked_static = _gs.blocked_static
    _dist_cache = _gs.dist_cache
    _adj_cache = _gs.adj_cache
    _last_pickup = _gs.last_pickup
    _pickup_fail_count = _gs.pickup_fail_count
    _blacklisted_items = _gs.blacklisted_items


def _sync_gs_from_globals():
    _gs.blocked_static = _blocked_static
    _gs.dist_cache = _dist_cache
    _gs.adj_cache = _adj_cache
    _gs.last_pickup = _last_pickup
    _gs.pickup_fail_count = _pickup_fail_count
    _gs.blacklisted_items = _blacklisted_items


def reset_state():
    _gs.reset()
    _sync_globals_from_gs()


def init_static(state):
    _gs.init_static(state)
    _sync_globals_from_gs()


def dist_static(a, b):
    return _gs.dist_static(a, b)


def get_distances_from(source, blocked):
    if blocked is _gs.blocked_static:
        return _gs.get_distances_from(source)
    return bfs_all(source, blocked)


def find_best_item_target(pos, item, _blocked_static=None):
    return _gs.find_best_item_target(pos, item)


def tsp_route(bot_pos, item_targets, drop_off):
    return _gs.tsp_route(bot_pos, item_targets, drop_off)


def tsp_cost(bot_pos, item_targets, drop_off):
    return _gs.tsp_cost(bot_pos, item_targets, drop_off)


def plan_multi_trip(bot_pos, all_candidates, drop_off, capacity=3):
    return _gs.plan_multi_trip(bot_pos, all_candidates, drop_off, capacity)


def decide_actions(state):
    _sync_gs_from_globals()

    if _gs.blocked_static is None:
        _gs.init_static(state)
        _sync_globals_from_gs()

    planner = RoundPlanner(_gs, state)
    planner._full_state = state  # for grid access in assignments
    result = planner.plan()

    _sync_globals_from_gs()
    return result


# ---------------------------------------------------------------------------
# WebSocket game loop
# ---------------------------------------------------------------------------

async def play():
    reset_state()

    ws_url = sys.argv[1] if len(sys.argv) > 1 else input("Enter WebSocket URL: ")

    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"logs/game_{timestamp}.csv"
    meta_path = f"logs/game_{timestamp}.json"
    log_rows = []
    game_meta = {}

    import websockets

    print(f"Connecting to {ws_url[:60]}...")
    async with websockets.connect(ws_url) as ws:
        print("Connected!")
        async for message in ws:
            data = json.loads(message)

            if data["type"] == "game_over":
                _log_game_over(data, game_meta, log_rows, log_path, meta_path)
                break

            if data["type"] == "game_state":
                round_num = data["round"]

                if round_num == 0:
                    game_meta.update(_build_game_meta(data, timestamp))
                    grid = data["grid"]
                    print(
                        f"Map: {grid['width']}x{grid['height']} | "
                        f"Bots: {len(data['bots'])} | "
                        f"Items: {len(data['items'])} "
                        f"({len(game_meta['item_types'])} types) | "
                        f"Rounds: {data['max_rounds']}"
                    )

                if round_num % 25 == 0 or round_num == 0:
                    print(
                        f"Round {round_num}/{data['max_rounds']} | "
                        f"Score: {data['score']} | "
                        f"Order: {data.get('active_order_index', '?')}"
                        f"/{data.get('total_orders', '?')} | "
                        f"Bots: {len(data['bots'])}"
                    )

                actions = decide_actions(data)
                _log_round(data, actions, log_rows)
                await ws.send(json.dumps({"actions": actions}))


def _build_game_meta(data, timestamp):
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
            {"type": it["type"], "position": it["position"]}
            for it in data["items"]
        ],
        "drop_off": data["drop_off"],
        "max_rounds": data["max_rounds"],
        "total_orders": data.get("total_orders", "?"),
        "spawn": data["bots"][0]["position"],
    }


def _log_round(data, actions, log_rows):
    active_o = next(
        (o for o in data["orders"]
         if o.get("status") == "active" and not o["complete"]),
        None,
    )
    preview_o = next(
        (o for o in data["orders"] if o.get("status") == "preview"), None
    )
    for a in actions:
        b = next(bt for bt in data["bots"] if bt["id"] == a["bot"])
        log_rows.append({
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
                if active_o else ""
            ),
            "active_delivered": (
                ";".join(active_o["items_delivered"]) if active_o else ""
            ),
            "preview_needed": (
                ";".join(f"{k}:{v}" for k, v in get_needed_items(preview_o).items())
                if preview_o else ""
            ),
        })


def _log_game_over(data, game_meta, log_rows, log_path, meta_path):
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
    if _gs.blacklisted_items:
        game_meta["blacklisted_items"] = list(_gs.blacklisted_items)

    with open(log_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "round", "score", "order_idx", "bot_id", "bot_pos",
            "inventory", "action", "item_id", "active_needed",
            "active_delivered", "preview_needed",
        ])
        writer.writeheader()
        writer.writerows(log_rows)
    with open(meta_path, "w") as f:
        json.dump(game_meta, f, indent=2)
    print(f"  Log: {log_path}")
    print(f"  Meta: {meta_path}")


if __name__ == "__main__":
    asyncio.run(play())
