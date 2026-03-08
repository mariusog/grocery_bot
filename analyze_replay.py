"""Text-based replay analyzer for AI agent debugging.

Usage:
    python analyze_replay.py <log>                  # Summary + problems
    python analyze_replay.py <log> --grid 50        # ASCII grid at round 50
    python analyze_replay.py <log> --rounds 40-60   # Actions in round range
    python analyze_replay.py <log> --bot 3          # Bot 3 timeline
    python analyze_replay.py <log> --problems       # Only detected problems
    python analyze_replay.py --list                 # List available logs

Log path can be a basename, full path, or path without extension.
"""

import argparse
import csv
import json
import os
import sys
from collections import defaultdict
from typing import Any

LOGS_DIR = "logs"


def list_logs() -> None:
    """List available log files with summary info."""
    if not os.path.isdir(LOGS_DIR):
        print("No logs directory found.")
        return
    basenames = set()
    for f in os.listdir(LOGS_DIR):
        if f.endswith(".csv"):
            base = f[:-4]
            if os.path.exists(os.path.join(LOGS_DIR, base + ".json")):
                basenames.add(base)
    for name in sorted(basenames):
        with open(os.path.join(LOGS_DIR, name + ".json")) as jf:
            meta = json.load(jf)
        r = meta.get("result", {})
        g = meta["grid"]
        print(
            f"  {name}  score={r.get('score', '?'):>4}  "
            f"bots={meta.get('bots', '?')}  grid={g['width']}x{g['height']}"
        )


def load_log(path: str) -> tuple[dict[int, list[dict]], dict]:
    """Load CSV + JSON log pair. Returns (rounds_data, meta)."""
    base = path
    for ext in (".csv", ".json"):
        if base.endswith(ext):
            base = base[: -len(ext)]
    csv_path = base + ".csv"
    json_path = base + ".json"
    if not os.path.exists(csv_path):
        csv_path = os.path.join(LOGS_DIR, os.path.basename(base) + ".csv")
        json_path = os.path.join(LOGS_DIR, os.path.basename(base) + ".json")
    if not os.path.exists(csv_path):
        print(f"CSV not found: {csv_path}")
        sys.exit(1)

    rounds_data: dict[int, list[dict]] = defaultdict(list)
    with open(csv_path) as f:
        for row in csv.DictReader(f):
            rounds_data[int(row["round"])].append(row)

    meta: dict[str, Any] = {}
    if os.path.exists(json_path):
        with open(json_path) as f:
            meta = json.load(f)
    return dict(rounds_data), meta


def render_grid(meta: dict, round_data: list[dict]) -> str:
    """Render ASCII grid at a specific round."""
    w, h = meta["grid"]["width"], meta["grid"]["height"]
    walls = {tuple(p) for p in meta["grid"].get("wall_positions", [])}
    shelves = {
        (it["position"][0], it["position"][1])
        for it in meta.get("item_positions", [])
    }
    dropoff = tuple(meta["drop_off"])
    bots: dict[int, tuple[int, int]] = {}
    for row in round_data:
        x, y = row["bot_pos"].split(",")
        bots[int(row["bot_id"])] = (int(x), int(y))

    lines = []
    hdr = "".join(str(x % 10) for x in range(w))
    lines.append(f"   {hdr}")
    for y in range(h):
        row_chars = []
        for x in range(w):
            here = [b for b, p in bots.items() if p == (x, y)]
            if here:
                c = str(here[0]) if here[0] < 10 else chr(55 + here[0])
                row_chars.append(c if len(here) == 1 else "*")
            elif (x, y) == dropoff:
                row_chars.append("D")
            elif (x, y) in shelves:
                row_chars.append("i")
            elif (x, y) in walls:
                row_chars.append("#")
            else:
                row_chars.append(".")
        lines.append(f"{y:>2} {''.join(row_chars)}")
    lines.append(f"   {''.join(str(x % 10) for x in range(w))}")

    score = round_data[0]["score"]
    needed = round_data[0].get("active_needed", "")
    order = round_data[0].get("order_idx", "?")
    lines.append(f"   Score={score} Order={order} Needed=[{needed}]")
    for row in round_data:
        inv = row.get("inventory", "")
        bid = row["bot_id"]
        lines.append(f"   B{bid} @{row['bot_pos']} inv=[{inv}] -> {row['action']}")
    return "\n".join(lines)


