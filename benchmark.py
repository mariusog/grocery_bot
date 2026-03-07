"""Benchmark script for grocery bot performance analysis.

Runs the bot through simulator difficulty presets matching the challenge:
  Easy:   1 bot,  12x10, 4 types,  orders 3-4
  Medium: 3 bots, 16x12, 8 types,  orders 3-5
  Hard:   5 bots, 22x14, 12 types, orders 3-5
  Expert: 10 bots, 28x18, 16 types, orders 4-6

Reports score, orders, items, timing across 20 seeds per difficulty.
"""

import statistics
import time

from grocery_bot.simulator import GameSimulator, DIFFICULTY_PRESETS

# Number of seeds for averaging
DEFAULT_SEEDS = list(range(1, 21))
QUICK_SEEDS = [42]


def run_game(difficulty, seed, diagnose=False):
    """Run a single game and return result dict."""
    import bot

    cfg = DIFFICULTY_PRESETS[difficulty]
    bot.reset_state()

    sim = GameSimulator(seed=seed, **cfg)
    t0 = time.perf_counter()
    result = sim.run(profile=True, diagnose=diagnose)
    wall = time.perf_counter() - t0

    result["difficulty"] = difficulty
    result["seed"] = seed
    result["num_bots"] = cfg["num_bots"]
    result["wall_time_s"] = wall
    return result


def run_benchmark(difficulties=None, seeds=None, verbose=False, diagnose=False):
    """Run benchmark across difficulties and seeds.

    Args:
        difficulties: list of difficulty names. Defaults to all four.
        seeds: list of seeds. Defaults to 1-20.
        verbose: print per-seed results.
        diagnose: run with diagnostics enabled and print summary.

    Returns:
        dict of {difficulty: list of result dicts}
    """
    if difficulties is None:
        difficulties = ["Easy", "Medium", "Hard", "Expert", "Nightmare"]
    if seeds is None:
        seeds = DEFAULT_SEEDS

    all_results = {}

    print("=" * 72)
    print("GROCERY BOT BENCHMARK")
    print(f"Seeds: {len(seeds)}  Difficulties: {', '.join(difficulties)}")
    print("=" * 72)

    for diff in difficulties:
        cfg = DIFFICULTY_PRESETS[diff]
        print(
            f"\n--- {diff} ({cfg['num_bots']} bot{'s' if cfg['num_bots'] > 1 else ''}, "
            f"{cfg['width']}x{cfg['height']}, {cfg['num_item_types']} types, "
            f"orders {cfg['items_per_order'][0]}-{cfg['items_per_order'][1]}) ---"
        )

        results = []
        for seed in seeds:
            r = run_game(diff, seed, diagnose=diagnose)
            results.append(r)
            if verbose:
                print(
                    f"  seed={seed:>3}  score={r['score']:>4}  "
                    f"orders={r['orders_completed']:>3}  "
                    f"items={r['items_delivered']:>3}  "
                    f"wall={r['wall_time_s']:.3f}s"
                )

        scores = [r["score"] for r in results]
        orders = [r["orders_completed"] for r in results]
        items = [r["items_delivered"] for r in results]
        walls = [r["wall_time_s"] for r in results]

        avg_score = statistics.mean(scores)
        std_score = statistics.stdev(scores) if len(scores) > 1 else 0

        print(
            f"  Avg: {avg_score:.1f}  Min: {min(scores)}  Max: {max(scores)}  "
            f"StdDev: {std_score:.1f}"
        )
        print(
            f"  Orders avg: {statistics.mean(orders):.1f}  "
            f"Items avg: {statistics.mean(items):.1f}"
        )
        print(f"  Wall avg: {statistics.mean(walls):.3f}s  max: {max(walls):.3f}s")

        # Timing from profiled games
        timing_avgs = []
        for r in results:
            t = r.get("timings", {}).get("decide_actions", {})
            if t:
                timing_avgs.append(t["avg_ms"])
        if timing_avgs:
            print(
                f"  decide_actions avg: {statistics.mean(timing_avgs):.3f}ms/round  "
                f"max: {max(timing_avgs):.3f}ms/round"
            )

        all_results[diff] = results

    print("\n" + "=" * 72)
    print_summary_table(all_results)
    print("=" * 72)

    return all_results


