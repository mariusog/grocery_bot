"""Parameter sweep using recorded replay maps only.

Usage:
    python sweep.py                    # sweep all bot counts
    python sweep.py -b 20             # sweep 20-bot maps only
    python sweep.py -b 10 -p blocking_radius  # sweep one param
"""

import argparse
import glob
import time
from dataclasses import replace
from typing import Any

import bot
from grocery_bot.simulator import ReplaySimulator
from grocery_bot.team_config import TeamConfig, get_team_config
import grocery_bot.team_config as tc_module
import grocery_bot.planner.round_planner as rp_module


def _find_maps(num_bots: int) -> list[str]:
    """Find all replay maps for a given bot count."""
    pattern = f"maps/*_{num_bots}bot.json"
    return sorted(glob.glob(pattern))


def replay_with_override(
    num_bots: int, override: dict[str, Any],
) -> list[int]:
    """Run replay maps with a TeamConfig override, return per-map scores."""
    maps = _find_maps(num_bots)
    if not maps:
        return []

    original_fn = tc_module.get_team_config
    original_rp = rp_module.get_team_config

    if override:
        base_cfg = original_fn(num_bots)
        patched = replace(base_cfg, **override)

        def patched_get(n: int) -> TeamConfig:
            return patched if n == num_bots else original_fn(n)

        tc_module.get_team_config = patched_get
        rp_module.get_team_config = patched_get

    scores: list[int] = []
    try:
        for f in maps:
            bot.reset_state()
            sim = ReplaySimulator(f)
            result = sim.run()
            scores.append(result["score"])
    finally:
        tc_module.get_team_config = original_fn
        rp_module.get_team_config = original_rp
    return scores


def sweep_param(
    num_bots: int,
    param: str,
    values: list[Any],
    baseline_avg: float,
) -> None:
    """Sweep one parameter and print results."""
    print(f"  {param}:")
    for val in values:
        scores = replay_with_override(num_bots, {param: val})
        avg = sum(scores) / len(scores) if scores else 0
        delta = avg - baseline_avg
        marker = " ***" if delta > 2.0 else ""
        print(f"    {str(val):>8} -> {scores}  avg={avg:.1f}  ({delta:+.1f}){marker}")


# Bot-count to sweep params mapping
SWEEP_PARAMS: dict[int, dict[str, list[Any]]] = {
    3: {
        "use_coordination": [True, False],
        "use_dropoff_weight": [True, False],
        "blocking_radius": [float("inf"), 4.0, 6.0],
    },
    5: {
        "enable_speculative": [True, False],
        "use_coordination": [True, False],
        "max_concurrent_deliverers": [1, 2, 3],
        "max_nonactive_deliverers": [1, 2],
        "blocking_radius": [float("inf"), 3.0, 4.0, 5.0],
        "use_dropoff_weight": [True, False],
        "preview_stage_weight": [0.0, 0.3, 0.5, 0.7],
        "target_attraction_weight": [0.0, 0.3, 0.5, 1.0],
    },
    10: {
        "max_concurrent_deliverers": [2, 3, 4, 5],
        "max_nonactive_deliverers": [1, 2, 3, 4],
        "blocking_radius": [3.0, 4.0, 5.0, 6.0],
        "preview_stage_weight": [0.0, 0.2, 0.4, 0.6],
        "target_attraction_weight": [0.0, 0.3, 0.5],
        "use_idle_spots": [True, False],
        "use_corridor_penalty": [True, False],
        "min_inv_nonactive_idle": [1, 2],
    },
    20: {
        "max_concurrent_deliverers": [3, 5, 6, 7, 10],
        "max_nonactive_deliverers": [3, 4, 5, 6, 7, 8],
        "blocking_radius": [2.0, 3.0, 4.0, 5.0],
        "preview_stage_weight": [0.0, 0.2, 0.4, 0.6],
        "target_attraction_weight": [0.0, 0.3, 0.5],
        "use_idle_spots": [True, False],
        "use_corridor_penalty": [True, False],
        "extra_preview_roles": [True, False],
        "enable_spec_assignment": [True, False],
    },
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Parameter sweep on replay maps")
    parser.add_argument("-b", "--bots", type=int, help="Bot count to sweep")
    parser.add_argument("-p", "--param", help="Single parameter to sweep")
    args = parser.parse_args()

    bot_counts = [args.bots] if args.bots else sorted(SWEEP_PARAMS.keys())

    for num_bots in bot_counts:
        params = SWEEP_PARAMS.get(num_bots, {})
        if args.param:
            params = {args.param: params[args.param]}

        maps = _find_maps(num_bots)
        if not maps:
            print(f"\n{num_bots}bot: no replay maps found")
            continue

        t0 = time.perf_counter()
        baseline = replay_with_override(num_bots, {})
        baseline_avg = sum(baseline) / len(baseline)
        print(f"\n{'='*60}")
        print(f"{num_bots}bot (baseline={baseline} avg={baseline_avg:.1f}, maps={len(maps)})")
        print(f"{'='*60}")

        for param, values in params.items():
            sweep_param(num_bots, param, values, baseline_avg)

        print(f"  [{time.perf_counter() - t0:.1f}s elapsed]")


if __name__ == "__main__":
    main()
