import asyncio
import csv
import json
import os
import sys
from collections import deque
from datetime import datetime
from itertools import permutations

import websockets

WS_URL = sys.argv[1] if len(sys.argv) > 1 else input("Enter WebSocket URL: ")

# --- Global cached state (computed once on round 0, map is static) ---
_blocked_static = None  # walls + item shelves + out-of-bounds
_dist_cache = {}        # {source_pos: {dest_pos: distance}} — lazy BFS cache
_adj_cache = {}         # {item_pos: [adjacent walkable positions]}


def init_static(state):
    """Compute static blocked set and caches on round 0."""
    global _blocked_static, _dist_cache, _adj_cache
    _dist_cache = {}
    _adj_cache = {}

    walls = {tuple(w) for w in state["grid"]["walls"]}
    width, height = state["grid"]["width"], state["grid"]["height"]
    item_positions = {tuple(it["position"]) for it in state["items"]}

    blocked = set(walls)
    for x in range(-1, width + 1):
        blocked.add((x, -1))
        blocked.add((x, height))
    for y in range(-1, height + 1):
        blocked.add((-1, y))
        blocked.add((width, y))
    blocked |= item_positions
    _blocked_static = blocked

    # Precompute adjacent walkable cells for every item shelf
    for it in state["items"]:
        ipos = tuple(it["position"])
        adj = []
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            pos = (ipos[0] + dx, ipos[1] + dy)
            if pos not in _blocked_static:
                adj.append(pos)
        _adj_cache[ipos] = adj


def bfs_all(source, blocked):
    """BFS from source to ALL reachable cells. Returns {pos: distance}."""
    distances = {source: 0}
    queue = deque([source])
    while queue:
        pos = queue.popleft()
        d = distances[pos]
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            npos = (pos[0] + dx, pos[1] + dy)
            if npos not in distances and npos not in blocked:
                distances[npos] = d + 1
                queue.append(npos)
    return distances


def get_distances_from(source, blocked):
    """Get cached distance map from source."""
    if blocked is _blocked_static:
        if source not in _dist_cache:
            _dist_cache[source] = bfs_all(source, blocked)
        return _dist_cache[source]
    return bfs_all(source, blocked)


def dist_static(a, b):
    """O(1) lookup for static distance between two walkable cells."""
    if a == b:
        return 0
    dmap = get_distances_from(a, _blocked_static)
    return dmap.get(b, float("inf"))


def bfs(start, goal, blocked):
    """BFS pathfinding. Returns next position to move to, or None if no path."""
    if start == goal:
        return None
    queue = deque([(goal, [])])
    visited = {goal}
    while queue:
        pos, path = queue.popleft()
        for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
            nx, ny = pos[0] + dx, pos[1] + dy
            npos = (nx, ny)
            if npos in visited or npos in blocked:
                continue
            visited.add(npos)
            if npos == start:
                return pos
            queue.append((npos, path + [pos]))
    return None


def direction_to(sx, sy, tx, ty):
    """Convert a single step into a move action string."""
    dx, dy = tx - sx, ty - sy
    if dx == 1:
        return "move_right"
    if dx == -1:
        return "move_left"
    if dy == 1:
        return "move_down"
    if dy == -1:
        return "move_up"
    return "wait"


def get_needed_items(order):
    """Get dict of {item_type: count_still_needed} for an order."""
    needed = {}
    for item in order["items_required"]:
        needed[item] = needed.get(item, 0) + 1
    for item in order["items_delivered"]:
        needed[item] = needed.get(item, 0) - 1
    return {k: v for k, v in needed.items() if v > 0}


def find_adjacent_positions(ix, iy, blocked_static):
    """Find walkable positions adjacent to an item shelf (cached)."""
    ipos = (ix, iy)
    if ipos in _adj_cache:
        return _adj_cache[ipos]
    adj = []
    for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]:
        pos = (ix + dx, iy + dy)
        if pos not in blocked_static:
            adj.append(pos)
    return adj


