from __future__ import annotations

from pathlib import Path

import yaml
from music21 import duration, note, stream

from chorale.data.build_dataset import build_dataset_from_scores
from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.evaluate_rule_baseline import evaluate_rule_baseline


def test_rule_baseline_evaluation_writes_metrics(tmp_path: Path) -> None:
    data_path = tmp_path / "tiny.npz"
    tokenizer = ScoreTokenizer(max_seq_len=16)
    scores = [(f"tiny_{idx}", make_score(offset=idx)) for idx in range(6)]
    build_dataset_from_scores(scores, data_path, tokenizer, seed=7)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "seed": 7,
                "experiment": {"label": "unit_external"},
                "data": {"processed_path": str(data_path)},
                "task": {"name": "soprano_to_satb", "mask_prob": 0.45},
                "run": {"output_dir": str(tmp_path / "run")},
                "eval": {"export_samples": 1},
            }
        ),
        encoding="utf-8",
    )
    output_path = tmp_path / "metrics.json"

    metrics = evaluate_rule_baseline(config_path, output_path)

    assert output_path.exists()
    assert metrics["model"] == "unit_external_rule_baseline"
    assert metrics["evaluated_generations"] >= 1
    assert 0.0 <= metrics["pitch_token_accuracy"] <= 1.0
    assert metrics["musicxml_export_success_rate"] == 1.0


def make_score(offset: int = 0) -> stream.Score:
    score = stream.Score()
    pitches = {
        "Soprano": ["C5", "D5", "E5", "F5"],
        "Alto": ["G4", "A4", "G4", "A4"],
        "Tenor": ["E3", "F3", "G3", "A3"],
        "Bass": ["C3", "D3", "C3", "F2"],
    }
    for part_name, pitch_names in pitches.items():
        part = stream.Part(id=f"{part_name}_{offset}")
        part.partName = part_name
        for pitch_name in pitch_names:
            n = note.Note(pitch_name)
            n.duration = duration.Duration(1.0)
            part.append(n)
        score.append(part)
    return score
