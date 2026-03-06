"""Benchmark script for grocery bot performance analysis.

Runs the bot through multiple simulator configurations and reports:
- Score, orders completed, items delivered, rounds used
- Per-function timing (decide_actions, bfs_all, tsp_route)
- Comparison across Easy/Medium/Hard difficulties
"""

import statistics
import time
from collections import defaultdict

import bot
from simulator import GameSimulator


# --- Timing infrastructure ---
_timings = defaultdict(list)  # func_name -> list of durations (seconds)


def _wrap_timer(func, name):
    """Wrap a function to record per-call timing."""
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - t0
        _timings[name].append(elapsed)
        return result
    return wrapper


def reset_timings():
    _timings.clear()


def timing_report():
    """Return formatted timing stats."""
    lines = []
    for name, times in sorted(_timings.items()):
        if not times:
            continue
        times_ms = [t * 1000 for t in times]
        avg = statistics.mean(times_ms)
        mx = max(times_ms)
        total = sum(times_ms)
        n = len(times_ms)
        # p99
        sorted_t = sorted(times_ms)
        p99_idx = min(int(n * 0.99), n - 1)
        p99 = sorted_t[p99_idx]
        lines.append(
            f"  {name:20s}  calls={n:5d}  avg={avg:7.3f}ms  "
            f"max={mx:7.3f}ms  p99={p99:7.3f}ms  total={total:8.1f}ms"
        )
    return "\n".join(lines)


# --- Benchmark configurations ---
CONFIGS = {
    "Easy": {
        "width": 12,
        "height": 10,
        "num_item_types": 4,
        "items_per_order": (3, 4),
        "max_rounds": 300,
    },
    "Medium": {
        "width": 16,
        "height": 12,
        "num_item_types": 6,
        "items_per_order": (3, 5),
        "max_rounds": 300,
    },
    "Hard": {
        "width": 22,
        "height": 14,
        "num_item_types": 10,
        "items_per_order": (4, 6),
        "max_rounds": 300,
    },
}


def run_single(config_name, seed, num_bots, config):
    """Run a single simulation, return result dict with timing."""
    reset_timings()

    # Patch timing wrappers
    orig_decide = bot.decide_actions
    orig_bfs_all = bot.bfs_all
    orig_tsp = bot.tsp_route
    bot.decide_actions = _wrap_timer(orig_decide, "decide_actions")
    bot.bfs_all = _wrap_timer(orig_bfs_all, "bfs_all")
    bot.tsp_route = _wrap_timer(orig_tsp, "tsp_route")

    try:
        sim = GameSimulator(
            seed=seed,
            num_bots=num_bots,
            width=config["width"],
            height=config["height"],
            num_item_types=config["num_item_types"],
            items_per_order=config["items_per_order"],
            max_rounds=config["max_rounds"],
        )

        # Reset bot globals
        bot._blocked_static = None
        bot._dist_cache = {}
        bot._adj_cache = {}
        bot._last_pickup = {}
        bot._pickup_fail_count = {}
        bot._blacklisted_items = set()

        t0 = time.perf_counter()
        while not sim.is_over():
            state = sim.get_state()
            if not state["orders"]:
                break
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)
        wall_time = time.perf_counter() - t0

        result = {
            "config": config_name,
            "seed": seed,
            "num_bots": num_bots,
            "score": sim.score,
            "orders_completed": sim.orders_completed,
            "items_delivered": sim.items_delivered,
            "rounds_used": sim.round,
            "wall_time_s": wall_time,
            "timings": dict(_timings),
        }
        return result
    finally:
        # Restore originals
        bot.decide_actions = orig_decide
        bot.bfs_all = orig_bfs_all
        bot.tsp_route = orig_tsp


