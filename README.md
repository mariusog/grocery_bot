# Grocery Bot

An AI-powered bot for the **NM i AI 2026** warm-up challenge. It controls a swarm of workers in a procedurally generated grocery store, navigating a grid to pick items from shelves and deliver them to drop-off zones to fulfill orders as fast as possible.

## How It Works

- **WebSocket client** (`bot.py`) connects to the game server and receives the full map state each round
- **GameState** (`grocery_bot/game_state/`) maintains caches, precomputed route tables, and bot-to-item assignments
- **RoundPlanner** (`grocery_bot/planner/`) makes per-round decisions: pickup targets, delivery timing, collision avoidance, idle positioning
- **Oracle knowledge** — games are deterministic per day, so completed order sequences are recorded to `maps/` and loaded on subsequent runs to plan ahead

The bot scales from 1 bot (Easy) up to 20 bots (Nightmare) with team-size-dependent configuration for coordination, delivery queuing, and speculative pre-picking.

## Requirements

- Python 3.11+
- [`websockets`](https://pypi.org/project/websockets/) (runtime dependency)

## Setup

### Using the Devcontainer (recommended)

Open this repo in VS Code or GitHub Codespaces — the devcontainer includes Python 3.13, Bun, and Claude Code CLI pre-installed.

### Manual Setup

```sh
pip install -e .
```

For development tools (pytest, ruff, mypy, bandit):

```sh
pip install -e ".[dev]"
```

### Updating Claude Code CLI

To install the latest version of Claude Code CLI inside the devcontainer:

```sh
bun update -g @anthropic-ai/claude-code
```

If that doesn't pick up the latest, you can also do:

```sh
bun install -g @anthropic-ai/claude-code@latest
```

## Running the Bot

```sh
python bot.py
```

Set the game server URL via the environment or command-line args as required by the competition.

## Testing

```sh
# Fast tests (excludes slow benchmarks)
python -m pytest tests/ -m "not slow"

# Full suite including regression tests
python -m pytest tests/
```

## Benchmarking

```sh
# Replay-based benchmark (uses recorded maps)
python benchmark.py

# Synthetic multi-seed benchmark with diagnostics
python benchmark.py --synthetic --seeds 10 --diagnostics
```

Results are written to `docs/benchmark_results.md`. Use `analyze_replay.py` to inspect individual game logs.

## Linting & Type Checking

```sh
ruff check grocery_bot/
ruff format --check grocery_bot/
mypy grocery_bot/
```

## Project Structure

```
bot.py                  # Entry point: WebSocket loop
benchmark.py            # CLI benchmark runner
analyze_replay.py       # Game log analysis tool

grocery_bot/
├── constants.py        # All tuning parameters
├── pathfinding.py      # BFS variants, direction helpers
├── game_state/         # Persistent state, caching, routing
├── planner/            # Per-round decision engine
└── simulator/          # Local game simulator for testing

tests/                  # pytest suite (unit + integration)
maps/                   # Recorded maps and order sequences
docs/                   # Benchmark results and plans
```
