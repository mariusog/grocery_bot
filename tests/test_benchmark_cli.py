"""Tests for benchmark replay-map selection behavior."""

from pathlib import Path

import benchmark


def test_replay_map_files_for_specific_difficulty(tmp_path: Path):
    (tmp_path / "2026-03-07_28x18_10bot.json").write_text("{}")
    (tmp_path / "2026-03-07_22x14_5bot.json").write_text("{}")
    (tmp_path / "README.txt").write_text("ignore")

    result = benchmark._replay_map_files_for_difficulties(
        ["Expert"], map_dir=str(tmp_path)
    )

    assert result == [str(tmp_path / "2026-03-07_28x18_10bot.json")]


def test_replay_map_files_for_all_difficulties_returns_all_json(tmp_path: Path):
    expert = tmp_path / "2026-03-07_28x18_10bot.json"
    hard = tmp_path / "2026-03-07_22x14_5bot.json"
    expert.write_text("{}")
    hard.write_text("{}")

    result = benchmark._replay_map_files_for_difficulties(
        None, map_dir=str(tmp_path)
    )

    assert result == [str(hard), str(expert)]
