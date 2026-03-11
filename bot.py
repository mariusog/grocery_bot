"""Grocery bot — thin orchestrator and backward-compatible API.

Classes live in their own modules:
  pathfinding.py  — pure BFS/movement functions
  game_state.py   — GameState (persistent caches)
  round_planner.py — RoundPlanner (per-round decisions)
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime

from grocery_bot.constants import MAX_INVENTORY
from grocery_bot.game_log import (
    build_game_meta,
    build_map_snapshot,
    log_game_over,
    log_round,
    save_recorded_map,
    update_expected_inventories,
    update_expected_positions,
)
from grocery_bot.game_state import GameState
from grocery_bot.orders import get_needed_items  # noqa: F401 — re-exported for tests

# Re-export everything tests and simulator access via `bot.xxx`
from grocery_bot.pathfinding import (  # noqa: F401
    DIRECTIONS,
    _predict_pos,
    bfs,
    bfs_all,
    direction_to,
    find_adjacent_positions,
)
from grocery_bot.planner.round_planner import RoundPlanner

# ---------------------------------------------------------------------------
# Module-level singleton and backward-compatible API
# ---------------------------------------------------------------------------

_gs = GameState()


def reset_state() -> None:
    _gs.reset()


def init_static(state: dict) -> None:
    _gs.init_static(state)


def dist_static(a: tuple, b: tuple) -> float:
    return _gs.dist_static(a, b)


def get_distances_from(source: tuple, blocked: set) -> dict:
    if blocked is _gs.blocked_static:
        return _gs.get_distances_from(source)
    return bfs_all(source, blocked)


def find_best_item_target(pos: tuple, item: dict, _blocked_static: object = None) -> tuple:
    return _gs.find_best_item_target(pos, item)


def tsp_route(bot_pos: tuple, item_targets: list, drop_off: tuple) -> list:
    return _gs.tsp_route(bot_pos, item_targets, drop_off)


def tsp_cost(bot_pos: tuple, item_targets: list, drop_off: tuple) -> float:
    return _gs.tsp_cost(bot_pos, item_targets, drop_off)


def plan_multi_trip(
    bot_pos: tuple, all_candidates: list, drop_off: tuple, capacity: int = 3
) -> list:
    return _gs.plan_multi_trip(bot_pos, all_candidates, drop_off, capacity)


def decide_actions(state: dict) -> list:
    if not _gs.blocked_static:
        _gs.init_static(state)

    # Load future orders when available (recorded maps / simulator)
    if "all_orders" in state and not _gs.future_orders:
        _gs.set_future_orders(state["all_orders"])
    _gs.update_demand(state.get("active_order_index", 0))

    planner = RoundPlanner(_gs, state, full_state=state)
    actions = planner.plan()
    return _validate_actions(actions, state)


def _validate_actions(actions: list, state: dict) -> list:
    """Final safety net: replace illegal actions with wait.

    Catches edge cases the planner missed — critical for the live server
    where illegal moves may incur 10-second penalties.
    """
    blocked = _gs.blocked_static
    if not blocked:
        return actions

    zones = state.get("drop_off_zones")
    drop_off_set = set(tuple(z) for z in zones) if zones else {tuple(state["drop_off"])}
    bot_positions = {b["id"]: tuple(b["position"]) for b in state["bots"]}
    occupied_cells = set(bot_positions.values())
    bot_inv_len = {b["id"]: len(b["inventory"]) for b in state["bots"]}
    items_by_id = {it["id"]: it for it in state["items"]}

    move_deltas = {
        "move_up": (0, -1),
        "move_down": (0, 1),
        "move_left": (-1, 0),
        "move_right": (1, 0),
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
                    if dest == bot_positions[other_bid] and destinations.get(other_bid) == pos:
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
            if pos not in drop_off_set or bot_inv_len.get(bid, 0) == 0:
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


async def play() -> None:
    reset_state()

    ws_url = sys.argv[1] if len(sys.argv) > 1 else input("Enter WebSocket URL: ")

    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"logs/game_{timestamp}.csv"
    meta_path = f"logs/game_{timestamp}.json"
    log_rows: list[dict] = []
    game_meta: dict = {}

    # Map recording state
    map_snapshot: dict = {}
    recorded_orders: list[dict] = []
    seen_order_ids = set()
    msg_count = 0

    import websockets

    # Debug log — deferred writes (no flush per line to avoid blocking I/O)
    debug_path = f"logs/debug_{timestamp}.log"
    debug_lines = []

    def dbg(line: str) -> None:
        debug_lines.append(line)

    # Desync detection: track expected positions and inventories
    expected_positions: dict[int, tuple[int, int]] = {}  # bot_id -> (x, y)
    expected_inventories: dict[int, list[str] | None] = {}  # bot_id -> list[str] or None
    last_actions_sent: dict[int, dict] = {}  # bot_id -> action_dict (what we ACTUALLY sent)
    desync_count = 0
    last_round_seen = -1
    prev_action_json = ""  # exact JSON we sent last round

    print(f"Connecting to {ws_url[:60]}...")
    async with websockets.connect(ws_url) as ws:
        print("Connected!")
        prev_send_time = None
        wall_set: set[tuple[int, int]] = set()  # server's wall set for validation
        shelf_set: set[tuple[int, int]] = set()  # item positions for validation
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
                except TimeoutError:
                    break
            if stale_this_round > 0:
                recv_time = time.perf_counter()
                dbg(f"DRAINED {stale_this_round} stale messages (total drained: {drained_count})")

            msg_len = len(message)
            data = json.loads(message)
            msg_type = data.get("type", "unknown")

            if msg_type == "game_over":
                dbg(f"GAME_OVER msg#{msg_count} len={msg_len}")
                game_meta["orders"] = recorded_orders
                log_game_over(data, game_meta, log_rows, log_path, meta_path, _gs.blacklisted_items)
                save_recorded_map(map_snapshot, recorded_orders, timestamp)
                break

            if msg_type != "game_state":
                dbg(
                    f"NON-STATE msg#{msg_count} type={msg_type} len={msg_len}: "
                    f"{json.dumps(data)[:300]}"
                )
                continue

            round_num = data["round"]

            # On first round, capture wall set and item positions for validation
            if round_num == 0:
                wall_set = set(tuple(w) for w in data["grid"]["walls"])
                shelf_set = set((it["position"][0], it["position"][1]) for it in data["items"])
                # Log ALL top-level keys to discover fields like drop_zones
                state_keys = sorted(k for k in data if k not in ("grid", "bots", "items", "orders"))
                dbg(
                    f"R0 INIT walls={len(wall_set)} shelves={len(shelf_set)} "
                    f"grid={data['grid']['width']}x{data['grid']['height']} "
                    f"drop_off={data['drop_off']} spawn={data['bots'][0]['position']}"
                )
                dbg(f"R0 ALL_KEYS: {list(data.keys())}")
                for k in state_keys:
                    dbg(f"R0 FIELD {k}={data[k]}")

            # Detect skipped rounds
            if last_round_seen >= 0 and round_num > last_round_seen + 1:
                dbg(
                    f"R{round_num} ROUND_SKIP: last_seen=R{last_round_seen}, jumped to R{round_num}"
                )
            if last_round_seen >= 0 and round_num <= last_round_seen:
                dbg(
                    f"R{round_num} ROUND_REPEAT: "
                    f"last_seen=R{last_round_seen}, got R{round_num} again!"
                )
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
                        f"bot{bid}: inv expected={exp_inv} actual={actual_inv} (sent {act_name})"
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
                                dbg(
                                    f"R{round_num} ILLEGAL_MOVE bot{bid}: "
                                    f"{action} target {target} is a WALL!"
                                )
                            if target and target in shelf_set:
                                dbg(
                                    f"R{round_num} ILLEGAL_MOVE bot{bid}: "
                                    f"{action} target {target} is a SHELF!"
                                )

            actions = decide_actions(data)
            # Actions are already validated by _validate_actions() inside
            # decide_actions() — illegal moves are replaced with "wait".

            # Build the exact JSON we'll send
            response_json = json.dumps({"actions": actions})

            await ws.send(response_json)
            send_time = time.perf_counter()

            # Update expected positions AND inventories
            update_expected_positions(expected_positions, data, actions)
            update_expected_inventories(expected_inventories, data, actions)
            last_actions_sent = {a["bot"]: a for a in actions}
            prev_action_json = response_json

            # --- Everything below is post-send bookkeeping ---
            total_ms = (send_time - recv_time) * 1000
            log_round(data, actions, log_rows)

            action_summary = " | ".join(
                f"b{a['bot']}:{a['action']}" + (f"({a['item_id']})" if a.get("item_id") else "")
                for a in actions
            )
            bots_info = [(b["id"], b["position"], b["inventory"]) for b in data["bots"]]
            score = data.get("score", 0)
            desync_tag = " DESYNC!" if desync_this_round else ""
            dbg(
                f"R{round_num} msg#{msg_count} len={msg_len} "
                f"wait={recv_wait_ms:.1f}ms gap={gap_ms:.1f}ms "
                f"send={total_ms:.1f}ms "
                f"bots={bots_info} score={score} -> [{action_summary}]{desync_tag}"
            )
            if desync_this_round:
                dbg(f"R{round_num} SENT: {response_json[:300]}")
                dbg(f"R{round_num} PREV_SENT: {prev_action_json[:300]}")
            prev_send_time = send_time

            # Accumulate orders as they become visible
            for order in data.get("orders", []):
                oid = order["id"]
                if oid not in seen_order_ids:
                    seen_order_ids.add(oid)
                    recorded_orders.append(
                        {
                            "id": oid,
                            "items_required": list(order["items_required"]),
                        }
                    )

            if round_num == 0:
                game_meta.update(build_game_meta(data, timestamp))
                map_snapshot = build_map_snapshot(data, timestamp)
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


if __name__ == "__main__":
    asyncio.run(play())
