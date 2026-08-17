from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml

from chorale.external_dataset_summary import build_external_dataset_summary, claim_boundary_for_source, write_outputs


def test_external_dataset_summary_writes_json_csv_and_md(tmp_path: Path) -> None:
    dataset = tmp_path / "external.npz"
    np.savez_compressed(
        dataset,
        tokens=np.zeros((3, 8, 4), dtype=np.int64),
        splits=np.array(["train", "val", "test"]),
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"data": {"processed_path": str(dataset), "max_seq_len": 8}}),
        encoding="utf-8",
    )
    subset = write_json(tmp_path / "subset.json", {"source_name": "BCFB", "source_doi": "doi", "selected_top_level_musicxml_count": 3})
    intake = write_json(
        tmp_path / "intake.json",
        {"intake_ready": True, "file_count_scanned": 3, "parse_ok_count": 3, "satb_candidate_count": 3, "encoded_count": 3, "issues": []},
    )
    model = write_json(
        tmp_path / "model.json",
        {"model": "pilot", "task": "soprano_to_satb", "evaluated_generations": 1, "pitch_token_accuracy": 0.5},
    )
    baseline = write_json(
        tmp_path / "baseline.json",
        {"model": "baseline", "task": "soprano_to_satb", "evaluated_generations": 1, "pitch_token_accuracy": 0.4},
    )

    summary = build_external_dataset_summary(
        config_path=config,
        subset_json=subset,
        intake_json=intake,
        model_metrics_json=model,
        baseline_metrics_json=baseline,
    )
    out_json = tmp_path / "summary.json"
    write_outputs(summary, out_json)

    assert out_json.exists()
    assert out_json.with_suffix(".csv").exists()
    assert out_json.with_suffix(".md").exists()
    assert summary["dataset"]["split_counts"] == {"test": 1, "train": 1, "val": 1}
    assert "external-repertory" in out_json.with_suffix(".md").read_text(encoding="utf-8")


def test_external_dataset_summary_supports_cpdl_subset_count(tmp_path: Path) -> None:
    dataset = tmp_path / "external.npz"
    np.savez_compressed(
        dataset,
        tokens=np.zeros((2, 8, 4), dtype=np.int64),
        splits=np.array(["train", "test"]),
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        yaml.safe_dump({"data": {"processed_path": str(dataset), "max_seq_len": 8}}),
        encoding="utf-8",
    )
    subset = write_json(
        tmp_path / "subset.json",
        {
            "source_name": "Choral Public Domain Library (CPDL)",
            "source_license": "mixed",
            "selected_mxl_count": 20,
        },
    )
    intake = write_json(
        tmp_path / "intake.json",
        {"intake_ready": True, "file_count_scanned": 20, "parse_ok_count": 20, "satb_candidate_count": 13, "encoded_count": 13, "issues": []},
    )
    model = write_json(tmp_path / "model.json", {"model": "pilot", "evaluated_generations": 1})
    baseline = write_json(tmp_path / "baseline.json", {"model": "baseline", "evaluated_generations": 1})

    summary = build_external_dataset_summary(
        config_path=config,
        subset_json=subset,
        intake_json=intake,
        model_metrics_json=model,
        baseline_metrics_json=baseline,
    )

    assert summary["source"]["selected_musicxml_count"] == 20
    assert "CPDL" in summary["claim_boundary"][0]


def test_claim_boundary_keeps_bcfb_and_cpdl_distinct() -> None:
    assert "Bach chorale material" in claim_boundary_for_source("Bach Chorales Figured Bass (BCFB) dataset")[0]
    assert "representative CPDL coverage" in claim_boundary_for_source("Choral Public Domain Library (CPDL)")[2]


def write_json(path: Path, data: dict) -> Path:
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
