"""Unit tests for DiagnosticTracker (simulator/diagnostics.py)."""

from grocery_bot.simulator.diagnostics import DiagnosticTracker


class _FakeSim:
    """Minimal simulator stub for DiagnosticTracker tests."""

    def __init__(self, num_bots: int = 2, rnd: int = 0) -> None:
        self.bots = [{"id": i, "position": [1 + i, 1], "inventory": []} for i in range(num_bots)]
        self.round = rnd
        self.score = 0
        self.orders_completed = 0
        self.active_order_idx = 0
        self.orders = [
            {
                "items_required": ["cheese", "milk"],
                "items_delivered": [],
            }
        ]
        self.items_on_map = [
            {"id": "item_0", "type": "cheese"},
            {"id": "item_1", "type": "milk"},
        ]


class TestDiagnosticTrackerInit:
    def test_initializes_counters(self) -> None:
        sim = _FakeSim(num_bots=2)
        tracker = DiagnosticTracker(sim)
        assert tracker.num_bots == 2
        assert tracker.idle_rounds == 0
        assert tracker.stuck_rounds == 0
        assert tracker.oscillation_count == 0
        assert tracker.moves == 0
        assert tracker.waits == 0
        assert tracker.pickups == 0
        assert tracker.delivers == 0

    def test_tracks_per_bot(self) -> None:
        sim = _FakeSim(num_bots=3)
        tracker = DiagnosticTracker(sim)
        assert len(tracker.prev_positions) == 3


class TestPreRound:
    def test_snapshots_positions(self) -> None:
        sim = _FakeSim(num_bots=2)
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        assert tracker._pre_positions == {0: (1, 1), 1: (2, 1)}

    def test_snapshots_inventory_sizes(self) -> None:
        sim = _FakeSim(num_bots=1)
        sim.bots[0]["inventory"] = ["cheese"]
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        assert tracker._pre_inv_sizes[0] == 1

    def test_computes_active_needed(self) -> None:
        sim = _FakeSim(num_bots=1)
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        assert "cheese" in tracker._active_needed
        assert "milk" in tracker._active_needed

    def test_active_needed_subtracts_delivered(self) -> None:
        sim = _FakeSim(num_bots=1)
        sim.orders[0]["items_delivered"] = ["cheese"]
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        assert "cheese" not in tracker._active_needed
        assert "milk" in tracker._active_needed


