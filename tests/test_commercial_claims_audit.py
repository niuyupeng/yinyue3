from __future__ import annotations

from pathlib import Path

from chorale.commercial_claims_audit import build_claims_audit


def test_claims_audit_allows_boundary_and_warning_language(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "README.md").write_text(
        "This is a score-level SATB system, not neural audio generation.\n"
        "Do not claim commercial release ready until expert and legal evidence exists.\n",
        encoding="utf-8",
    )
    (docs / "checklist.md").write_text(
        "禁止表述：世界顶级音乐生成。\n"
        "本包不是真人合唱录音，也不是神经音频生成。\n",
        encoding="utf-8",
    )

    audit = build_claims_audit(tmp_path)

    assert audit["all_pass"] is True
    assert audit["violation_count"] == 0


def test_claims_audit_blocks_unsupported_positive_claim(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "Project1 is commercial release ready and provides world-class human vocal realism.\n",
        encoding="utf-8",
    )

    audit = build_claims_audit(tmp_path)

    assert audit["all_pass"] is False
    labels = {item["label"] for item in audit["findings"]}
    assert "final_commercial_release_claim" in labels
    assert "human_choral_audio_or_vocal_realism" in labels


def test_claims_audit_allows_prohibited_examples_under_heading(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(
        "## 禁止表述\n\n"
        "在专家评分和法务签核完成前，不得对外写：\n\n"
        "- 已商用发布\n"
        "- 世界顶级音乐生成\n"
        "- 真人合唱音频生成\n",
        encoding="utf-8",
    )

    audit = build_claims_audit(tmp_path)

    assert audit["all_pass"] is True
    assert audit["violation_count"] == 0
