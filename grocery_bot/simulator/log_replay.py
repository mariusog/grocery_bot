"""Log replay — verify live game scores by replaying actions through physics."""

import csv
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grocery_bot.simulator.game_simulator import GameSimulator


def parse_actions(csv_path: str) -> list[dict[str, Any]]:
    """Parse a live game CSV into per-round action lists.

    For pick_up actions, infers the item type from inventory changes
    between rounds so remapping can match by type.

    Returns list of dicts, each with:
      round: int, live_score: int, actions: list[dict]
    """
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    # Build per-bot inventory timeline for type inference
    bot_inv: dict[int, list[tuple[int, list[str]]]] = {}
    for row in rows:
        bid = int(row["bot_id"])
        rnd = int(row["round"])
        inv = row.get("inventory", "").split(";") if row.get("inventory") else []
        if bid not in bot_inv:
            bot_inv[bid] = []
        bot_inv[bid].append((rnd, inv))

    # Build lookup: (bot_id, round) -> inventory AFTER this round's action
    next_inv: dict[tuple[int, int], list[str]] = {}
    for bid, timeline in bot_inv.items():
        for i in range(len(timeline) - 1):
            rnd = timeline[i][0]
            next_inv[(bid, rnd)] = timeline[i + 1][1]

    rounds: list[dict[str, Any]] = []
    current_round = -1
    current: dict[str, Any] | None = None

    for row in rows:
        rnd = int(row["round"])
        if rnd != current_round:
            if current is not None:
                rounds.append(current)
            current = {
                "round": rnd,
                "live_score": int(row["score"]),
                "actions": [],
            }
            current_round = rnd

        bid = int(row["bot_id"])
        action: dict[str, Any] = {"bot": bid, "action": row["action"]}
        item_id = row.get("item_id", "")
        if item_id:
            action["item_id"] = item_id

        # Infer picked-up item type from inventory change
        if row["action"] == "pick_up":
            cur_inv = row.get("inventory", "").split(";") if row.get("inventory") else []
            after = next_inv.get((bid, rnd), [])
            if len(after) == len(cur_inv) + 1:
                # Find the new item type
                remaining = list(cur_inv)
                for item in after:
                    if item in remaining:
                        remaining.remove(item)
                    else:
                        action["pickup_type"] = item
                        break

        if current is not None:
            current["actions"].append(action)

    if current is not None:
        rounds.append(current)
    return rounds


def reconstruct_orders(csv_path: str) -> list[dict[str, Any]]:
    """Reconstruct orders from CSV active_needed column at each order transition."""
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    orders: list[dict[str, Any]] = []
    seen_idx: set[int] = set()

    for row in rows:
        idx_str = row.get("order_idx", "")
        needed_str = row.get("active_needed", "")
        preview_str = row.get("preview_needed", "")
        if not idx_str:
            continue
        idx = int(idx_str)

        if idx not in seen_idx and needed_str:
            seen_idx.add(idx)
            items = _parse_needed_str(needed_str)
            orders.append({"id": f"order_{idx}", "items_required": items})

        preview_idx = idx + 1
        if preview_idx not in seen_idx and preview_str:
            seen_idx.add(preview_idx)
            items = _parse_needed_str(preview_str)
            orders.append({"id": f"order_{preview_idx}", "items_required": items})

    orders.sort(key=lambda o: int(o["id"].split("_")[-1]))
    return orders


def _parse_needed_str(needed_str: str) -> list[str]:
    """Parse 'milk:2;cheese:1' into ['milk', 'milk', 'cheese']."""
    items: list[str] = []
    for part in needed_str.split(";"):
        if ":" not in part:
            continue
        name, count = part.split(":", 1)
        items.extend([name] * int(count))
    return items


def _infer_drop_off_zones(csv_path: str, primary_drop_off: list[int]) -> list[list[int]]:
    """Infer drop-off zones from CSV by finding where drop_off actions succeed."""
    zones: set[tuple[int, int]] = {(primary_drop_off[0], primary_drop_off[1])}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["action"] == "drop_off" and row.get("bot_pos"):
                parts = row["bot_pos"].split(",")
                zones.add((int(parts[0]), int(parts[1])))
    return [list(z) for z in sorted(zones)]


