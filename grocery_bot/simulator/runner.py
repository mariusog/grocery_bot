"""Benchmark runner and congestion profiler for the simulator."""

import statistics
import time
from collections import defaultdict

from grocery_bot.simulator.presets import DIFFICULTY_PRESETS
from grocery_bot.simulator.game_simulator import GameSimulator


def run_benchmark(configs=None, seeds=None, verbose=False):
    """Run multiple simulator configurations and print a comparison table."""
    if configs is None:
        configs = DIFFICULTY_PRESETS
    if seeds is None:
        seeds = [42]

    all_results = []
    print(
        f"{'Config':<10} {'Bots':>4} {'Seed':>5} {'Score':>6} "
        f"{'Orders':>7} {'Items':>6} {'Rounds':>7} {'Time(s)':>8}"
    )
    print("-" * 65)

    for cname, cfg in configs.items():
        config_scores = []
        for seed in seeds:
            t0 = time.perf_counter()
            sim = GameSimulator(seed=seed, **cfg)
            result = sim.run(verbose=verbose, profile=True)
            elapsed = time.perf_counter() - t0

            result["config"] = cname
            result["seed"] = seed
            result["num_bots"] = cfg.get("num_bots", 1)
            result["wall_time_s"] = elapsed
            all_results.append(result)
            config_scores.append(result["score"])

            print(
                f"{cname:<10} {cfg.get('num_bots', 1):>4} {seed:>5} "
                f"{result['score']:>6} {result['orders_completed']:>7} "
                f"{result['items_delivered']:>6} {result['rounds_used']:>7} "
                f"{elapsed:>8.3f}"
            )

        if len(seeds) > 1:
            avg = statistics.mean(config_scores)
            print(f"{'':10} {'':>4} {'AVG':>5} {avg:>6.1f}")

    return all_results


def profile_congestion(num_bots, seeds, verbose=False):
    """Run each seed with diagnostics and print a congestion profile table."""
    cfg = dict(DIFFICULTY_PRESETS["Hard"])
    cfg["num_bots"] = num_bots

    all_results = []
    header = (
        f"{'Seed':>5} {'Score':>6} {'Orders':>7} {'Items':>6} "
        f"{'Idle%':>6} {'Stuck%':>7} {'MaxGap':>7} {'Oscil':>6} "
        f"{'AvgIdle':>8} {'Status'}"
    )
    print(f"\n=== Congestion Profile: {num_bots} bots ===")
    print(header)
    print("-" * len(header))

    for seed in seeds:
        sim = GameSimulator(seed=seed, **cfg)
        result = sim.run(verbose=verbose, diagnose=True)
        result["seed"] = seed
        result["num_bots"] = num_bots
        all_results.append(result)

        diag = result["diagnostics"]
        total_br = diag["total_bot_rounds"]
        idle_pct = (diag["idle_rounds"] / total_br * 100) if total_br > 0 else 0
        stuck_pct = (diag["stuck_rounds"] / total_br * 100) if total_br > 0 else 0

        problems = []
        if result["score"] < 50:
            problems.append("LOW_SCORE")
        if idle_pct > 30:
            problems.append("HIGH_IDLE")
        if stuck_pct > 10:
            problems.append("HIGH_STUCK")
        if diag["max_delivery_gap"] > 40:
            problems.append("LONG_GAP")
        if diag["oscillation_count"] > 20:
            problems.append("OSCILLATING")
        status = ", ".join(problems) if problems else "OK"

        print(
            f"{seed:>5} {result['score']:>6} {result['orders_completed']:>7} "
            f"{result['items_delivered']:>6} {idle_pct:>5.1f}% {stuck_pct:>6.1f}% "
            f"{diag['max_delivery_gap']:>7} {diag['oscillation_count']:>6} "
            f"{diag['avg_bots_idle']:>8.2f} {status}"
        )

    scores = [r["score"] for r in all_results]
    print(f"\n  Average score: {statistics.mean(scores):.1f}")
    print(f"  Min score: {min(scores)}, Max score: {max(scores)}")
    problem_seeds = [
        r["seed"]
        for r in all_results
        if r["score"] < 50
        or (
            r["diagnostics"]["idle_rounds"] / r["diagnostics"]["total_bot_rounds"] * 100
            > 30
        )
    ]
    if problem_seeds:
        print(f"  Problematic seeds: {problem_seeds}")
    else:
        print("  No problematic seeds detected.")

    return all_results
