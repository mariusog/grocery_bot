"""Generate ASCII map visualizations for all recorded maps in maps/."""

import glob
import json
import sys
from pathlib import Path

LEGEND = """Legend: # wall  S shelf  D drop-off  * spawn  . floor"""


def render_map(map_path: str) -> str:
    """Render a recorded map JSON as an ASCII grid."""
    with open(map_path) as f:
        data = json.load(f)

    grid_info = data["grid"]
    w, h = grid_info["width"], grid_info["height"]
    walls = {(c[0], c[1]) for c in grid_info.get("walls", [])}
    shelves = {(it["position"][0], it["position"][1]) for it in data["items"]}
    drop_off = set()
    if data.get("drop_off_zones"):
        for dz in data["drop_off_zones"]:
            drop_off.add((dz[0], dz[1]))
    elif data.get("drop_off"):
        drop_off.add((data["drop_off"][0], data["drop_off"][1]))
    spawn = None
    if data.get("spawn"):
        spawn = (data["spawn"][0], data["spawn"][1])

    # Count items per type
    type_counts: dict[str, int] = {}
    for it in data["items"]:
        t = it["type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    # Header
    name = Path(map_path).stem
    lines = [
        f"Map: {name}",
        f"Size: {w}x{h}  Bots: {data.get('num_bots', '?')}  "
        f"Rounds: {data.get('max_rounds', '?')}  "
        f"Orders: {data.get('total_orders', len(data.get('orders', [])))}",
        f"Spawn: {data.get('spawn')}  Drop-off: {list(drop_off)}",
        f"Items: {len(data['items'])} ({len(type_counts)} types: "
        + ", ".join(f"{t}={c}" for t, c in sorted(type_counts.items()))
        + ")",
        "",
        # Column numbers
        "    " + "".join(f"{x % 10}" for x in range(w)),
    ]

    for y in range(h):
        row = f"{y:2d}  "
        for x in range(w):
            if (x, y) in walls:
                row += "#"
            elif spawn and (x, y) == spawn:
                row += "*"
            elif (x, y) in drop_off:
                row += "D"
            elif (x, y) in shelves:
                row += "S"
            else:
                row += "."
        lines.append(row)

    lines.append("")
    lines.append(LEGEND)
    return "\n".join(lines)


def main() -> None:
    map_files = sorted(glob.glob("maps/*.json"))
    if not map_files:
        print("No map files found in maps/")
        sys.exit(1)

    output_dir = Path("maps")

    all_maps: list[str] = []
    for map_path in map_files:
        ascii_map = render_map(map_path)
        all_maps.append(ascii_map)

        # Save individual file next to the JSON
        stem = Path(map_path).stem
        out_path = output_dir / f"{stem}.txt"
        out_path.write_text(ascii_map + "\n")
        print(f"Generated: {out_path}")

    # Save combined file
    combined = output_dir / "all_maps.txt"
    combined.write_text("\n\n" + "=" * 60 + "\n\n".join(
        [""] + all_maps
    ) + "\n")
    print(f"\nCombined: {combined} ({len(map_files)} maps)")


if __name__ == "__main__":
    main()