def find_best_item_target(pos, item, blocked_static):
    """Find the best adjacent cell to reach an item, using cached static distances."""
    ipos = tuple(item["position"])
    adj_cells = _adj_cache.get(ipos, find_adjacent_positions(ipos[0], ipos[1], blocked_static))
    if not adj_cells:
        return None, float("inf")
    best_cell = None
    best_d = float("inf")
    for ac in adj_cells:
        d = dist_static(pos, ac)
        if d < best_d:
            best_d = d
            best_cell = ac
    return best_cell, best_d


def tsp_route(bot_pos, item_targets, drop_off):
    """Find optimal pickup order for items using brute-force TSP.
    item_targets: list of (item, best_adjacent_cell) tuples.
    Returns reordered list of (item, cell) in optimal pickup sequence.
    """
    if len(item_targets) <= 1:
        return item_targets

    best_order = None
    best_cost = float("inf")
    for perm in permutations(range(len(item_targets))):
        cost = 0
        prev = bot_pos
        for idx in perm:
            _, cell = item_targets[idx]
            cost += dist_static(prev, cell)
            if cost >= best_cost:
                break
            prev = cell
        else:
            cost += dist_static(prev, drop_off)
            if cost < best_cost:
                best_cost = cost
                best_order = perm

    if best_order is None:
        return item_targets
    return [item_targets[i] for i in best_order]


