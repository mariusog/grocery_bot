"""Reporting functions for grocery bot benchmark results.

Extracted from benchmark.py: summary tables, diagnostics, markdown, replay.
"""

import os
import statistics
import time

from grocery_bot.simulator import DIFFICULTY_PRESETS


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


def _safe_avg_diag(diag_results: list, key: str, default: float = 0.0) -> float:
    """Average a diagnostics key, returning default if key is missing."""
    vals = [r["diagnostics"][key] for r in diag_results if key in r["diagnostics"]]
    return statistics.mean(vals) if vals else default


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
        f"{'Idle%':>5} {'Stuck%':>6} {'AvDel':>5} {'Blk%':>5}"
    )
    print("-" * 100)

    for diff in ["Easy", "Medium", "Hard", "Expert", "Nightmare"]:
        if diff not in all_results:
            continue
        results = all_results[diff]
        # Only include results that have diagnostics
        diag_results = [r for r in results if "diagnostics" in r]
        if not diag_results:
            continue

        avg_score = statistics.mean([r["score"] for r in diag_results])
        num_bots = diag_results[0]["num_bots"]

        # Aggregate diagnostics
        def avg_diag(key, _dr=diag_results):
            return statistics.mean([r["diagnostics"][key] for r in _dr])

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
        avg_del = _safe_avg_diag(diag_results, "avg_delivery_size")
        blk_pct = _safe_avg_diag(diag_results, "blocked_move_pct")

        print(
            f"{diff:<8} {num_bots:>4} {avg_score:>5.0f} "
            f"{moves:>6.0f} {waits:>6.0f} {pickups:>5.0f} {delivers:>5.0f} "
            f"{waste_pct:>5.1f}% {inv_full:>5.0f} {rds_per_order:>7.1f} {pd_ratio:>5.2f} "
            f"{idle_pct:>4.1f}% {stuck_pct:>5.1f}% {avg_del:>5.2f} {blk_pct:>4.1f}%"
        )

    # Per-bot action breakdown for multi-bot difficulties
    _print_per_bot_actions(all_results)

    # Order completion timeline
    _print_order_timeline(all_results)

    print()
    # Legend
    print("Legend: Waste%=non-active pickups, InvFW=inventory-full waits,")
    print("        Rds/Ord=avg rounds per order, P/D=pickup-to-delivery ratio,")
    print("        AvDel=avg items per delivery, Blk%=blocked moves")
    print("=" * 100)


def _print_per_bot_actions(all_results: dict) -> None:
    """Print per-bot action breakdown for multi-bot difficulties."""
    print("\n--- Per-Bot Actions (avg across seeds) ---")
    for diff in ["Medium", "Hard", "Expert"]:
        if diff not in all_results:
            continue
        diag_results = [
            r for r in all_results[diff]
            if "diagnostics" in r and "per_bot_actions" in r["diagnostics"]
        ]
        if not diag_results:
            continue

        num_bots = diag_results[0]["num_bots"]
        total_rounds = statistics.mean([r["rounds_used"] for r in diag_results])
        print(f"  {diff} ({num_bots} bots, {total_rounds:.0f} rounds):")
        print(f"    {'Bot':>5} {'Moves':>6} {'Picks':>5} {'Deliv':>5} {'Idle':>5} {'Stuck':>5} {'Util%':>5}")
        for bid in range(num_bots):
            bkey = str(bid) if str(bid) in diag_results[0]["diagnostics"]["per_bot_actions"] else bid
            vals = [r["diagnostics"]["per_bot_actions"].get(bkey, {}) for r in diag_results]
            moves = statistics.mean([v.get("moves", 0) for v in vals])
            picks = statistics.mean([v.get("pickups", 0) for v in vals])
            deliv = statistics.mean([v.get("delivers", 0) for v in vals])
            idle = statistics.mean([v.get("idle", 0) for v in vals])
            stuck = statistics.mean([v.get("stuck", 0) for v in vals])
            util = (moves + picks + deliv) / max(1, total_rounds) * 100
            print(f"    B{bid:<4} {moves:>6.0f} {picks:>5.0f} {deliv:>5.0f} {idle:>5.0f} {stuck:>5.0f} {util:>4.0f}%")