def run_benchmark(configs=None):
    """Run full benchmark suite and print comparison table.

    Args:
        configs: dict of {name: config_dict}. Uses CONFIGS if None.

    Returns:
        list of result dicts.
    """
    if configs is None:
        configs = CONFIGS

    all_results = []

    # --- 1-bot benchmarks ---
    print("=" * 80)
    print("GROCERY BOT BENCHMARK")
    print("=" * 80)

    # 1 bot, seed 42 (Easy baseline)
    print("\n--- 1 bot, seed 42, Easy (baseline) ---")
    r = run_single("Easy", 42, 1, configs.get("Easy", CONFIGS["Easy"]))
    all_results.append(r)
    print(f"  Score: {r['score']}, Orders: {r['orders_completed']}, "
          f"Items: {r['items_delivered']}, Rounds: {r['rounds_used']}, "
          f"Wall: {r['wall_time_s']:.3f}s")
    print(timing_report())

    # 1 bot, seeds 1-10
    print("\n--- 1 bot, seeds 1-10, Easy (variance check) ---")
    scores = []
    orders = []
    items = []
    for seed in range(1, 11):
        r = run_single("Easy", seed, 1, configs.get("Easy", CONFIGS["Easy"]))
        all_results.append(r)
        scores.append(r["score"])
        orders.append(r["orders_completed"])
        items.append(r["items_delivered"])
    print(f"  Scores: {scores}")
    print(f"  Avg: {statistics.mean(scores):.1f}, Min: {min(scores)}, "
          f"Max: {max(scores)}, StdDev: {statistics.stdev(scores):.1f}")
    print(f"  Orders avg: {statistics.mean(orders):.1f}, "
          f"Items avg: {statistics.mean(items):.1f}")

    # 2 bots, seed 42
    print("\n--- 2 bots, seed 42, Easy ---")
    r = run_single("Easy", 42, 2, configs.get("Easy", CONFIGS["Easy"]))
    all_results.append(r)
    print(f"  Score: {r['score']}, Orders: {r['orders_completed']}, "
          f"Items: {r['items_delivered']}, Rounds: {r['rounds_used']}, "
          f"Wall: {r['wall_time_s']:.3f}s")
    print(timing_report())

    # 2 bots, seeds 1-5
    print("\n--- 2 bots, seeds 1-5, Easy ---")
    scores2 = []
    orders2 = []
    items2 = []
    for seed in range(1, 6):
        r = run_single("Easy", seed, 2, configs.get("Easy", CONFIGS["Easy"]))
        all_results.append(r)
        scores2.append(r["score"])
        orders2.append(r["orders_completed"])
        items2.append(r["items_delivered"])
    print(f"  Scores: {scores2}")
    print(f"  Avg: {statistics.mean(scores2):.1f}, Min: {min(scores2)}, "
          f"Max: {max(scores2)}")

    # Multi-difficulty comparison
    print("\n--- Difficulty comparison (1 bot, seed 42) ---")
    print(f"  {'Config':<10} {'Score':>6} {'Orders':>7} {'Items':>6} "
          f"{'Rounds':>7} {'Wall(s)':>8}")
    print(f"  {'-'*10} {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*8}")
    for cname, cfg in configs.items():
        r = run_single(cname, 42, 1, cfg)
        all_results.append(r)
        print(f"  {cname:<10} {r['score']:>6} {r['orders_completed']:>7} "
              f"{r['items_delivered']:>6} {r['rounds_used']:>7} "
              f"{r['wall_time_s']:>8.3f}")

    # Multi-difficulty with 2 bots
    print("\n--- Difficulty comparison (2 bots, seed 42) ---")
    print(f"  {'Config':<10} {'Score':>6} {'Orders':>7} {'Items':>6} "
          f"{'Rounds':>7} {'Wall(s)':>8}")
    print(f"  {'-'*10} {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*8}")
    for cname, cfg in configs.items():
        r = run_single(cname, 42, 2, cfg)
        all_results.append(r)
        print(f"  {cname:<10} {r['score']:>6} {r['orders_completed']:>7} "
              f"{r['items_delivered']:>6} {r['rounds_used']:>7} "
              f"{r['wall_time_s']:>8.3f}")

    # Multi-difficulty with 5 bots
    print("\n--- Difficulty comparison (5 bots, seed 42) ---")
    print(f"  {'Config':<10} {'Score':>6} {'Orders':>7} {'Items':>6} "
          f"{'Rounds':>7} {'Wall(s)':>8}")
    print(f"  {'-'*10} {'-'*6} {'-'*7} {'-'*6} {'-'*7} {'-'*8}")
    for cname, cfg in configs.items():
        r = run_single(cname, 42, 5, cfg)
        all_results.append(r)
        print(f"  {cname:<10} {r['score']:>6} {r['orders_completed']:>7} "
              f"{r['items_delivered']:>6} {r['rounds_used']:>7} "
              f"{r['wall_time_s']:>8.3f}")

    # Timing profile for Easy 1-bot (detailed)
    print("\n--- Timing Profile (Easy, 1 bot, seed 42) ---")
    reset_timings()
    r = run_single("Easy", 42, 1, configs.get("Easy", CONFIGS["Easy"]))
    print(timing_report())

    print("\n" + "=" * 80)
    return all_results