def _build_sim_from_meta(meta: dict[str, Any]) -> "GameSimulator":
    """Build a simulator from a live game JSON sidecar."""
    from grocery_bot.simulator.game_simulator import GameSimulator

    grid = meta["grid"]
    sim = object.__new__(GameSimulator)
    sim.width = grid["width"]
    sim.height = grid["height"]
    sim.max_rounds = meta["max_rounds"]
    sim.num_bots = meta["bots"]

    sim.walls = [list(w) for w in grid.get("wall_positions", [])]
    sim.drop_off = list(meta["drop_off"])
    zones = meta.get("drop_off_zones")
    sim.drop_off_zones = [list(z) for z in zones] if zones else [sim.drop_off]
    sim.spawn = list(meta["spawn"])

    sim.shelf_positions = set()
    sim.item_shelves = []
    sim.items_on_map = []
    for i, it in enumerate(meta.get("item_positions", [])):
        pos = (it["position"][0], it["position"][1])
        sim.shelf_positions.add(pos)
        sim.item_shelves.append((pos[0], pos[1], it["type"]))
        sim.items_on_map.append(
            {
                "id": f"item_{i}",
                "type": it["type"],
                "position": list(it["position"]),
            }
        )
    sim._next_item_id = len(sim.items_on_map)
    sim.item_type_names = sorted(meta.get("item_types", []))

    # Orders
    sim.orders = []
    for order in meta.get("orders", []):
        sim.orders.append(
            {
                "id": order["id"],
                "items_required": list(order["items_required"]),
                "items_delivered": [],
                "complete": False,
            }
        )

    # Game state
    sim.round = 0
    sim.score = 0
    sim.items_delivered = 0
    sim.orders_completed = 0
    sim.active_order_idx = 0

    # Bots at spawn
    sim.bots = []
    for i in range(sim.num_bots):
        sim.bots.append(
            {
                "id": i,
                "position": list(sim.spawn),
                "inventory": [],
            }
        )

    return sim


def _remap_actions(
    actions: list[dict[str, Any]],
    sim: Any,
) -> list[dict[str, Any]]:
    """Remap pick_up item_ids from live IDs to current sim IDs.

    Live server and sim generate different replacement item IDs after
    pickup. Match by position and type instead of ID.
    """
    remapped: list[dict[str, Any]] = []
    for a in actions:
        if a["action"] != "pick_up" or "item_id" not in a:
            remapped.append(a)
            continue
        # Always remap by position+type — never trust live IDs
        bot = next((b for b in sim.bots if b["id"] == a["bot"]), None)
        if not bot:
            remapped.append(a)
            continue
        bx, by = bot["position"]
        want_type = a.get("pickup_type")
        best = None
        for it in sim.items_on_map:
            ix, iy = it["position"]
            if abs(bx - ix) + abs(by - iy) != 1:
                continue
            if want_type and it["type"] != want_type:
                continue
            best = it
            break
        if not best and want_type:
            # Fallback: any adjacent item if type-match failed
            for it in sim.items_on_map:
                ix, iy = it["position"]
                if abs(bx - ix) + abs(by - iy) == 1:
                    best = it
                    break
        if best:
            remapped.append({**a, "item_id": best["id"]})
        else:
            remapped.append(a)
    return remapped


def replay_log(
    csv_path: str,
    json_path: str | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """Replay a live game log through simulator physics, comparing scores."""
    if json_path is None:
        json_path = csv_path.replace(".csv", ".json")
    with open(json_path) as f:
        meta = json.load(f)
    if "orders" not in meta or not meta["orders"]:
        meta["orders"] = reconstruct_orders(csv_path)
    if not meta.get("drop_off_zones"):
        meta["drop_off_zones"] = _infer_drop_off_zones(csv_path, meta["drop_off"])

    sim = _build_sim_from_meta(meta)
    parsed_rounds = parse_actions(csv_path)
    round_results: list[dict[str, Any]] = []
    first_divergence: dict[str, Any] | None = None
    total_divergences = 0
    max_score_delta = 0

    for entry in parsed_rounds:
        rnd, live_score = entry["round"], entry["live_score"]
        sim_score = sim.score
        sim.apply_actions(_remap_actions(entry["actions"], sim))
        delta = abs(sim_score - live_score)
        rd = {"round": rnd, "sim_score": sim_score, "live_score": live_score, "delta": delta}
        round_results.append(rd)
        if delta > 0:
            total_divergences += 1
            max_score_delta = max(max_score_delta, delta)
            if first_divergence is None:
                first_divergence = rd.copy()
            if verbose:
                print(f"R{rnd}: DIVERGE sim={sim_score} live={live_score} delta={delta}")

    return {
        "sim_final_score": sim.score,
        "live_final_score": meta.get("result", {}).get("score", 0),
        "first_divergence": first_divergence,
        "total_divergences": total_divergences,
        "max_score_delta": max_score_delta,
        "rounds": round_results,
    }
