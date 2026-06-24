from __future__ import annotations

from pathlib import Path

from chorale.delivery_package_docs import write_delivery_readme
from chorale.delivery_player_static_audit import BAD_TEXT_PATTERNS


def test_delivery_docs_are_clean_score_level_chinese(tmp_path: Path) -> None:
    write_delivery_readme(tmp_path, master_package="master_package_for_test")

    expected = [
        "DELIVERY_README_CN.md",
        "COMMERCIAL_PLAYBACK_README_CN.md",
        "README_CN.md",
        "README_FOR_EXPERTS.md",
        "START_HERE_CN.md",
        "START_HERE_CN.html",
    ]
    for rel in expected:
        path = tmp_path / rel
        text = path.read_text(encoding="utf-8")
        assert "SATB" in text or "score-level" in text or "乐谱" in text
        assert "神经音频生成" in text or "not an audio-generation" in text or "not audio-generation" in text
        assert not any(pattern in text for pattern in BAD_TEXT_PATTERNS), rel
