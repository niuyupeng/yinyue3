from __future__ import annotations

from pathlib import Path

from chorale.harmonization_quality import evaluate_harmonization_quality


def test_quality_gate_passes_low_violation_score(tmp_path: Path) -> None:
    summary = make_summary(tmp_path, violations_per_100=4.0, total_violations=3, total_penalty=2.5)

    quality = evaluate_harmonization_quality(summary)

    assert quality["status"] == "pass"
    assert quality["issues"] == []
    assert quality["score"] > 80.0


def test_quality_gate_marks_high_violation_score_for_review(tmp_path: Path) -> None:
    summary = make_summary(tmp_path, violations_per_100=25.0, total_violations=40, total_penalty=33.0)

    quality = evaluate_harmonization_quality(summary)

    assert quality["status"] == "needs_review"
    assert any("violations_per_100_timesteps" in item for item in quality["issues"])
    assert any("total_violations" in item for item in quality["issues"])
    assert any("total_penalty" in item for item in quality["issues"])


def test_quality_gate_fails_when_required_output_is_missing(tmp_path: Path) -> None:
    summary = make_summary(tmp_path, violations_per_100=1.0, total_violations=1, total_penalty=1.0)
    Path(summary["outputs"]["harmonized_musicxml"]).unlink()

    quality = evaluate_harmonization_quality(summary)

    assert quality["status"] == "failed"
    assert any("not found" in item for item in quality["issues"])
    assert quality["score"] == 0.0


def test_quality_gate_can_require_audio(tmp_path: Path) -> None:
    summary = make_summary(tmp_path, violations_per_100=1.0, total_violations=1, total_penalty=1.0)
    summary["audio"] = {"requested": False}

    quality = evaluate_harmonization_quality(summary, require_audio=True)

    assert quality["status"] == "needs_review"
    assert any("required WAV audio" in item for item in quality["issues"])


def test_quality_gate_fails_if_known_voice_is_not_preserved(tmp_path: Path) -> None:
    summary = make_summary(tmp_path, violations_per_100=1.0, total_violations=1, total_penalty=1.0)
    summary["known_voice_preservation"] = {"pass": False, "mismatches": 2}

    quality = evaluate_harmonization_quality(summary)

    assert quality["status"] == "failed"
    assert any("known input voice preservation failed" in item for item in quality["issues"])


def test_quality_gate_fails_if_export_is_not_satb(tmp_path: Path) -> None:
    summary = make_summary(tmp_path, violations_per_100=1.0, total_violations=1, total_penalty=1.0)
    summary["score_validation"] = {"parse_ok": True, "part_count": 3, "has_notes": True}

    quality = evaluate_harmonization_quality(summary)

    assert quality["status"] == "failed"
    assert any("expected 4 SATB parts" in item for item in quality["issues"])


def make_summary(
    tmp_path: Path,
    *,
    violations_per_100: float,
    total_violations: int,
    total_penalty: float,
) -> dict:
    musicxml = tmp_path / "score.musicxml"
    report = tmp_path / "report.json"
    musicxml.write_text("<score-partwise version=\"3.1\" />", encoding="utf-8")
    report.write_text("{}", encoding="utf-8")
    return {
        "outputs": {
            "harmonized_musicxml": str(musicxml),
            "rule_report_json": str(report),
        },
        "rule_summary": {
            "total_penalty": total_penalty,
            "total_violations": total_violations,
            "violations_per_100_timesteps": violations_per_100,
            "seventh_resolution_violations": 0,
            "cadence_type": "AUTHENTIC_LIKE",
        },
        "audio": {"requested": False},
    }