def print_summary(meta: dict, rounds_data: dict[int, list[dict]]) -> None:
    """Print compact game summary with per-bot stats."""
    r = meta.get("result", {})
    g = meta["grid"]
    total_rounds = r.get("rounds_used", max(rounds_data) + 1 if rounds_data else 0)
    print(
        f"Game: {meta.get('difficulty', '?')} | Grid: {g['width']}x{g['height']} | "
        f"Bots: {meta.get('bots', '?')} | Rounds: {total_rounds}"
    )
    print(
        f"Score: {r.get('score', '?')} | Items: {r.get('items_delivered', '?')} | "
        f"Orders: {r.get('orders_completed', '?')}"
    )
    diag = meta.get("diagnostics", {})
    if not diag:
        return
    print(
        f"\n  Moves={diag['moves']} Waits={diag['waits']} "
        f"Picks={diag['pickups']} Delivers={diag['delivers']}"
    )
    print(
        f"  Waste={diag.get('pickup_waste_pct', 0):.1f}% "
        f"InvFull={diag.get('inv_full_waits', 0)} "
        f"MaxGap={diag.get('max_delivery_gap', 0)}rds "
        f"AvgDel={diag.get('avg_delivery_size', 0):.2f} "
        f"Blocked={diag.get('blocked_move_pct', 0):.1f}%"
    )
    pba = diag.get("per_bot_actions", {})
    if pba:
        print(f"\n  {'Bot':>5} {'Moves':>6} {'Picks':>5} {'Deliv':>5} {'Idle':>5} {'Stuck':>5} {'Util%':>5}")
        for bid in sorted(pba, key=lambda x: int(x)):
            v = pba[bid]
            util = (v["moves"] + v["pickups"] + v["delivers"]) / max(1, total_rounds) * 100
            print(
                f"  B{bid:<4} {v['moves']:>6} {v['pickups']:>5} {v['delivers']:>5} "
                f"{v['idle']:>5} {v['stuck']:>5} {util:>4.0f}%"
            )
    ocr = diag.get("order_completion_rounds", [])
    if ocr:
        parts = [f"O{i + 1}@R{r}" for i, r in enumerate(ocr[:12])]
        suffix = f" +{len(ocr) - 12} more" if len(ocr) > 12 else ""
        print(f"\n  Orders: {' -> '.join(parts)}{suffix}")


def _inv_count(row: dict) -> int:
    """Extract inventory count, handling missing items_carried field."""
    ic = row.get("items_carried", "")
    if ic != "":
        return int(ic)
    inv = row.get("inventory", "")
    return len(inv.split(";")) if inv else 0


def detect_problems(rounds_data: dict[int, list[dict]], meta: dict) -> None:
    """Auto-detect scoring problems sorted by severity."""
    problems: list[tuple[int, str]] = []
    bot_acts: dict[int, list[tuple]] = defaultdict(list)
    prev_score = 0
    last_score_rnd = 0
    total = max(rounds_data) + 1 if rounds_data else 0

    for rnd in sorted(rounds_data):
        for row in rounds_data[rnd]:
            bid = int(row["bot_id"])
            bot_acts[bid].append((rnd, row["action"], row["bot_pos"], _inv_count(row)))
        score = int(rounds_data[rnd][0]["score"])
        if score > prev_score:
            gap = rnd - last_score_rnd
            if gap >= 20:
                problems.append((gap, f"No scoring for {gap} rounds (R{last_score_rnd}-R{rnd})"))
            last_score_rnd = rnd
        prev_score = score
    if total - last_score_rnd >= 20:
        problems.append((total - last_score_rnd, f"No scoring in final {total - last_score_rnd} rounds"))

    for bid in sorted(bot_acts):
        acts = bot_acts[bid]
        # Idle streaks
        streak = streak_start = 0
        for rnd, act, _, _ in acts:
            if act == "wait":
                if streak == 0:
                    streak_start = rnd
                streak += 1
            else:
                if streak >= 10:
                    problems.append((streak, f"Bot {bid} idle {streak} rounds (R{streak_start}-R{streak_start + streak - 1})"))
                streak = 0
        if streak >= 10:
            problems.append((streak, f"Bot {bid} idle {streak} rounds (R{streak_start}-end)"))
        # Oscillation
        osc = osc_start = 0
        for i in range(2, len(acts)):
            if acts[i][2] == acts[i - 2][2] and acts[i][2] != acts[i - 1][2]:
                if osc == 0:
                    osc_start = acts[i][0]
                osc += 1
            else:
                if osc >= 5:
                    problems.append((osc, f"Bot {bid} oscillating {osc} rounds from R{osc_start}"))
                osc = 0
        if osc >= 5:
            problems.append((osc, f"Bot {bid} oscillating {osc} rounds from R{osc_start}"))
        # Full-inv waits and zero-pickup bots
        full_waits = sum(1 for _, a, _, ic in acts if a == "wait" and ic >= 3)
        if full_waits >= 5:
            problems.append((full_waits, f"Bot {bid} waited {full_waits} rounds with full inventory"))
        picks = sum(1 for _, a, _, _ in acts if a == "pick_up")
        if picks == 0 and len(acts) > 50:
            problems.append((len(acts), f"Bot {bid} never picked up anything ({len(acts)} rounds)"))

    problems.sort(key=lambda x: x[0], reverse=True)
    if problems:
        print(f"\nDetected {len(problems)} problems:")
        for sev, desc in problems[:20]:
            print(f"  [{sev:>3}] {desc}")
    else:
        print("\nNo significant problems detected.")


