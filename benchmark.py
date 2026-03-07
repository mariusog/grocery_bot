"""Benchmark script for grocery bot performance analysis.

Runs the bot through simulator difficulty presets matching the challenge:
  Easy:   1 bot,  12x10, 4 types,  orders 3-4
  Medium: 3 bots, 16x12, 8 types,  orders 3-5
  Hard:   5 bots, 22x14, 12 types, orders 3-5
  Expert: 10 bots, 28x18, 16 types, orders 4-6

Reports score, orders, items, timing across 20 seeds per difficulty.
"""

import os
import statistics
import time

from grocery_bot.simulator import GameSimulator, DIFFICULTY_PRESETS
from benchmark_reporting import (
    print_summary_table,
    print_diagnostics_table,
    generate_markdown_report,
    run_replay_benchmark,
)

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


if __name__ == "__main__":
    import argparse
    import glob as globmod

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
    parser.add_argument(
        "--map", type=str, help="Path to a single recorded map JSON to benchmark"
    )
    parser.add_argument(
        "--map-dir",
        type=str,
        default=None,
        help="Directory of recorded map JSONs (benchmarks all of them)",
    )
    args = parser.parse_args()

    if args.map:
        run_replay_benchmark([args.map], verbose=args.verbose, diagnose=args.diagnostics)
    elif args.map_dir:
        map_files = sorted(globmod.glob(os.path.join(args.map_dir, "*.json")))
        if not map_files:
            print(f"No .json files found in {args.map_dir}")
        else:
            run_replay_benchmark(
                map_files, verbose=args.verbose, diagnose=args.diagnostics
            )
    else:
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
