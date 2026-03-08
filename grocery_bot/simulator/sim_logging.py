"""Logging and timing helpers for local simulator runs."""

import csv
import glob
import json
import os
import statistics
from collections import defaultdict
from datetime import datetime
from typing import Any

from grocery_bot.orders import get_needed_items
from grocery_bot.simulator.presets import DIFFICULTY_PRESETS


_LOG_DIR = "logs"
_MAX_LOCAL_LOGS = 10


def make_timings() -> defaultdict:
    """Create a fresh timings accumulator for profiling."""
    return defaultdict(list)


def compute_timing_stats(timings: dict[str, list[float]]) -> dict[str, Any]:
    """Compute timing statistics from profiled data."""
    timing_stats: dict[str, Any] = {}
    for name, vals in timings.items():
        ms = [v * 1000 for v in vals]
        sorted_ms = sorted(ms)
        p99_idx = min(int(len(ms) * 0.99), len(ms) - 1)
        timing_stats[name] = {
            "calls": len(ms),
            "avg_ms": statistics.mean(ms),
            "max_ms": max(ms),
            "p99_ms": sorted_ms[p99_idx],
            "total_ms": sum(ms),
        }
    return timing_stats


def infer_difficulty_slug(sim: Any) -> str:
    """Best-effort difficulty label for local replay/log filenames."""
    item_type_count = len(
        getattr(sim, "item_type_names", [])
        or {it["type"] for it in getattr(sim, "items_on_map", [])}
    )
    for name, cfg in DIFFICULTY_PRESETS.items():
        if (
            sim.width == cfg["width"]
            and sim.height == cfg["height"]
            and sim.num_bots == cfg["num_bots"]
            and sim.max_rounds == cfg["max_rounds"]
            and item_type_count == cfg["num_item_types"]
        ):
            return name.lower()
    return "custom"


def log_round(
    state: dict, actions: list[dict], log_rows: list[dict],
) -> None:
    """Record one round of actions in the same CSV format as live games."""
    active_o = next(
        (o for o in state["orders"] if o.get("status") == "active" and not o["complete"]),
        None,
    )
    preview_o = next((o for o in state["orders"] if o.get("status") == "preview"), None)
    for a in actions:
        b = next(bt for bt in state["bots"] if bt["id"] == a["bot"])
        log_rows.append({
            "round": state["round"],
            "score": state["score"],
            "order_idx": state.get("active_order_index", ""),
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
            "items_carried": len(b["inventory"]),
            "dist_to_dropoff": (
                abs(b["position"][0] - state["drop_off"][0])
                + abs(b["position"][1] - state["drop_off"][1])
            ),
        })


def save_local_log(
    sim: Any,
    log_rows: list[dict],
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """Save CSV + JSON for a local simulator run, pruning old logs."""
    os.makedirs(_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    difficulty = infer_difficulty_slug(sim)
    prefix = f"local_{difficulty}_{sim.width}x{sim.height}_{sim.num_bots}bot_{timestamp}"
    csv_path = f"{_LOG_DIR}/{prefix}.csv"
    json_path = f"{_LOG_DIR}/{prefix}.json"

    _write_csv(csv_path, log_rows)
    _write_meta_json(json_path, sim, timestamp, difficulty, diagnostics)
    _prune_old_logs()
    return csv_path


def _write_csv(csv_path: str, log_rows: list[dict]) -> None:
    """Write round-log rows to a CSV file."""
    fieldnames = [
        "round", "score", "order_idx", "bot_id", "bot_pos",
        "inventory", "action", "item_id", "active_needed",
        "active_delivered", "preview_needed",
        "items_carried", "dist_to_dropoff",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)


def _write_meta_json(
    json_path: str,
    sim: Any,
    timestamp: str,
    difficulty: str,
    diagnostics: dict[str, Any] | None = None,
) -> None:
    """Write game metadata to a JSON sidecar file."""
    item_types = sorted({it["type"] for it in sim.items_on_map})
    meta: dict[str, Any] = {
        "timestamp": timestamp,
        "source": "local_simulator",
        "difficulty": difficulty,
        "grid": {
            "width": sim.width,
            "height": sim.height,
            "walls": len(sim.walls),
            "wall_positions": [list(w) for w in sim.walls],
        },
        "bots": sim.num_bots,
        "items_on_map": len(sim.items_on_map),
        "item_types": item_types,
        "item_positions": [
            {"type": it["type"], "position": list(it["position"])}
            for it in sim.items_on_map
        ],
        "drop_off": list(sim.drop_off),
        "drop_off_zones": [list(z) for z in sim.drop_off_zones],
        "max_rounds": sim.max_rounds,
        "total_orders": len(sim.orders),
        "spawn": list(sim.spawn),
        "result": {
            "score": sim.score,
            "rounds_used": sim.round,
            "items_delivered": sim.items_delivered,
            "orders_completed": sim.orders_completed,
        },
    }
    if diagnostics:
        meta["diagnostics"] = diagnostics
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2)


def _prune_old_logs() -> None:
    """Remove oldest local log files beyond the retention limit."""
    local_csvs = sorted(glob.glob(f"{_LOG_DIR}/local_*.csv"))
    while len(local_csvs) > _MAX_LOCAL_LOGS:
        old_csv = local_csvs.pop(0)
        old_json = old_csv.replace(".csv", ".json")
        os.remove(old_csv)
        if os.path.exists(old_json):
            os.remove(old_json)
