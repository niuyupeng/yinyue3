from __future__ import annotations

import csv
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_table_uses_current_enhanced_primary_row() -> None:
    metrics = read_metrics()
    proposed = metrics["proposed_neural_symbolic_rule_guided_enhanced"]
    table = (ROOT / "paper" / "tables" / "project1_main_results.tex").read_text(
        encoding="utf-8"
    )

    assert "rerankfix" not in table
    assert "Proposed rule-guided Transformer" in table
    assert format4(proposed["pitch_accuracy"]) in table
    assert format4(proposed["cross_entropy"]) in table
    assert format4(proposed["rule_violations_per_100_timesteps"]) in table
    assert format4(proposed["parallel_octaves_per_100_timesteps"]) in table


def test_expert_results_are_not_reported_without_completed_summary() -> None:
    results_section = (ROOT / "paper" / "sections" / "results.tex").read_text(
        encoding="utf-8"
    )
    expert_table = (
        ROOT / "paper" / "tables" / "project1_expert_eval_results.tex"
    ).read_text(encoding="utf-8")

    assert "project1_expert_eval_template" in results_section
    assert "project1_expert_eval_results" not in results_section
    assert "expert evaluation pending" in expert_table
    assert "4.000" not in expert_table


def test_rule_csv_matches_primary_metric_totals() -> None:
    metrics = read_metrics()
    rule_rows = read_rule_rows()
    proposed_rules = [
        row
        for row in rule_rows
        if row["model"] == "proposed_neural_symbolic_rule_guided_enhanced"
    ]
    total = sum(float(row["per_100_timesteps"]) for row in proposed_rules)
    expected = float(
        metrics["proposed_neural_symbolic_rule_guided_enhanced"][
            "rule_violations_per_100_timesteps"
        ]
    )

    assert round(total, 4) == round(expected, 4)
    assert {row["rule"] for row in proposed_rules} == {
        "leading_tone_resolution",
        "melodic_leap_recovery",
        "parallel_octave",
        "seventh_resolution",
    }


def test_figure_source_data_contains_only_plotted_current_rows() -> None:
    metrics_source = (
        ROOT / "paper" / "figures" / "source_data" / "project1_metrics_source_data.csv"
    ).read_text(encoding="utf-8")
    rule_source = (
        ROOT / "paper" / "figures" / "source_data" / "project1_rule_source_data.csv"
    ).read_text(encoding="utf-8")

    assert "rerankfix" not in metrics_source
    assert "rerankfix" not in rule_source
    assert "proposed_neural_symbolic_rule_guided_enhanced" in metrics_source
    assert "proposed_neural_symbolic_rule_guided_enhanced" in rule_source


def read_metrics() -> dict[str, dict[str, str]]:
    with (ROOT / "results" / "project1_metrics.csv").open(
        "r", newline="", encoding="utf-8"
    ) as f:
        return {row["model"]: row for row in csv.DictReader(f)}


def read_rule_rows() -> list[dict[str, str]]:
    with (ROOT / "results" / "project1_rule_violations.csv").open(
        "r", newline="", encoding="utf-8"
    ) as f:
        return list(csv.DictReader(f))


def format4(value: str) -> str:
    return f"{float(value):.4f}"
