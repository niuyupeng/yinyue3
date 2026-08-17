from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from chorale.utils import ensure_dir, load_config, write_json


def build_external_dataset_summary(
    *,
    config_path: str | Path,
    subset_json: str | Path,
    intake_json: str | Path,
    model_metrics_json: str | Path,
    baseline_metrics_json: str | Path,
) -> dict[str, Any]:
    config_path = Path(config_path)
    config = load_config(config_path)
    dataset_path = Path(config["data"]["processed_path"])
    split_counts = dataset_split_counts(dataset_path)
    subset = load_json(subset_json)
    intake = load_json(intake_json)
    model_metrics = load_json(model_metrics_json)
    baseline_metrics = load_json(baseline_metrics_json)
    metrics = [
        compact_metrics("pilot_transformer", model_metrics),
        compact_metrics("rule_baseline", baseline_metrics),
    ]
    selected_count = subset.get("selected_top_level_musicxml_count", subset.get("selected_mxl_count"))
    source_name = subset.get("source_name")
    return {
        "schema": "project1_external_dataset_summary_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": "pilot_complete",
        "config": str(config_path),
        "dataset_path": str(dataset_path),
        "source": {
            "name": source_name,
            "doi": subset.get("source_doi"),
            "license": subset.get("source_license"),
            "record_url": subset.get("source_record_url"),
            "archive_md5": subset.get("archive_md5"),
            "selected_musicxml_count": selected_count,
        },
        "intake": {
            "intake_ready": bool(intake.get("intake_ready")),
            "file_count_scanned": int(intake.get("file_count_scanned", 0)),
            "parse_ok_count": int(intake.get("parse_ok_count", 0)),
            "satb_candidate_count": int(intake.get("satb_candidate_count", 0)),
            "encoded_count": int(intake.get("encoded_count", 0)),
            "issues": intake.get("issues", []),
        },
        "dataset": {
            "tokens_shape": list(split_counts["tokens_shape"]),
            "split_counts": split_counts["split_counts"],
            "max_seq_len": int(config["data"].get("max_seq_len", 0)),
        },
        "metrics": metrics,
        "claim_boundary": claim_boundary_for_source(str(source_name or "")),
    }


def dataset_split_counts(dataset_path: Path) -> dict[str, Any]:
    with np.load(dataset_path, allow_pickle=False) as data:
        unique, counts = np.unique(data["splits"].astype(str), return_counts=True)
        return {
            "tokens_shape": tuple(int(x) for x in data["tokens"].shape),
            "split_counts": {str(key): int(value) for key, value in zip(unique, counts)},
        }


def compact_metrics(label: str, metrics: dict[str, Any]) -> dict[str, Any]:
    return {
        "label": label,
        "model": metrics.get("model"),
        "task": metrics.get("task"),
        "evaluated_generations": int(metrics.get("evaluated_generations", 0)),
        "pitch_token_accuracy": metrics.get("pitch_token_accuracy"),
        "cross_entropy": metrics.get("cross_entropy"),
        "rule_violations_per_100_timesteps": metrics.get("rule_violations_per_100_timesteps"),
        "parallel_octaves_per_100_timesteps": metrics.get("parallel_octaves_per_100_timesteps"),
        "musicxml_export_success_rate": metrics.get("musicxml_export_success_rate"),
        "generation_validity_rate": metrics.get("generation_validity_rate"),
    }


