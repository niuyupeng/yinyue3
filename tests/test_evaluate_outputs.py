from __future__ import annotations

import csv
from pathlib import Path

from chorale.evaluate import write_project1_outputs


def test_write_project1_outputs_removes_stale_rule_rows(tmp_path: Path) -> None:
    metrics = base_metrics()
    write_project1_outputs(
        metrics,
        {"parallel_fifth": 2, "spacing": 1},
        total_steps=10,
        example_records=[],
        harmony_summary={},
        results_dir=tmp_path / "results",
        paper_tables_dir=tmp_path / "tables",
    )

    write_project1_outputs(
        metrics,
        {"parallel_octave": 3},
        total_steps=10,
        example_records=[],
        harmony_summary={},
        results_dir=tmp_path / "results",
        paper_tables_dir=tmp_path / "tables",
    )

    with (tmp_path / "results" / "project1_rule_violations.csv").open(
        "r", newline="", encoding="utf-8"
    ) as f:
        rows = list(csv.DictReader(f))

    assert [row["rule"] for row in rows] == ["parallel_octave"]
    assert rows[0]["count"] == "3"


def base_metrics() -> dict:
    return {
        "model": "unit_model",
        "task": "soprano_to_satb",
        "rule_guided_decoding": True,
        "checkpoint": "runs/unit/best.pt",
        "pitch_token_accuracy": 0.5,
        "cross_entropy": 1.0,
        "negative_log_likelihood": 1.0,
        "voice_wise_accuracy": {
            "soprano": 0.0,
            "alto": 0.5,
            "tenor": 0.5,
            "bass": 0.5,
        },
        "rule_violations_per_100_timesteps": 30.0,
        "parallel_fifths_per_100_timesteps": 20.0,
        "parallel_octaves_per_100_timesteps": 0.0,
        "seventh_resolution_violation_rate": 0.0,
        "cadence_correctness_rate": None,
        "cadence_unknown_rate": 1.0,
        "roman_numeral_extraction_coverage": 0.0,
        "chord_label_coverage": 0.0,
        "generated_roman_numeral_coverage": 0.0,
        "generated_chord_label_coverage": 0.0,
        "voice_range_violation_rate": 0.0,
        "voice_crossing_rate": 0.0,
        "spacing_violation_rate": 0.0,
        "musicxml_export_success_rate": 1.0,
        "evaluated_generations": 1,
    }
