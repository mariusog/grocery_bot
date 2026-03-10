"""Unit tests for map_generator (simulator/map_generator.py)."""

import random

from grocery_bot.simulator.map_generator import (
    ITEM_TYPE_NAMES,
    generate_orders,
    generate_store_layout,
)


class TestGenerateStoreLayout:
    def test_returns_four_element_tuple(self) -> None:
        walls, shelf_pos, item_shelves, names = generate_store_layout(12, 10, 4)
        assert isinstance(walls, list)
        assert isinstance(shelf_pos, set)
        assert isinstance(item_shelves, list)
        assert isinstance(names, list)

    def test_border_walls_present(self) -> None:
        walls, _, _, _ = generate_store_layout(12, 10, 4)
        wall_set = set(walls)
        # Top and bottom borders
        for x in range(12):
            assert (x, 0) in wall_set
            assert (x, 9) in wall_set
        # Left and right borders
        for y in range(1, 9):
            assert (0, y) in wall_set
            assert (11, y) in wall_set

    def test_item_types_limited(self) -> None:
        _, _, _, names = generate_store_layout(12, 10, 4)
        assert len(names) == 4
        assert all(n in ITEM_TYPE_NAMES for n in names)

    def test_shelf_positions_match_item_shelves(self) -> None:
        _, shelf_pos, item_shelves, _ = generate_store_layout(12, 10, 4)
        for x, y, _ in item_shelves:
            assert (x, y) in shelf_pos

    def test_shelves_not_on_walls(self) -> None:
        walls, _, item_shelves, _ = generate_store_layout(12, 10, 4)
        wall_set = set(walls)
        for x, y, _ in item_shelves:
            assert (x, y) not in wall_set

    def test_shelves_within_bounds(self) -> None:
        width, height = 12, 10
        _, _, item_shelves, _ = generate_store_layout(width, height, 4)
        for x, y, _ in item_shelves:
            assert 0 <= x < width
            assert 0 <= y < height

    def test_large_map_has_more_aisles(self) -> None:
        _, _, shelves_small, _ = generate_store_layout(12, 10, 4)
        _, _, shelves_large, _ = generate_store_layout(22, 10, 4)
        assert len(shelves_large) > len(shelves_small)

    def test_all_item_types_placed(self) -> None:
        _, _, item_shelves, names = generate_store_layout(12, 10, 4)
        placed_types = {itype for _, _, itype in item_shelves}
        for name in names:
            assert name in placed_types

    def test_sixteen_item_types(self) -> None:
        _, _, _, names = generate_store_layout(12, 10, 16)
        assert len(names) == 16
        assert names == ITEM_TYPE_NAMES


class TestGenerateOrders:
    def test_returns_correct_count(self) -> None:
        rng = random.Random(42)
        orders = generate_orders(rng, ["cheese", "milk"], (2, 3), count=10)
        assert len(orders) == 10

    def test_order_has_required_keys(self) -> None:
        rng = random.Random(42)
        orders = generate_orders(rng, ["cheese", "milk"], (2, 3), count=1)
        order = orders[0]
        assert "id" in order
        assert "items_required" in order
        assert "items_delivered" in order
        assert "complete" in order

    def test_order_starts_incomplete(self) -> None:
        rng = random.Random(42)
        orders = generate_orders(rng, ["cheese", "milk"], (2, 3), count=5)
        for o in orders:
            assert o["complete"] is False
            assert o["items_delivered"] == []

    def test_items_within_range(self) -> None:
        rng = random.Random(42)
        orders = generate_orders(rng, ["cheese", "milk", "bread"], (2, 4), count=20)
        for o in orders:
            assert 2 <= len(o["items_required"]) <= 4

    def test_items_from_provided_types(self) -> None:
        rng = random.Random(42)
        types = ["cheese", "milk"]
        orders = generate_orders(rng, types, (2, 3), count=10)
        for o in orders:
            for item in o["items_required"]:
                assert item in types

    def test_unique_order_ids(self) -> None:
        rng = random.Random(42)
        orders = generate_orders(rng, ["cheese"], (1, 2), count=50)
        ids = [o["id"] for o in orders]
        assert len(ids) == len(set(ids))

    def test_deterministic_with_same_seed(self) -> None:
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        types = ["cheese", "milk", "bread"]
        orders1 = generate_orders(rng1, types, (2, 3), count=10)
        orders2 = generate_orders(rng2, types, (2, 3), count=10)
        for o1, o2 in zip(orders1, orders2, strict=True):
            assert o1["items_required"] == o2["items_required"]