def claim_boundary_for_source(source_name: str) -> list[str]:
    normalized = source_name.lower()
    if "bcfb" in normalized or "bach" in normalized:
        return [
            "This is a BCFB external MusicXML source pilot using Bach chorale material.",
            "It supports that the pipeline can ingest, train, evaluate, baseline, and export MusicXML on this selected external source.",
            "It must not be cited as external-repertory generalization, expert preference, or final SCI robustness evidence.",
        ]
    if "cpdl" in normalized or "choral public domain library" in normalized:
        return [
            "This is a CPDL score-level SATB MusicXML/MXL candidate-source pilot using a small automatically selected subset.",
            "It supports that the pipeline can ingest, train, evaluate, baseline, and export MusicXML on the selected CPDL files.",
            "It must not be cited as representative CPDL coverage, final external-corpus robustness, expert preference, or license-cleared publication evidence without additional curation and review.",
        ]
    return [
        "This is an external MusicXML source pilot on a selected source subset.",
        "It supports that the pipeline can ingest, train, evaluate, baseline, and export MusicXML on this selected external source.",
        "It must not be cited as final external-corpus robustness, expert preference, or license-cleared publication evidence without additional curation and review.",
    ]


def load_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}")
    return data


def write_outputs(summary: dict[str, Any], out_json: str | Path) -> None:
    out_json = Path(out_json)
    ensure_dir(out_json.parent)
    write_json(summary, out_json)
    out_json.with_suffix(".csv").write_text(make_csv(summary), encoding="utf-8")
    out_json.with_suffix(".md").write_text(make_markdown(summary), encoding="utf-8")


def make_csv(summary: dict[str, Any]) -> str:
    from io import StringIO

    buffer = StringIO()
    fieldnames = [
        "label",
        "model",
        "task",
        "evaluated_generations",
        "pitch_token_accuracy",
        "cross_entropy",
        "rule_violations_per_100_timesteps",
        "parallel_octaves_per_100_timesteps",
        "musicxml_export_success_rate",
        "generation_validity_rate",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for row in summary.get("metrics", []):
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def make_markdown(summary: dict[str, Any]) -> str:
    source = summary.get("source", {})
    intake = summary.get("intake", {})
    dataset = summary.get("dataset", {})
    lines = [
        "# Project1 External Dataset Pilot Summary",
        "",
        f"Status: `{summary.get('status')}`",
        f"Source: {source.get('name')} ({source.get('doi')})",
        f"Selected MusicXML files: {source.get('selected_musicxml_count')}",
        f"Intake ready: {intake.get('intake_ready')}",
        f"Parsed / encoded: {intake.get('parse_ok_count')} / {intake.get('encoded_count')}",
        f"Dataset shape: `{dataset.get('tokens_shape')}`",
        f"Split counts: `{dataset.get('split_counts')}`",
        "",
        "## Metrics",
        "",
        "| Label | Pitch accuracy | Cross entropy | Rule flags / 100 | Parallel octaves / 100 | MusicXML export | Evaluated |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in summary.get("metrics", []):
        lines.append(
            f"| {row.get('label')} | {fmt(row.get('pitch_token_accuracy'))} | "
            f"{fmt(row.get('cross_entropy'))} | {fmt(row.get('rule_violations_per_100_timesteps'))} | "
            f"{fmt(row.get('parallel_octaves_per_100_timesteps'))} | "
            f"{fmt(row.get('musicxml_export_success_rate'))} | {row.get('evaluated_generations')} |"
        )
    lines.extend(["", "## Claim Boundary", ""])
    lines.extend(f"- {item}" for item in summary.get("claim_boundary", []))
    return "\n".join(lines) + "\n"


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (float, int)):
        return f"{float(value):.4f}"
    return str(value)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Project1 external dataset pilot summary files.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--subset-json", required=True)
    parser.add_argument("--intake-json", required=True)
    parser.add_argument("--model-metrics-json", required=True)
    parser.add_argument("--baseline-metrics-json", required=True)
    parser.add_argument("--out-json", default="results/project1_external_dataset_summary_latest.json")
    args = parser.parse_args()
    summary = build_external_dataset_summary(
        config_path=args.config,
        subset_json=args.subset_json,
        intake_json=args.intake_json,
        model_metrics_json=args.model_metrics_json,
        baseline_metrics_json=args.baseline_metrics_json,
    )
    write_outputs(summary, args.out_json)
    print(json.dumps(summary, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
