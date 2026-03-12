"""Hungarian algorithm and bot-to-item assignment for GameState."""

from typing import Any

from grocery_bot.constants import (
    ASSIGNMENT_DROPOFF_WEIGHT,
    HUNGARIAN_MAX_PAIRS,
    LAST_ITEM_BOOST_THRESHOLD,
    LAST_ITEM_COST_MULTIPLIER,
    ZONE_CROSS_PENALTY,
)
from grocery_bot.game_state._base import GameStateBase


class AssignmentMixin(GameStateBase):
    """Mixin providing optimal bot-to-item assignment."""

    def assign_items_to_bots(
        self,
        assignable_bots: list[tuple[int, tuple[int, int], int]],
        candidate_items: list[dict[str, Any]],
        zone_width: float | None = None,
        drop_off: tuple[int, int] | None = None,
    ) -> dict[int, list[dict[str, Any]]]:
        """Assign items to bots optimally using Hungarian algorithm."""
        if not assignable_bots or not candidate_items:
            return {}

        priority_multiplier: float = 1.0
        n_candidates = len(candidate_items)
        if 0 < n_candidates <= LAST_ITEM_BOOST_THRESHOLD and len(assignable_bots) > 1:
            priority_multiplier = LAST_ITEM_COST_MULTIPLIER

        n_bots = len(assignable_bots)
        n_items = len(candidate_items)
        cost_matrix: list[list[float]] = []
        for bi, (_, bot_pos, _) in enumerate(assignable_bots):
            row: list[float] = []
            bot_zone = int(bot_pos[0] / zone_width) if zone_width else 0
            for ii, it in enumerate(candidate_items):
                if drop_off is not None:
                    _, d = self.find_best_item_target_weighted(
                        bot_pos, it, drop_off, ASSIGNMENT_DROPOFF_WEIGHT
                    )
                else:
                    _, d = self.find_best_item_target(bot_pos, it)
                if zone_width:
                    item_zone = int(it["position"][0] / zone_width)
                    d += abs(bot_zone - item_zone) * ZONE_CROSS_PENALTY
                d *= priority_multiplier
                if n_bots > 1 and n_items > 1:
                    d += 0.01 * abs(bi / n_bots - ii / n_items)
                row.append(d)
            cost_matrix.append(row)

        if n_bots * n_items <= HUNGARIAN_MAX_PAIRS:
            pairs = hungarian_solve(cost_matrix)
        else:
            pairs = []
            flat: list[tuple[float, int, int]] = []
            for i, row in enumerate(cost_matrix):
                for j, d in enumerate(row):
                    if d < float("inf"):
                        flat.append((d, i, j))
            flat.sort()
            used_b: set[int] = set()
            used_i: set[int] = set()
            for _d, bi, ii in flat:
                if bi not in used_b and ii not in used_i:
                    pairs.append((bi, ii))
                    used_b.add(bi)
                    used_i.add(ii)

        result: dict[int, list[dict[str, Any]]] = {}
        bot_counts: dict[int, int] = {}
        for bi, ii in sorted(pairs, key=lambda p: cost_matrix[p[0]][p[1]]):
            bot_id, _, slots = assignable_bots[bi]
            if bot_counts.get(bot_id, 0) >= slots:
                continue
            result.setdefault(bot_id, []).append(candidate_items[ii])
            bot_counts[bot_id] = bot_counts.get(bot_id, 0) + 1

        return result

    def hungarian_assign(
        self,
        bot_positions: list[tuple[int, int]],
        item_positions: list[tuple[int, int]],
        dist_fn: Any | None = None,
    ) -> list[tuple[int, int]]:
        """Optimal bot-to-item assignment. Falls back to greedy for >100 pairs."""
        if not bot_positions or not item_positions:
            return []

        if dist_fn is None:
            dist_fn = self.dist_static

        n_bots = len(bot_positions)
        n_items = len(item_positions)

        if n_bots * n_items > HUNGARIAN_MAX_PAIRS:
            return greedy_assign(bot_positions, item_positions, dist_fn)

        cost_matrix: list[list[float]] = []
        for i in range(n_bots):
            row: list[float] = []
            for j in range(n_items):
                row.append(dist_fn(bot_positions[i], item_positions[j]))
            cost_matrix.append(row)

        return hungarian_solve(cost_matrix)


def hungarian_solve(cost_matrix: list[list[float]]) -> list[tuple[int, int]]:
    """Solve assignment problem using Hungarian/Munkres algorithm O(n^3)."""
    if not cost_matrix or not cost_matrix[0]:
        return []

    n_rows = len(cost_matrix)
    n_cols = len(cost_matrix[0])
    n = max(n_rows, n_cols)
    INF = float("inf")

    has_finite = any(val < INF for row in cost_matrix for val in row)
    if not has_finite:
        return []

    max_finite = max((val for row in cost_matrix for val in row if val < INF), default=0)
    pad_val = max_finite * n + 1

    matrix: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if i < n_rows and j < n_cols:
                val = cost_matrix[i][j]
                row.append(pad_val if val == INF else val)
            else:
                row.append(pad_val)
        matrix.append(row)

    u: list[float] = [0.0] * (n + 1)
    v: list[float] = [0.0] * (n + 1)
    p: list[int] = [0] * (n + 1)
    way: list[int] = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        min_v: list[float] = [INF] * (n + 1)
        used: list[bool] = [False] * (n + 1)

        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1

            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = matrix[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < min_v[j]:
                    min_v[j] = cur
                    way[j] = j0
                if min_v[j] < delta:
                    delta = min_v[j]
                    j1 = j

            if j1 == -1:
                break

            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    min_v[j] -= delta

            j0 = j1
            if p[j0] == 0:
                break

        while j0 != 0:
            p[j0] = p[way[j0]]
            j0 = way[j0]

    result: list[tuple[int, int]] = []
    for j in range(1, n + 1):
        row_idx = p[j] - 1
        col_idx = j - 1
        if row_idx < n_rows and col_idx < n_cols and cost_matrix[row_idx][col_idx] < INF:
            result.append((row_idx, col_idx))
    return result


def greedy_assign(
    bot_positions: list[tuple[int, int]],
    item_positions: list[tuple[int, int]],
    dist_fn: Any,
) -> list[tuple[int, int]]:
    """Greedy fallback for large inputs."""
    pairs: list[tuple[float, int, int]] = []
    for i, bp in enumerate(bot_positions):
        for j, ip in enumerate(item_positions):
            d = dist_fn(bp, ip)
            if d < float("inf"):
                pairs.append((d, i, j))
    pairs.sort()

    assigned_bots: set[int] = set()
    assigned_items: set[int] = set()
    result: list[tuple[int, int]] = []
    for _d, bi, ii in pairs:
        if bi in assigned_bots or ii in assigned_items:
            continue
        result.append((bi, ii))
        assigned_bots.add(bi)
        assigned_items.add(ii)
        if len(result) >= min(len(bot_positions), len(item_positions)):
            break
    return result