def print_summary_table(all_results):
    """Print a compact summary table."""
    print(
        f"\n{'Difficulty':<10} {'Bots':>4} {'Avg':>6} {'Min':>5} {'Max':>5} "
        f"{'StdDev':>6} {'Orders':>6} {'Items':>5} {'Wall':>6}"
    )
    print("-" * 60)
    for diff in ["Easy", "Medium", "Hard", "Expert", "Nightmare"]:
        if diff not in all_results:
            continue
        results = all_results[diff]
        scores = [r["score"] for r in results]
        orders = [r["orders_completed"] for r in results]
        items = [r["items_delivered"] for r in results]
        walls = [r["wall_time_s"] for r in results]
        std = statistics.stdev(scores) if len(scores) > 1 else 0
        print(
            f"{diff:<10} {results[0]['num_bots']:>4} {statistics.mean(scores):>6.1f} "
            f"{min(scores):>5} {max(scores):>5} {std:>6.1f} "
            f"{statistics.mean(orders):>6.1f} {statistics.mean(items):>5.1f} "
            f"{statistics.mean(walls):>5.3f}s"
        )


def print_diagnostics_table(all_results):
    """Print a diagnostic summary table showing action breakdown and efficiency metrics."""
    print("\n" + "=" * 90)
    print("DIAGNOSTICS SUMMARY")
    print("=" * 90)

    # Header
    print(
        f"\n{'Diff':<8} {'Bots':>4} {'Score':>5} "
        f"{'Moves':>6} {'Waits':>6} {'Picks':>5} {'Deliv':>5} "
        f"{'Waste%':>6} {'InvFW':>5} {'Rds/Ord':>7} {'P/D':>5} "
        f"{'Idle%':>5} {'Stuck%':>6}"
    )
    print("-" * 90)

    for diff in ["Easy", "Medium", "Hard", "Expert", "Nightmare"]:
        if diff not in all_results:
            continue
        results = all_results[diff]
        # Only include results that have diagnostics
        diag_results = [r for r in results if "diagnostics" in r]
        if not diag_results:
            continue

        n = len(diag_results)
        avg_score = statistics.mean([r["score"] for r in diag_results])
        num_bots = diag_results[0]["num_bots"]

        # Aggregate diagnostics
        def avg_diag(key):
            return statistics.mean([r["diagnostics"][key] for r in diag_results])

        moves = avg_diag("moves")
        waits = avg_diag("waits")
        pickups = avg_diag("pickups")
        delivers = avg_diag("delivers")
        waste_pct = avg_diag("pickup_waste_pct")
        inv_full = avg_diag("inv_full_waits")
        rds_per_order = avg_diag("avg_rounds_per_order")
        pd_ratio = avg_diag("pickup_delivery_ratio")
        total_br = avg_diag("total_bot_rounds")
        idle_pct = avg_diag("idle_rounds") / total_br * 100 if total_br > 0 else 0
        stuck_pct = avg_diag("stuck_rounds") / total_br * 100 if total_br > 0 else 0

        print(
            f"{diff:<8} {num_bots:>4} {avg_score:>5.0f} "
            f"{moves:>6.0f} {waits:>6.0f} {pickups:>5.0f} {delivers:>5.0f} "
            f"{waste_pct:>5.1f}% {inv_full:>5.0f} {rds_per_order:>7.1f} {pd_ratio:>5.2f} "
            f"{idle_pct:>4.1f}% {stuck_pct:>5.1f}%"
        )

    # Per-bot idle breakdown for multi-bot difficulties
    print("\n--- Per-Bot Idle Rounds (avg across seeds) ---")
    for diff in ["Medium", "Hard", "Expert"]:
        if diff not in all_results:
            continue
        diag_results = [r for r in all_results[diff] if "diagnostics" in r]
        if not diag_results:
            continue

        num_bots = diag_results[0]["num_bots"]
        total_rounds = statistics.mean([r["rounds_used"] for r in diag_results])

        # Aggregate per-bot idle across seeds
        bot_idles = {}
        for r in diag_results:
            for bid_str, idle in r["diagnostics"]["per_bot_idle"].items():
                bid = int(bid_str) if isinstance(bid_str, str) else bid_str
                bot_idles.setdefault(bid, []).append(idle)

        bot_avgs = {bid: statistics.mean(vals) for bid, vals in bot_idles.items()}
        parts = []
        for bid in sorted(bot_avgs):
            idle_avg = bot_avgs[bid]
            pct = idle_avg / total_rounds * 100 if total_rounds > 0 else 0
            parts.append(f"B{bid}:{pct:.0f}%")
        print(f"  {diff:<8} {' '.join(parts)}")

    print()
    # Legend
    print("Legend: Waste%=non-active pickups, InvFW=inventory-full waits,")
    print("        Rds/Ord=avg rounds per order, P/D=pickup-to-delivery ratio")
    print("=" * 90)


