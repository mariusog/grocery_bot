"""Map layout and order generation for the grocery bot simulator."""

import random

ITEM_TYPE_NAMES = [
    "milk", "cheese", "bread", "yogurt", "butter", "eggs",
    "pasta", "juice", "rice", "flour", "sugar", "salt",
    "oil", "vinegar", "honey", "tea",
]


def generate_store_layout(width, height, num_item_types):
    """Generate a store layout with border walls, vertical aisles, and shelves.

    Returns:
        (walls, shelf_positions, item_shelves, item_type_names)
        where item_shelves is a list of (x, y, type) tuples.
    """
    item_type_names = ITEM_TYPE_NAMES[:num_item_types]
    walls = []
    shelf_positions = set()
    item_shelves = []

    # Border walls
    for x in range(width):
        walls.append((x, 0))
        walls.append((x, height - 1))
    for y in range(1, height - 1):
        walls.append((0, y))
        walls.append((width - 1, y))

    wall_set = set(walls)

    # Aisle configuration based on map size
    if width <= 12:
        aisle_starts = [3, 7]
    elif width <= 16:
        aisle_starts = [3, 7, 11]
    elif width <= 22:
        aisle_starts = [3, 7, 11, 16]
    else:
        aisle_starts = [3, 7, 11, 16, 21]

    shelf_cols = []
    for ax in aisle_starts:
        shelf_cols.append(ax)
        shelf_cols.append(ax + 2)

    corridor_rows = {1, height - 2}
    mid = height // 2
    corridor_rows.add(mid)
    if height > 10:
        corridor_rows.add(mid - 1)

    shelf_rows = [y for y in range(2, height - 2) if y not in corridor_rows]

    # Place shelves and items
    type_idx = 0
    for col in shelf_cols:
        for row in shelf_rows:
            if col < width - 1 and (col, row) not in wall_set:
                itype = item_type_names[type_idx % len(item_type_names)]
                item_shelves.append((col, row, itype))
                shelf_positions.add((col, row))
                type_idx += 1

    # Internal walls: mid-aisle barriers
    for ax in aisle_starts:
        for cap_col in [ax, ax + 2]:
            for crow in corridor_rows:
                if crow <= 1 or crow >= height - 2:
                    continue
                if (cap_col, crow) not in wall_set and (
                    cap_col, crow
                ) not in shelf_positions:
                    walls.append((cap_col, crow))
                    wall_set.add((cap_col, crow))

    return walls, shelf_positions, item_shelves, item_type_names


def generate_orders(rng, item_type_names, items_per_order, count=50):
    """Generate random orders using available item types.

    Returns:
        list of order dicts with id, items_required, items_delivered, complete.
    """
    orders = []
    lo, hi = items_per_order
    for i in range(count):
        num_items = rng.randint(lo, hi)
        items = [rng.choice(item_type_names) for _ in range(num_items)]
        orders.append({
            "id": f"order_{i}",
            "items_required": items,
            "items_delivered": [],
            "complete": False,
        })
    return orders
