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
import time
from datetime import datetime

# Re-export everything tests and simulator access via `bot.xxx`
from grocery_bot.pathfinding import (  # noqa: F401
    DIRECTIONS,
    bfs,
    bfs_all,
    direction_to,
    find_adjacent_positions,
    _predict_pos,
)
from grocery_bot.orders import get_needed_items  # noqa: F401
from grocery_bot.constants import MAX_INVENTORY  # noqa: F401
from grocery_bot.game_state import GameState  # noqa: F401
from grocery_bot.planner.round_planner import RoundPlanner  # noqa: F401


# ---------------------------------------------------------------------------
# Module-level singleton and backward-compatible API
# ---------------------------------------------------------------------------

_gs = GameState()


def reset_state():
    _gs.reset()


def init_static(state):
    _gs.init_static(state)


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
    if _gs.blocked_static is None:
        _gs.init_static(state)

    planner = RoundPlanner(_gs, state, full_state=state)
    actions = planner.plan()
    return _validate_actions(actions, state)


def _validate_actions(actions, state):
    """Final safety net: replace illegal actions with wait.

    Catches edge cases the planner missed — critical for the live server
    where illegal moves may incur 10-second penalties.
    """
    blocked = _gs.blocked_static
    if blocked is None:
        return actions

    drop_off = tuple(state["drop_off"])
    bot_positions = {b["id"]: tuple(b["position"]) for b in state["bots"]}
    occupied_cells = set(bot_positions.values())
    bot_inv_len = {b["id"]: len(b["inventory"]) for b in state["bots"]}
    items_by_id = {it["id"]: it for it in state["items"]}

    move_deltas = {
        "move_up": (0, -1), "move_down": (0, 1),
        "move_left": (-1, 0), "move_right": (1, 0),
    }

    # Compute intended destinations for all bots
    actions_by_bot = {a["bot"]: a for a in actions}
    destinations = {}
    for bid, a in actions_by_bot.items():
        pos = bot_positions[bid]
        act = a["action"]
        if act in move_deltas:
            dx, dy = move_deltas[act]
            destinations[bid] = (pos[0] + dx, pos[1] + dy)
        else:
            destinations[bid] = pos

    validated = []
    claimed_cells = set()

    for a in actions:
        bid = a["bot"]
        pos = bot_positions[bid]
        act = a["action"]
        dest = destinations[bid]
        valid = True

        if act in move_deltas:
            # Static obstacles (walls, shelves, boundaries)
            if dest in blocked:
                valid = False

            # Live/simulator movement resolves against current occupancy:
            # entering a cell another bot currently occupies is illegal,
            # even if that bot also intends to move away this round.
            if valid and dest in occupied_cells:
                valid = False

            # Swap collision (A→B and B→A)
            if valid:
                for other_bid in bot_positions:
                    if other_bid == bid:
                        continue
                    if (dest == bot_positions[other_bid]
                            and destinations.get(other_bid) == pos):
                        valid = False
                        break

            # Two of our own bots targeting the same cell
            if valid and dest in claimed_cells:
                valid = False

        elif act == "pick_up":
            item_id = a.get("item_id")
            if not item_id or bot_inv_len.get(bid, 0) >= MAX_INVENTORY:
                valid = False
            else:
                item = items_by_id.get(item_id)
                if not item:
                    valid = False
                else:
                    ix, iy = item["position"]
                    if abs(pos[0] - ix) + abs(pos[1] - iy) != 1:
                        valid = False

        elif act == "drop_off":
            if pos != drop_off or bot_inv_len.get(bid, 0) == 0:
                valid = False

        if valid:
            validated.append(a)
            claimed_cells.add(dest)
        else:
            validated.append({"bot": bid, "action": "wait"})
            claimed_cells.add(pos)
            destinations[bid] = pos  # update so subsequent checks see corrected dest

    return validated


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

    # Map recording state
    map_snapshot = {}
    recorded_orders = []
    seen_order_ids = set()
    msg_count = 0

    import websockets

    # Debug log — deferred writes (no flush per line to avoid blocking I/O)
    debug_path = f"logs/debug_{timestamp}.log"
    debug_lines = []

    def dbg(line):
        debug_lines.append(line)

    # Desync detection: track expected positions and inventories
    expected_positions = {}  # bot_id -> (x, y)
    expected_inventories = {}  # bot_id -> list[str]
    last_actions_sent = {}  # bot_id -> action_dict (what we ACTUALLY sent)
    desync_count = 0
    last_round_seen = -1
    prev_action_json = ""  # exact JSON we sent last round

    print(f"Connecting to {ws_url[:60]}...")
    async with websockets.connect(ws_url) as ws:
        print("Connected!")
        prev_send_time = None
        wall_set = None  # server's wall set for validation
        shelf_set = None  # item positions for validation
        drained_count = 0  # total stale messages drained
        while True:
            pre_recv = time.perf_counter()
            message = await ws.recv()
            recv_time = time.perf_counter()
            recv_wait_ms = (recv_time - pre_recv) * 1000
            gap_ms = (recv_time - prev_send_time) * 1000 if prev_send_time else 0
            msg_count += 1

            # Drain any buffered messages — always process the LATEST state.
            # After a network stall, the server may have queued multiple states.
            # Responding to stale states creates a permanent 1-round offset.
            stale_this_round = 0
            while True:
                try:
                    newer = await asyncio.wait_for(ws.recv(), timeout=0.002)
                    stale_this_round += 1
                    drained_count += 1
                    msg_count += 1
                    # If we drained a game_over, stop draining and use it
                    peek = json.loads(newer)
                    if peek.get("type") == "game_over":
                        message = newer
                        break
                    message = newer
                except (asyncio.TimeoutError, TimeoutError):
                    break
            if stale_this_round > 0:
                recv_time = time.perf_counter()
                dbg(f"DRAINED {stale_this_round} stale messages (total drained: {drained_count})")

            msg_len = len(message)
            data = json.loads(message)
            msg_type = data.get("type", "unknown")

            if msg_type == "game_over":
                dbg(f"GAME_OVER msg#{msg_count} len={msg_len}")
                _log_game_over(data, game_meta, log_rows, log_path, meta_path)
                _save_recorded_map(map_snapshot, recorded_orders, timestamp)
                break

            if msg_type != "game_state":
                dbg(f"NON-STATE msg#{msg_count} type={msg_type} len={msg_len}: {json.dumps(data)[:300]}")
                continue

            round_num = data["round"]

            # On first round, capture wall set and item positions for validation
            if round_num == 0:
                wall_set = set(tuple(w) for w in data["grid"]["walls"])
                shelf_set = set((it["position"][0], it["position"][1]) for it in data["items"])
                dbg(f"R0 INIT walls={len(wall_set)} shelves={len(shelf_set)} "
                    f"grid={data['grid']['width']}x{data['grid']['height']} "
                    f"drop_off={data['drop_off']} spawn={data['bots'][0]['position']}")

            # Detect skipped rounds
            if last_round_seen >= 0 and round_num > last_round_seen + 1:
                dbg(f"R{round_num} ROUND_SKIP: last_seen=R{last_round_seen}, jumped to R{round_num}")
            if last_round_seen >= 0 and round_num <= last_round_seen:
                dbg(f"R{round_num} ROUND_REPEAT: last_seen=R{last_round_seen}, got R{round_num} again!")
            last_round_seen = round_num

            # === DESYNC DETECTION ===
            desync_this_round = False
            desync_details = []
            for bot in data["bots"]:
                bid = bot["id"]
                actual_pos = tuple(bot["position"])
                actual_inv = list(bot["inventory"])
                exp_pos = expected_positions.get(bid)
                exp_inv = expected_inventories.get(bid)
                last_act = last_actions_sent.get(bid, {})

                # Position desync
                if exp_pos and actual_pos != exp_pos:
                    desync_this_round = True
                    desync_count += 1
                    # Figure out what move WOULD produce actual position
                    if exp_pos:
                        # Try to figure out which action produced this position
                        act_name = last_act.get("action", "?")
                        desync_details.append(
                            f"bot{bid}: pos expected={exp_pos} actual={actual_pos} "
                            f"(sent {act_name}, desync#{desync_count})"
                        )

                # Inventory desync (pick_up didn't apply)
                if exp_inv is not None and actual_inv != exp_inv:
                    act_name = last_act.get("action", "?")
                    desync_details.append(
                        f"bot{bid}: inv expected={exp_inv} actual={actual_inv} "
                        f"(sent {act_name})"
                    )

            for d in desync_details:
                dbg(f"R{round_num} DESYNC {d}")

            # Validate: check if our INTENDED action was legal on the server's map
            if wall_set and last_actions_sent:
                for bid, act in last_actions_sent.items():
                    action = act.get("action", "")
                    if action.startswith("move_"):
                        bot_data = next((b for b in data["bots"] if b["id"] == bid), None)
                        if bot_data and exp_pos:
                            target = expected_positions.get(bid)
                            if target and target in wall_set:
                                dbg(f"R{round_num} ILLEGAL_MOVE bot{bid}: {action} target {target} is a WALL!")
                            if target and target in shelf_set:
                                dbg(f"R{round_num} ILLEGAL_MOVE bot{bid}: {action} target {target} is a SHELF!")

            actions = decide_actions(data)
            # Actions are already validated by _validate_actions() inside
            # decide_actions() — illegal moves are replaced with "wait".

            # Build the exact JSON we'll send
            response_json = json.dumps({"actions": actions})

            await ws.send(response_json)
            send_time = time.perf_counter()

            # Update expected positions AND inventories
            _update_expected_positions(expected_positions, data, actions)
            _update_expected_inventories(expected_inventories, data, actions)
            last_actions_sent = {a["bot"]: a for a in actions}
            prev_action_json = response_json

            # --- Everything below is post-send bookkeeping ---
            total_ms = (send_time - recv_time) * 1000
            _log_round(data, actions, log_rows)

            action_summary = " | ".join(
                f"b{a['bot']}:{a['action']}" + (f"({a['item_id']})" if a.get('item_id') else "")
                for a in actions
            )
            bots_info = [(b["id"], b["position"], b["inventory"]) for b in data["bots"]]
            score = data.get("score", 0)
            desync_tag = " DESYNC!" if desync_this_round else ""
            dbg(f"R{round_num} msg#{msg_count} len={msg_len} wait={recv_wait_ms:.1f}ms gap={gap_ms:.1f}ms "
                f"send={total_ms:.1f}ms "
                f"bots={bots_info} score={score} -> [{action_summary}]{desync_tag}")
            if desync_this_round:
                dbg(f"R{round_num} SENT: {response_json[:300]}")
                dbg(f"R{round_num} PREV_SENT: {prev_action_json[:300]}")
            prev_send_time = send_time

            # Accumulate orders as they become visible
            for order in data.get("orders", []):
                oid = order["id"]
                if oid not in seen_order_ids:
                    seen_order_ids.add(oid)
                    recorded_orders.append({
                        "id": oid,
                        "items_required": list(order["items_required"]),
                    })

            if round_num == 0:
                game_meta.update(_build_game_meta(data, timestamp))
                map_snapshot = _build_map_snapshot(data, timestamp)
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
                    f"Bots: {len(data['bots'])} | "
                    f"Latency: {total_ms:.1f}ms"
                )

    if desync_count > 0:
        print(f"  Desyncs detected: {desync_count}")

    # Write debug log in one shot at end (no per-round I/O overhead)
    with open(debug_path, "w") as f:
        f.write("\n".join(debug_lines) + "\n")
    print(f"  Debug: {debug_path}")