def generate_markdown_report(all_results):
    """Generate markdown report from benchmark results."""
    lines = [
        "# Benchmark Results\n",
        "Generated by `benchmark.py`\n",
    ]

    # Summary table
    lines.append("## Summary\n")
    lines.append(
        "| Difficulty | Bots | Avg Score | Min | Max | StdDev | Avg Orders | Avg Items |"
    )
    lines.append(
        "|------------|------|-----------|-----|-----|--------|------------|-----------|"
    )
    for diff in ["Easy", "Medium", "Hard", "Expert", "Nightmare"]:
        if diff not in all_results:
            continue
        results = all_results[diff]
        scores = [r["score"] for r in results]
        orders = [r["orders_completed"] for r in results]
        items = [r["items_delivered"] for r in results]
        std = statistics.stdev(scores) if len(scores) > 1 else 0
        lines.append(
            f"| {diff} | {results[0]['num_bots']} | {statistics.mean(scores):.1f} "
            f"| {min(scores)} | {max(scores)} | {std:.1f} "
            f"| {statistics.mean(orders):.1f} | {statistics.mean(items):.1f} |"
        )
    lines.append("")

    # Per-difficulty detail
    for diff in ["Easy", "Medium", "Hard", "Expert", "Nightmare"]:
        if diff not in all_results:
            continue
        results = all_results[diff]
        cfg = DIFFICULTY_PRESETS[diff]
        lines.append(
            f"## {diff} ({cfg['num_bots']} bots, {cfg['width']}x{cfg['height']})\n"
        )
        lines.append("| Seed | Score | Orders | Items | Wall Time |")
        lines.append("|------|-------|--------|-------|-----------|")
        for r in sorted(results, key=lambda x: x["seed"]):
            lines.append(
                f"| {r['seed']} | {r['score']} | {r['orders_completed']} "
                f"| {r['items_delivered']} | {r['wall_time_s']:.3f}s |"
            )
        scores = [r["score"] for r in results]
        lines.append(f"\n**Average: {statistics.mean(scores):.1f}**\n")

    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Grocery Bot Benchmark")
    parser.add_argument(
        "--quick", action="store_true", help="Run single seed (42) instead of 20 seeds"
    )
    parser.add_argument(
        "--seeds", type=int, default=20, help="Number of seeds to run (default: 20)"
    )
    parser.add_argument(
        "--difficulty",
        "-d",
        nargs="+",
        choices=["Easy", "Medium", "Hard", "Expert", "Nightmare"],
        help="Run specific difficulties only",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-seed results"
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Run with diagnostics and print action breakdown per difficulty",
    )
    args = parser.parse_args()

    seeds = QUICK_SEEDS if args.quick else list(range(1, args.seeds + 1))
    difficulties = args.difficulty

    results = run_benchmark(
        difficulties=difficulties,
        seeds=seeds,
        verbose=args.verbose,
        diagnose=args.diagnostics,
    )

    if args.diagnostics:
        print_diagnostics_table(results)

    os.makedirs("docs", exist_ok=True)
    report = generate_markdown_report(results)
    with open("docs/benchmark_results.md", "w") as f:
        f.write(report)
    print("\nReport written to docs/benchmark_results.md")
