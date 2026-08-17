from __future__ import annotations

from pathlib import Path

import yaml

from chorale.robustness import build_record, summarize_records


def test_multiseed_summary_marks_three_full_seeds_as_formal(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    rows = [
        make_row(seed=2026, fast_dev=False, generations=37),
        make_row(seed=2027, fast_dev=False, generations=37),
        make_row(seed=2028, fast_dev=False, generations=37),
    ]

    summary = summarize_records(
        rows=rows,
        config_path=config_path,
        out_csv=tmp_path / "results" / "project1_multiseed_summary.csv",
        out_json=tmp_path / "results" / "project1_robustness_summary.json",
        fast_dev_run=False,
        max_eval_batches=None,
    )

    assert summary["formal_robustness_evidence"] is True
    assert summary["seed_count"] == 3
    assert summary["aggregates"]["pitch_accuracy"]["mean"] == 0.82


def test_multiseed_summary_keeps_fast_dev_as_software_check(tmp_path: Path) -> None:
    config_path = write_config(tmp_path)
    rows = [
        make_row(seed=2026, fast_dev=True, generations=3),
        make_row(seed=2027, fast_dev=True, generations=3),
        make_row(seed=2028, fast_dev=True, generations=3),
    ]

    summary = summarize_records(
        rows=rows,
        config_path=config_path,
        out_csv=tmp_path / "results" / "project1_multiseed_summary.csv",
        out_json=tmp_path / "results" / "project1_robustness_summary.json",
        fast_dev_run=True,
        max_eval_batches=3,
    )

    assert summary["formal_robustness_evidence"] is False
    assert "software check only" in summary["status"]


def make_row(seed: int, fast_dev: bool, generations: int) -> dict[str, object]:
    return build_record(
        seed=seed,
        config_path=Path(f"config_seed_{seed}.yaml"),
        run_dir=Path(f"runs/seed_{seed}"),
        metrics={
            "model": "proposed_neural_symbolic_rule_guided_enhanced",
            "task": "soprano_to_satb",
            "rule_guided_decoding": True,
            "checkpoint": f"runs/seed_{seed}/best.pt",
            "pitch_token_accuracy": 0.82,
            "cross_entropy": 0.59,
            "voice_wise_accuracy": {"soprano": 0.0, "alto": 0.83, "tenor": 0.81, "bass": 0.82},
            "rule_violations_per_100_timesteps": 4.0,
            "parallel_fifths_per_100_timesteps": 0.0,
            "parallel_octaves_per_100_timesteps": 0.08,
            "seventh_resolution_violation_rate": 0.01,
            "cadence_unknown_rate": 0.4,
            "musicxml_export_success_rate": 1.0,
            "evaluated_generations": generations,
        },
        fast_dev_run=fast_dev,
        source="fixture",
        train_summary={"best_epoch": 12, "best_val_loss": 0.5, "device": "cuda"},
    )


def write_config(root: Path) -> Path:
    path = root / "config.yaml"
    path.write_text(yaml.safe_dump({"seed": 2026, "run": {"output_dir": "runs/base"}}), encoding="utf-8")
    return path