def _update_expected_positions(expected, data, actions):
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


def _update_expected_inventories(expected, data, actions):
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


def _build_map_snapshot(data, timestamp):
    """Capture the round-0 game state for map recording."""
    return {
        "version": 1,
        "recorded_at": timestamp,
        "source": "live",
        "grid": data["grid"],
        "drop_off": data["drop_off"],
        "spawn": data["bots"][0]["position"],
        "num_bots": len(data["bots"]),
        "max_rounds": data["max_rounds"],
        "total_orders": data.get("total_orders"),
        "items": [
            {"id": it["id"], "type": it["type"], "position": it["position"]}
            for it in data["items"]
        ],
    }


def _save_recorded_map(map_snapshot, recorded_orders, timestamp):
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
            existing_ids = {o["id"] for o in existing_orders}
            new_count = 0
            for order in recorded_orders:
                if order["id"] not in existing_ids:
                    existing_orders.append(order)
                    existing_ids.add(order["id"])
                    new_count += 1
            # Sort by order id to maintain consistent ordering
            existing_orders.sort(key=lambda o: o["id"])
            map_snapshot["orders"] = existing_orders
            print(f"  Map merged: {new_count} new orders added (total: {len(existing_orders)})")
        except (json.JSONDecodeError, KeyError):
            pass
    with open(map_path, "w") as f:
        json.dump(map_snapshot, f, indent=2)
    print(f"  Map saved: {map_path} ({len(map_snapshot['orders'])} orders)")


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
            {"type": it["type"], "position": it["position"]} for it in data["items"]
        ],
        "drop_off": data["drop_off"],
        "max_rounds": data["max_rounds"],
        "total_orders": data.get("total_orders", "?"),
        "spawn": data["bots"][0]["position"],
    }


def _log_round(data, actions, log_rows):
    active_o = next(
        (
            o
            for o in data["orders"]
            if o.get("status") == "active" and not o["complete"]
        ),
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
                "active_delivered": (
                    ";".join(active_o["items_delivered"]) if active_o else ""
                ),
                "preview_needed": (
                    ";".join(f"{k}:{v}" for k, v in get_needed_items(preview_o).items())
                    if preview_o
                    else ""
                ),
            }
        )


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
        writer = csv.DictWriter(
            f,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerows(log_rows)
    with open(meta_path, "w") as f:
        json.dump(game_meta, f, indent=2)
    print(f"  Log: {log_path}")
    print(f"  Meta: {meta_path}")


if __name__ == "__main__":
    asyncio.run(play())