class TestPostRound:
    def _setup(self, num_bots: int = 2) -> tuple:
        sim = _FakeSim(num_bots=num_bots)
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        return sim, tracker

    def test_counts_move_actions(self) -> None:
        sim, tracker = self._setup(1)
        sim.bots[0]["position"] = [2, 1]
        actions = [{"bot": 0, "action": "move_right"}]
        tracker.post_round(sim, actions)
        assert tracker.moves == 1
        assert tracker.waits == 0

    def test_counts_wait_actions(self) -> None:
        sim, tracker = self._setup(1)
        actions = [{"bot": 0, "action": "wait"}]
        tracker.post_round(sim, actions)
        assert tracker.waits == 1
        assert tracker.idle_rounds == 1

    def test_counts_pickup_useful(self) -> None:
        sim, tracker = self._setup(1)
        actions = [{"bot": 0, "action": "pick_up", "item_id": "item_0"}]
        tracker.post_round(sim, actions)
        assert tracker.pickups == 1
        assert tracker.useful_pickups == 1
        assert tracker.wasted_pickups == 0

    def test_counts_pickup_wasted(self) -> None:
        sim, tracker = self._setup(1)
        # Pick up an item not in the active needed set
        sim.items_on_map.append({"id": "item_99", "type": "bread"})
        tracker.pre_round(sim)
        actions = [{"bot": 0, "action": "pick_up", "item_id": "item_99"}]
        tracker.post_round(sim, actions)
        assert tracker.wasted_pickups == 1

    def test_counts_dropoff_action(self) -> None:
        sim, tracker = self._setup(1)
        actions = [{"bot": 0, "action": "drop_off"}]
        tracker.post_round(sim, actions)
        assert tracker.delivers == 1

    def test_detects_stuck_bot(self) -> None:
        sim, tracker = self._setup(1)
        # Bot tried to move but position didn't change
        actions = [{"bot": 0, "action": "move_right"}]
        # Position stays the same (blocked)
        tracker.post_round(sim, actions)
        assert tracker.stuck_rounds == 1

    def test_detects_oscillation(self) -> None:
        sim, tracker = self._setup(1)
        # Round 1: bot at (1,1) moves to (2,1)
        sim.bots[0]["position"] = [2, 1]
        actions = [{"bot": 0, "action": "move_right"}]
        tracker.post_round(sim, actions)
        # Round 2: bot at (2,1) moves back to (1,1)
        tracker.pre_round(sim)
        sim.bots[0]["position"] = [1, 1]
        actions = [{"bot": 0, "action": "move_left"}]
        tracker.post_round(sim, actions)
        # Round 3: bot at (1,1) moves to (2,1) again -> oscillation
        tracker.pre_round(sim)
        sim.bots[0]["position"] = [2, 1]
        actions = [{"bot": 0, "action": "move_right"}]
        tracker.post_round(sim, actions)
        assert tracker.oscillation_count == 1

    def test_tracks_delivery_gap(self) -> None:
        sim, tracker = self._setup(1)
        # Round 0: no score
        actions = [{"bot": 0, "action": "wait"}]
        tracker.post_round(sim, actions)
        # Round 1: score increases
        sim.round = 5
        sim.score = 1
        tracker.pre_round(sim)
        tracker.post_round(sim, actions)
        assert tracker.last_delivery_round == 5
        assert tracker.max_delivery_gap == 5

    def test_tracks_order_completion(self) -> None:
        sim, tracker = self._setup(1)
        actions = [{"bot": 0, "action": "wait"}]
        sim.orders_completed = 1
        sim.round = 10
        tracker.post_round(sim, actions)
        assert len(tracker.rounds_per_order) == 1

    def test_inv_full_waits(self) -> None:
        sim, tracker = self._setup(1)
        sim.bots[0]["inventory"] = ["a", "b", "c"]
        tracker.pre_round(sim)
        actions = [{"bot": 0, "action": "wait"}]
        tracker.post_round(sim, actions)
        assert tracker.inv_full_waits == 1


class TestGetResults:
    def test_returns_expected_keys(self) -> None:
        sim = _FakeSim(num_bots=1)
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        tracker.post_round(sim, [{"bot": 0, "action": "wait"}])
        results = tracker.get_results()
        expected_keys = {
            "idle_rounds",
            "stuck_rounds",
            "max_delivery_gap",
            "oscillation_count",
            "avg_bots_idle",
            "total_bot_rounds",
            "moves",
            "waits",
            "pickups",
            "delivers",
            "useful_pickups",
            "wasted_pickups",
            "pickup_waste_pct",
            "inv_full_waits",
            "avg_rounds_per_order",
            "pickup_delivery_ratio",
            "per_bot_idle",
            "blocked_move_pct",
            "avg_delivery_size",
            "order_completion_rounds",
            "per_bot_actions",
        }
        assert set(results.keys()) == expected_keys

    def test_pickup_waste_pct_zero_when_no_pickups(self) -> None:
        sim = _FakeSim(num_bots=1)
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        tracker.post_round(sim, [{"bot": 0, "action": "wait"}])
        results = tracker.get_results()
        assert results["pickup_waste_pct"] == 0.0

    def test_total_bot_rounds_calculation(self) -> None:
        sim = _FakeSim(num_bots=2)
        tracker = DiagnosticTracker(sim)
        tracker.pre_round(sim)
        actions = [{"bot": 0, "action": "wait"}, {"bot": 1, "action": "wait"}]
        tracker.post_round(sim, actions)
        results = tracker.get_results()
        # 1 round * 2 bots = 2
        assert results["total_bot_rounds"] == 2

    def test_avg_rounds_per_order_zero_when_none(self) -> None:
        sim = _FakeSim(num_bots=1)
        tracker = DiagnosticTracker(sim)
        results = tracker.get_results()
        assert results["avg_rounds_per_order"] == 0.0