def decide_actions(state):
    global _blocked_static

    bots = state["bots"]
    items = state["items"]
    orders = state["orders"]
    drop_off = tuple(state["drop_off"])

    # Initialize static data on round 0
    if _blocked_static is None:
        init_static(state)

    blocked_static = _blocked_static
    rounds_remaining = state["max_rounds"] - state["round"]

    # Active and preview orders
    active = next((o for o in orders if o.get("status") == "active" and not o["complete"]), None)
    preview = next((o for o in orders if o.get("status") == "preview"), None)

    if not active:
        return [{"bot": b["id"], "action": "wait"} for b in bots]

    active_needed = get_needed_items(active)
    preview_needed = get_needed_items(preview) if preview else {}

    # Build item index: which items on the map match needed types
    items_by_type = {}
    for it in items:
        items_by_type.setdefault(it["type"], []).append(it)

    # Track what's already being carried by all bots toward active order
    carried_for_active = {}
    carried_for_preview = {}
    for bot in bots:
        for inv_item in bot["inventory"]:
            if inv_item in active_needed:
                carried_for_active[inv_item] = carried_for_active.get(inv_item, 0) + 1
            elif inv_item in preview_needed:
                carried_for_preview[inv_item] = carried_for_preview.get(inv_item, 0) + 1

    # Net needed from shelves (accounting for what's already carried)
    net_active_needed = {}
    for item_type, count in active_needed.items():
        still = count - carried_for_active.get(item_type, 0)
        if still > 0:
            net_active_needed[item_type] = still

    # Items still on shelves needed for active order
    active_items_on_shelves = sum(net_active_needed.values())

    net_preview_needed = {}
    for item_type, count in preview_needed.items():
        still = count - carried_for_preview.get(item_type, 0)
        if still > 0:
            net_preview_needed[item_type] = still

    # Assignment: track which items are claimed by bots this round
    claimed_items = set()

    # Count idle bots (not delivering) for fair item distribution
    idle_bots = 0
    for bot in bots:
        has_ai = any(active_needed.get(it, 0) > 0 for it in bot["inventory"])
        if has_ai and (len(bot["inventory"]) >= 3 or active_items_on_shelves == 0):
            continue
        if tuple(bot["position"]) == drop_off and has_ai:
            continue
        idle_bots += 1
    # Max items per bot = fair share (at least 1)
    total_needed = active_items_on_shelves
    max_claim_per_bot = max(1, (total_needed + idle_bots - 1) // idle_bots) if idle_bots > 0 else 3

    actions = []
    # Track predicted positions for anti-collision: where each bot will be after this round
    predicted_positions = {}  # bot_id -> predicted (x, y)

    def emit(bot_id, bx, by, action_dict):
        """Append action and record predicted position."""
        actions.append(action_dict)
        predicted_positions[bot_id] = _predict_pos(bx, by, action_dict["action"])

    for bot in bots:
        bx, by = bot["position"]
        pos = (bx, by)
        inventory = bot["inventory"]
        bot_id = bot["id"]

        # Use predicted positions for already-processed bots (they move first),
        # and current positions for not-yet-processed bots
        other_bot_positions = set()
        for b in bots:
            if b["id"] == bot_id:
                continue
            if b["id"] in predicted_positions:
                other_bot_positions.add(predicted_positions[b["id"]])
            else:
                other_bot_positions.add(tuple(b["position"]))
        blocked = blocked_static | other_bot_positions

        # Check if we have items useful for active order
        has_active_items = any(active_needed.get(it, 0) > 0 for it in inventory)

        # 1. If at drop-off and have useful items, deliver
        if pos == drop_off and has_active_items:
            emit(bot_id, bx, by, {"bot": bot_id, "action": "drop_off"})
            continue

        # 2. Rush to deliver if all active items are picked up (completes order = +5 bonus)
        #    BUT still grab adjacent preview items first (1 round cost saves ~20 later)
        if has_active_items and active_items_on_shelves == 0:
            # Check for adjacent preview items first — nearly free
            if preview and len(inventory) < 3:
                for item_type, count in net_preview_needed.items():
                    if count <= 0:
                        continue
                    for it in items_by_type.get(item_type, []):
                        if it["id"] in claimed_items:
                            continue
                        ix, iy = it["position"]
                        if abs(bx - ix) + abs(by - iy) == 1:
                            claimed_items.add(it["id"])
                            net_preview_needed[it["type"]] = net_preview_needed.get(it["type"], 0) - 1
                            emit(bot_id, bx, by, {"bot": bot_id, "action": "pick_up", "item_id": it["id"]})
                            break
                    else:
                        continue
                    break
                if len(actions) > 0 and actions[-1]["bot"] == bot_id:
                    continue

            next_pos = bfs(pos, drop_off, blocked)
            if next_pos:
                emit(bot_id, bx, by, {"bot": bot_id, "action": direction_to(bx, by, next_pos[0], next_pos[1])})
            else:
                emit(bot_id, bx, by, {"bot": bot_id, "action": "wait"})
            continue

        # 3. Opportunistic preview pickup: grab adjacent preview items only if
        #    we have spare slots beyond what active items need
        spare_slots = (3 - len(inventory)) - active_items_on_shelves
        if preview and spare_slots > 0:
            for item_type, count in net_preview_needed.items():
                if count <= 0:
                    continue
                for it in items_by_type.get(item_type, []):
                    if it["id"] in claimed_items:
                        continue
                    ix, iy = it["position"]
                    if abs(bx - ix) + abs(by - iy) == 1:
                        claimed_items.add(it["id"])
                        net_preview_needed[it["type"]] = net_preview_needed.get(it["type"], 0) - 1
                        emit(bot_id, bx, by, {"bot": bot_id, "action": "pick_up", "item_id": it["id"]})
                        picked_up_preview = True
                        break
                else:
                    continue
                break
            else:
                picked_up_preview = False

            if picked_up_preview:
                continue

        # 3. If inventory full, go deliver
        if has_active_items and len(inventory) >= 3:
            next_pos = bfs(pos, drop_off, blocked)
            if next_pos:
                emit(bot_id, bx, by, {"bot": bot_id, "action": direction_to(bx, by, next_pos[0], next_pos[1])})
            else:
                emit(bot_id, bx, by, {"bot": bot_id, "action": "wait"})
            continue

        # 4. Try to pick up needed items for active order — use TSP for optimal ordering
        candidates = []
        picked_up = False
        for item_type, count in net_active_needed.items():
            if count <= 0:
                continue
            for it in items_by_type.get(item_type, []):
                if it["id"] in claimed_items:
                    continue
                ix, iy = it["position"]
                # Check if adjacent (can pick up immediately)
                if abs(bx - ix) + abs(by - iy) == 1 and len(inventory) < 3:
                    claimed_items.add(it["id"])
                    net_active_needed[it["type"]] = net_active_needed.get(it["type"], 0) - 1
                    emit(bot_id, bx, by, {"bot": bot_id, "action": "pick_up", "item_id": it["id"]})
                    picked_up = True
                    break
                cell, d = find_best_item_target(pos, it, blocked_static)
                if cell and d < float("inf"):
                    # End-game: skip items we can't pick up and deliver in time
                    round_trip = d + 1 + dist_static(cell, drop_off)
                    if round_trip < rounds_remaining:
                        candidates.append((it, cell, d))
            if picked_up:
                break

        if picked_up:
            continue

        if candidates and len(inventory) < 3:
            slots = min(3 - len(inventory), max_claim_per_bot)
            candidates.sort(key=lambda c: c[2])
            selected = []
            selected_types = {}
            for it, cell, d in candidates:
                t = it["type"]
                needed_count = net_active_needed.get(t, 0) - selected_types.get(t, 0)
                if needed_count > 0 and len(selected) < slots:
                    selected.append((it, cell))
                    selected_types[t] = selected_types.get(t, 0) + 1

            if selected:
                route = tsp_route(pos, selected, drop_off)
                first_item, first_cell = route[0]
                for it, _ in route:
                    claimed_items.add(it["id"])
                    net_active_needed[it["type"]] = net_active_needed.get(it["type"], 0) - 1

                next_pos = bfs(pos, first_cell, blocked)
                if next_pos:
                    emit(bot_id, bx, by, {"bot": bot_id, "action": direction_to(bx, by, next_pos[0], next_pos[1])})
                    continue

        # 5. If we have active items to deliver, consider preview detour first
        if has_active_items:
            # If empty slots, check if a preview item is worth a small detour
            if preview and len(inventory) < 3:
                direct = dist_static(pos, drop_off)
                best_detour_item = None
                best_detour_cell = None
                best_detour_cost = float("inf")
                for item_type, count in net_preview_needed.items():
                    if count <= 0:
                        continue
                    for it in items_by_type.get(item_type, []):
                        if it["id"] in claimed_items:
                            continue
                        cell, d = find_best_item_target(pos, it, blocked_static)
                        if cell:
                            detour = d + dist_static(cell, drop_off) - direct
                            if detour < best_detour_cost:
                                best_detour_cost = detour
                                best_detour_item = it
                                best_detour_cell = cell

                # Detour worth it if cost is small relative to savings
                # A preview item picked up now saves ~2*dist(dropoff, item) later
                if best_detour_item and best_detour_cost <= 6:
                    claimed_items.add(best_detour_item["id"])
                    net_preview_needed[best_detour_item["type"]] = net_preview_needed.get(best_detour_item["type"], 0) - 1
                    next_pos = bfs(pos, best_detour_cell, blocked)
                    if next_pos:
                        emit(bot_id, bx, by, {"bot": bot_id, "action": direction_to(bx, by, next_pos[0], next_pos[1])})
                        continue

            next_pos = bfs(pos, drop_off, blocked)
            if next_pos:
                emit(bot_id, bx, by, {"bot": bot_id, "action": direction_to(bx, by, next_pos[0], next_pos[1])})
                continue

        # 6. Try preview order items (pre-pick)
        if preview and len(inventory) < 3:
            best_preview = None
            best_pdist = float("inf")
            for item_type, count in net_preview_needed.items():
                if count <= 0:
                    continue
                for it in items_by_type.get(item_type, []):
                    if it["id"] in claimed_items:
                        continue
                    ix, iy = it["position"]
                    if abs(bx - ix) + abs(by - iy) == 1:
                        best_preview = it
                        best_pdist = 0
                        break
                    _, d = find_best_item_target(pos, it, blocked_static)
                    if d < best_pdist:
                        best_pdist = d
                        best_preview = it
                if best_pdist == 0:
                    break

            if best_preview and best_pdist == 0:
                claimed_items.add(best_preview["id"])
                net_preview_needed[best_preview["type"]] = net_preview_needed.get(best_preview["type"], 0) - 1
                emit(bot_id, bx, by, {"bot": bot_id, "action": "pick_up", "item_id": best_preview["id"]})
                continue

            if best_preview:
                claimed_items.add(best_preview["id"])
                net_preview_needed[best_preview["type"]] = net_preview_needed.get(best_preview["type"], 0) - 1
                target, _ = find_best_item_target(pos, best_preview, blocked_static)
                if target:
                    next_pos = bfs(pos, target, blocked)
                    if next_pos:
                        emit(bot_id, bx, by, {"bot": bot_id, "action": direction_to(bx, by, next_pos[0], next_pos[1])})
                        continue

        emit(bot_id, bx, by, {"bot": bot_id, "action": "wait"})

    return actions


def _predict_pos(bx, by, action):
    """Predict bot position after an action."""
    if action == "move_up":
        return (bx, by - 1)
    elif action == "move_down":
        return (bx, by + 1)
    elif action == "move_left":
        return (bx - 1, by)
    elif action == "move_right":
        return (bx + 1, by)
    return (bx, by)


async def play():
    global _blocked_static, _dist_cache, _adj_cache
    _blocked_static = None
    _dist_cache = {}
    _adj_cache = {}

    os.makedirs("logs", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"logs/game_{timestamp}.csv"
    log_rows = []

    print(f"Connecting to {WS_URL[:60]}...")
    async with websockets.connect(WS_URL) as ws:
        print("Connected!")
        async for message in ws:
            data = json.loads(message)

            if data["type"] == "game_over":
                print(f"\nGame Over!")
                print(f"  Score: {data['score']}")
                print(f"  Rounds: {data['rounds_used']}")
                print(f"  Items delivered: {data['items_delivered']}")
                print(f"  Orders completed: {data['orders_completed']}")

                # Write log file
                with open(log_path, "w", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=[
                        "round", "score", "order_idx", "bot_id", "bot_pos",
                        "inventory", "action", "item_id", "active_needed",
                        "active_delivered", "preview_needed",
                    ])
                    writer.writeheader()
                    writer.writerows(log_rows)
                print(f"  Log: {log_path}")
                break

            if data["type"] == "game_state":
                round_num = data["round"]
                if round_num % 25 == 0 or round_num == 0:
                    print(f"Round {round_num}/{data['max_rounds']} | Score: {data['score']} | "
                          f"Order: {data.get('active_order_index', '?')} | "
                          f"Bots: {len(data['bots'])}")

                actions = decide_actions(data)

                # Log each bot's action
                active_o = next((o for o in data["orders"] if o.get("status") == "active" and not o["complete"]), None)
                preview_o = next((o for o in data["orders"] if o.get("status") == "preview"), None)
                for a in actions:
                    b = next(bt for bt in data["bots"] if bt["id"] == a["bot"])
                    log_rows.append({
                        "round": round_num,
                        "score": data["score"],
                        "order_idx": data.get("active_order_index", ""),
                        "bot_id": a["bot"],
                        "bot_pos": f"{b['position'][0]},{b['position'][1]}",
                        "inventory": ";".join(b["inventory"]) if b["inventory"] else "",
                        "action": a["action"],
                        "item_id": a.get("item_id", ""),
                        "active_needed": ";".join(f"{k}:{v}" for k, v in get_needed_items(active_o).items()) if active_o else "",
                        "active_delivered": ";".join(active_o["items_delivered"]) if active_o else "",
                        "preview_needed": ";".join(f"{k}:{v}" for k, v in get_needed_items(preview_o).items()) if preview_o else "",
                    })

                await ws.send(json.dumps({"actions": actions}))


if __name__ == "__main__":
    asyncio.run(play())
