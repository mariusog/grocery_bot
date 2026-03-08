"""Unit tests for coordination module public functions."""

from grocery_bot.planner.coordination import role_to_task_type


class TestRoleToTaskType:
    def test_pick_role(self) -> None:
        assert role_to_task_type("pick") == "pick"

    def test_deliver_role(self) -> None:
        assert role_to_task_type("deliver") == "deliver"

    def test_preview_role(self) -> None:
        assert role_to_task_type("preview") == "preview"

    def test_unknown_role_defaults_to_idle(self) -> None:
        assert role_to_task_type("unknown") == "idle"

    def test_empty_string_defaults_to_idle(self) -> None:
        assert role_to_task_type("") == "idle"

    def test_idle_role(self) -> None:
        """Idle is not in the mapping, so it falls through to default."""
        assert role_to_task_type("idle") == "idle"
