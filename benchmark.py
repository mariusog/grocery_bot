"""Benchmark script for grocery bot performance analysis.

Benchmarks the recorded replay maps in `maps/`, preserving the
recorded order prefix and padding the unseen future tail with
deterministic synthetic orders.
"""

import glob as globmod
import os

from benchmark_reporting import (
    generate_replay_markdown_report,
    run_replay_benchmark,
)

DEFAULT_MAP_DIR = "maps"
DIFFICULTY_MAP_KEYS = {
    "Easy": ("12x10", "1bot"),
    "Medium": ("16x12", "3bot"),
    "Hard": ("22x14", "5bot"),
    "Expert": ("28x18", "10bot"),
    "Nightmare": ("30x18", "20bot"),
}


def _default_replay_map_files(map_dir: str = DEFAULT_MAP_DIR) -> list[str]:
    """Return replay maps from the latest day only."""
    if not os.path.isdir(map_dir):
        return []
    json_files = sorted(
        name for name in os.listdir(map_dir) if name.endswith(".json")
    )
    if not json_files:
        return []
    latest_date = json_files[-1][:10]
    return [
        os.path.join(map_dir, name)
        for name in json_files
        if name.startswith(latest_date)
    ]


def _replay_map_files_for_difficulties(
    difficulties: list[str] | None,
    map_dir: str = DEFAULT_MAP_DIR,
) -> list[str]:
    """Return recorded replay maps matching the requested difficulties."""
    map_files = _default_replay_map_files(map_dir)
    if not difficulties:
        return map_files

    wanted_keys = [DIFFICULTY_MAP_KEYS[diff] for diff in difficulties]
    selected = []
    for path in map_files:
        base = os.path.basename(path)
        if any(size in base and bots in base for size, bots in wanted_keys):
            selected.append(path)
    return selected


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Grocery Bot Benchmark")
    parser.add_argument(
        "--difficulty",
        "-d",
        nargs="+",
        choices=["Easy", "Medium", "Hard", "Expert", "Nightmare"],
        help="Run specific difficulties only",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print per-map results"
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Run with diagnostics (generates log files)",
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
    parser.add_argument(
        "--strict-replay",
        action="store_true",
        help="Use only the recorded replay orders with no synthetic padding",
    )
    args = parser.parse_args()

    os.makedirs("docs", exist_ok=True)

    if args.map:
        map_files = [args.map]
    elif args.map_dir:
        map_files = sorted(globmod.glob(os.path.join(args.map_dir, "*.json")))
        if not map_files:
            print(f"No .json files found in {args.map_dir}")
            raise SystemExit(1)
    else:
        map_files = _replay_map_files_for_difficulties(args.difficulty)
        if not map_files:
            print(f"No recorded maps found in {DEFAULT_MAP_DIR}/")
            raise SystemExit(1)

    replay_results = run_replay_benchmark(
        map_files,
        verbose=args.verbose,
        diagnose=args.diagnostics,
        pad_orders=not args.strict_replay,
    )
    with open("docs/benchmark_results.md", "w") as f:
        f.write(generate_replay_markdown_report(replay_results))
    print("\nReport written to docs/benchmark_results.md")