def generate_markdown_report(all_results):
    """Generate markdown report from benchmark results."""
    lines = []
    lines.append("# Benchmark Results\n")
    lines.append("Generated by `benchmark.py`\n")

    # Group results
    easy_1bot_42 = [r for r in all_results if r["config"] == "Easy"
                    and r["num_bots"] == 1 and r["seed"] == 42]
    easy_1bot_multi = [r for r in all_results if r["config"] == "Easy"
                       and r["num_bots"] == 1 and r["seed"] != 42]
    easy_2bot_42 = [r for r in all_results if r["config"] == "Easy"
                    and r["num_bots"] == 2 and r["seed"] == 42]
    easy_2bot_multi = [r for r in all_results if r["config"] == "Easy"
                       and r["num_bots"] == 2 and r["seed"] != 42]

    lines.append("## 1. Easy Baseline (1 bot, seed 42)\n")
    if easy_1bot_42:
        r = easy_1bot_42[0]
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Score | {r['score']} |")
        lines.append(f"| Orders completed | {r['orders_completed']} |")
        lines.append(f"| Items delivered | {r['items_delivered']} |")
        lines.append(f"| Rounds used | {r['rounds_used']} |")
        lines.append(f"| Wall time | {r['wall_time_s']:.3f}s |")
        lines.append("")

    lines.append("## 2. Variance Check (1 bot, seeds 1-10)\n")
    if easy_1bot_multi:
        lines.append("| Seed | Score | Orders | Items | Rounds |")
        lines.append("|------|-------|--------|-------|--------|")
        for r in sorted(easy_1bot_multi, key=lambda x: x["seed"]):
            lines.append(f"| {r['seed']} | {r['score']} | {r['orders_completed']} "
                         f"| {r['items_delivered']} | {r['rounds_used']} |")
        scores = [r["score"] for r in easy_1bot_multi]
        lines.append(f"\n**Average: {statistics.mean(scores):.1f}, "
                     f"Min: {min(scores)}, Max: {max(scores)}, "
                     f"StdDev: {statistics.stdev(scores):.1f}**\n")

    lines.append("## 3. Multi-bot (2 bots, seed 42)\n")
    if easy_2bot_42:
        r = easy_2bot_42[0]
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| Score | {r['score']} |")
        lines.append(f"| Orders completed | {r['orders_completed']} |")
        lines.append(f"| Items delivered | {r['items_delivered']} |")
        lines.append(f"| Rounds used | {r['rounds_used']} |")
        lines.append("")

    lines.append("## 4. Multi-bot Variance (2 bots, seeds 1-5)\n")
    if easy_2bot_multi:
        lines.append("| Seed | Score | Orders | Items |")
        lines.append("|------|-------|--------|-------|")
        for r in sorted(easy_2bot_multi, key=lambda x: x["seed"]):
            lines.append(f"| {r['seed']} | {r['score']} | {r['orders_completed']} "
                         f"| {r['items_delivered']} |")
        scores = [r["score"] for r in easy_2bot_multi]
        lines.append(f"\n**Average: {statistics.mean(scores):.1f}**\n")

    # Difficulty comparison tables
    for nb in [1, 2, 5]:
        diff_results = [r for r in all_results if r["num_bots"] == nb
                        and r["seed"] == 42 and r["config"] in ("Easy", "Medium", "Hard")]
        # Deduplicate: keep last result per config
        seen = {}
        for r in diff_results:
            seen[r["config"]] = r
        diff_results = [seen[c] for c in ("Easy", "Medium", "Hard") if c in seen]
        if diff_results:
            lines.append(f"## 5{'abc'[nb-1] if nb <= 3 else ''}. "
                         f"Difficulty Comparison ({nb} bot{'s' if nb > 1 else ''}, seed 42)\n")
            lines.append("| Config | Score | Orders | Items | Rounds | Wall Time |")
            lines.append("|--------|-------|--------|-------|--------|-----------|")
            for r in diff_results:
                lines.append(f"| {r['config']} | {r['score']} | {r['orders_completed']} "
                             f"| {r['items_delivered']} | {r['rounds_used']} "
                             f"| {r['wall_time_s']:.3f}s |")
            lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    import os
    results = run_benchmark()

    os.makedirs("docs", exist_ok=True)
    report = generate_markdown_report(results)

    # The report will be completed with code review findings later
    with open("docs/benchmark_results.md", "w") as f:
        f.write(report)
    print("\nReport written to docs/benchmark_results.md")