def print_rounds(
    rounds_data: dict[int, list[dict]], start: int, end: int, bot_id: int | None = None,
) -> None:
    """Print action detail for a round range."""
    for rnd in range(start, end + 1):
        if rnd not in rounds_data:
            continue
        rows = rounds_data[rnd]
        if bot_id is not None:
            rows = [r for r in rows if int(r["bot_id"]) == bot_id]
        if not rows:
            continue
        needed = rows[0].get("active_needed", "")
        print(f"R{rnd:>3} score={rows[0]['score']} order={rows[0].get('order_idx', '?')} needed=[{needed}]")
        for r in rows:
            act = r["action"]
            if r.get("item_id"):
                act += f"({r['item_id']})"
            dist = r.get("dist_to_dropoff", "?")
            print(f"  B{r['bot_id']} @{r['bot_pos']} inv=[{r.get('inventory', '')}] d={dist} -> {act}")


def print_bot_timeline(rounds_data: dict[int, list[dict]], bot_id: int) -> None:
    """Print condensed action timeline for one bot."""
    prev_act: str | None = None
    streak = streak_start = 0
    print(f"Bot {bot_id} timeline:")
    for rnd in sorted(rounds_data):
        for row in rounds_data[rnd]:
            if int(row["bot_id"]) != bot_id:
                continue
            act = row["action"]
            if act in ("pick_up", "drop_off"):
                if prev_act and streak > 1:
                    print(f"  R{streak_start}-R{rnd - 1}: {prev_act} x{streak}")
                detail = row.get("item_id", "") if act == "pick_up" else ""
                print(f"  R{rnd}: {act}({detail}) @{row['bot_pos']} inv=[{row.get('inventory', '')}]")
                prev_act = None
                streak = 0
            elif act != prev_act:
                if prev_act and streak > 1:
                    print(f"  R{streak_start}-R{rnd - 1}: {prev_act} x{streak}")
                elif prev_act:
                    print(f"  R{streak_start}: {prev_act} @{row['bot_pos']}")
                prev_act = act
                streak = 1
                streak_start = rnd
            else:
                streak += 1
    if prev_act and streak > 1:
        print(f"  R{streak_start}-R{max(rounds_data)}: {prev_act} x{streak}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Text-based replay analyzer for AI agent debugging",
    )
    parser.add_argument("log", nargs="?", help="Log path or basename")
    parser.add_argument("--list", action="store_true", help="List available logs")
    parser.add_argument("--grid", type=int, metavar="N", help="ASCII grid at round N")
    parser.add_argument("--rounds", metavar="N-M", help="Actions for rounds N to M")
    parser.add_argument("--bot", type=int, metavar="ID", help="Bot timeline")
    parser.add_argument("--problems", action="store_true", help="Only problems")
    parser.add_argument("--summary", action="store_true", help="Only summary")
    args = parser.parse_args()

    if args.list:
        list_logs()
        sys.exit(0)
    if not args.log:
        parser.print_help()
        sys.exit(1)

    rdata, meta = load_log(args.log)

    if args.grid is not None:
        if args.grid in rdata:
            print(render_grid(meta, rdata[args.grid]))
        else:
            print(f"Round {args.grid} not found (available: {min(rdata)}-{max(rdata)})")
    elif args.rounds:
        parts = args.rounds.split("-")
        s, e = int(parts[0]), int(parts[-1])
        print_rounds(rdata, s, e, bot_id=args.bot)
    elif args.bot is not None:
        print_bot_timeline(rdata, args.bot)
    elif args.problems:
        detect_problems(rdata, meta)
    elif args.summary:
        print_summary(meta, rdata)
    else:
        print_summary(meta, rdata)
        detect_problems(rdata, meta)
        print("\nDrill down: --grid <round>, --bot <id>, --rounds N-M")