def _print_order_timeline(all_results: dict) -> None:
    """Print order completion timeline summary."""
    print("\n--- Order Completion Timeline (avg across seeds) ---")
    for diff in ["Easy", "Medium", "Hard", "Expert"]:
        if diff not in all_results:
            continue
        diag_results = [
            r for r in all_results[diff]
            if "diagnostics" in r and "order_completion_rounds" in r["diagnostics"]
        ]
        if not diag_results:
            continue

        all_timelines = [r["diagnostics"]["order_completion_rounds"] for r in diag_results]
        max_orders = max(len(t) for t in all_timelines) if all_timelines else 0
        if max_orders == 0:
            continue

        avg_rounds = []
        for i in range(min(max_orders, 10)):
            vals = [t[i] for t in all_timelines if i < len(t)]
            avg_rounds.append(statistics.mean(vals) if vals else 0)

        timeline = " -> ".join(f"O{i + 1}@R{r:.0f}" for i, r in enumerate(avg_rounds))
        suffix = f" ... ({max_orders} total)" if max_orders > 10 else ""
        print(f"  {diff:<8} {timeline}{suffix}")


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


def generate_replay_markdown_report(results):
    """Generate markdown report from replay benchmark results."""
    lines = [
        "# Replay Benchmark Results\n",
        "Generated by `benchmark.py` from recorded maps in `maps/`.\n",
        "## Summary\n",
        "| Map | Bots | Grid | Score | Recorded | Total | Done | Items | Wall |",
        "|-----|------|------|-------|----------|-------|------|-------|------|",
    ]
    for r in results:
        lines.append(
            f"| {r['map_file']} | {r['num_bots']} | {r['grid_size']} "
            f"| {r['score']} | {r['recorded_orders']} | {r['total_orders']} "
            f"| {r['orders_completed']} | {r['items_delivered']} | {r['wall_time_s']:.3f}s |"
        )
    if results:
        scores = [r["score"] for r in results]
        items = sum(r["items_delivered"] for r in results)
        walls = [r["wall_time_s"] for r in results]
        lines.append(
            f"\n**Total: {sum(scores)}** | Orders: {sum(r['orders_completed'] for r in results)}"
            f" | Items: {items} | Avg wall: {statistics.mean(walls):.3f}s\n"
        )
    return "\n".join(lines)


def run_replay_game(map_path, diagnose=False, pad_orders=True):
    """Run a single game using a recorded map and return result dict."""
    import bot
    from grocery_bot.simulator import ReplaySimulator

    bot.reset_state()
    sim = ReplaySimulator(map_path, pad_orders=pad_orders)
    t0 = time.perf_counter()
    result = sim.run(profile=True, diagnose=diagnose, log=diagnose)
    wall = time.perf_counter() - t0

    result["map_file"] = os.path.basename(map_path)
    result["num_bots"] = sim.num_bots
    result["grid_size"] = f"{sim.width}x{sim.height}"
    result["recorded_orders"] = sim.recorded_order_count
    result["total_orders"] = len(sim.orders)
    result["synthetic_orders"] = sim.synthetic_order_count
    result["wall_time_s"] = wall
    return result


def run_replay_benchmark(map_paths, verbose=False, diagnose=False, pad_orders=True):
    """Run benchmark against recorded maps."""
    print("=" * 72)
    print("GROCERY BOT REPLAY BENCHMARK")
    print(f"Maps: {len(map_paths)}")
    print("=" * 72)

    all_results = []
    for map_path in map_paths:
        r = run_replay_game(map_path, diagnose=diagnose, pad_orders=pad_orders)
        all_results.append(r)
        print(
            f"  {r['map_file']}: score={r['score']:>4}  "
            f"orders={r['orders_completed']:>3}  "
            f"recorded={r['recorded_orders']:>3}  "
            f"total={r['total_orders']:>3}  "
            f"items={r['items_delivered']:>3}  "
            f"bots={r['num_bots']}  grid={r['grid_size']}  "
            f"wall={r['wall_time_s']:.3f}s"
        )

    if all_results:
        scores = [r["score"] for r in all_results]
        print(f"\n  Total: {sum(scores)}  Avg: {statistics.mean(scores):.1f}")

    return all_results
