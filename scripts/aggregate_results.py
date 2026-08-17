from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chorale.utils import load_config  # noqa: E402


CORE_METRICS = [
    "pitch_accuracy",
    "pitch_token_accuracy",
    "cross_entropy",
    "negative_log_likelihood",
    "soprano_accuracy",
    "alto_accuracy",
    "tenor_accuracy",
    "bass_accuracy",
    "rule_violations_per_100_timesteps",
    "parallel_fifths_per_100_timesteps",
    "parallel_octaves_per_100_timesteps",
    "voice_crossing_rate",
    "spacing_violation_rate",
    "range_violation_rate",
    "voice_range_violation_rate",
    "seventh_resolution_violation_rate",
    "cadence_unknown_rate",
    "cadence_correctness_rate",
    "roman_numeral_extraction_coverage",
    "chord_label_coverage",
    "generated_roman_numeral_coverage",
    "generated_chord_label_coverage",
    "musicxml_export_success_rate",
    "generation_validity_rate",
    "evaluated_generations",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: normalize_cell(row.get(key, "")) for key in fieldnames})


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def normalize_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.12g}"
    return str(value)


def float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_model_family(model: str) -> str:
    lower = model.lower()
    if "cih_s2s" in lower or "constraint-integrated" in lower:
        return "cih_s2s_transformer"
    if "lstm" in lower:
        return "lstm_baseline"
    if "transformer_no_constraints" in lower:
        return "vanilla_transformer"
    if "rule_guided" in lower or "neural_symbolic" in lower:
        return "current_rule_guided_transformer"
    if "rule_baseline" in lower or "rule-only" in lower:
        return "rule_only_baseline"
    return model


def normalize_project_metrics(root: Path) -> list[dict[str, Any]]:
    rows = []
    for row in read_csv(root / "results" / "project1_metrics.csv"):
        model = row.get("model", "")
        out = {
            "source": "results/project1_metrics.csv",
            "model": model,
            "model_family": normalize_model_family(model),
            "task": row.get("task", ""),
            "seed": "",
            "formal_evidence": "false" if "smoke" in model.lower() else "true",
            "evidence_level": "smoke" if "smoke" in model.lower() else "single_seed_aggregate",
        }
        for metric in CORE_METRICS:
            if metric in row:
                out[metric] = row.get(metric, "")
        rows.append(out)
    return rows


def normalize_metrics_json(path: Path, *, source_label: str) -> dict[str, Any] | None:
    data = read_json(path)
    if not data:
        return None
    model = str(data.get("model", path.stem))
    out: dict[str, Any] = {
        "source": str(path),
        "model": model,
        "model_family": normalize_model_family(model),
        "task": data.get("task", ""),
        "seed": "",
        "formal_evidence": "false" if "smoke" in path.name.lower() or "smoke" in model.lower() else "true",
        "evidence_level": source_label,
    }
    if isinstance(data.get("voice_wise_accuracy"), dict):
        for voice, value in data["voice_wise_accuracy"].items():
            out[f"{voice}_accuracy"] = value
    for metric in CORE_METRICS:
        if metric in data:
            out[metric] = data.get(metric)
    if "pitch_token_accuracy" in out and "pitch_accuracy" not in out:
        out["pitch_accuracy"] = out["pitch_token_accuracy"]
    if "voice_range_violation_rate" in out and "range_violation_rate" not in out:
        out["range_violation_rate"] = out["voice_range_violation_rate"]
    return out


def collect_multiseed_rows(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for robustness_path in sorted((root / "results").glob("*robustness_summary.json")):
        robustness = read_json(robustness_path)
        for item in robustness.get("rows", []) if isinstance(robustness.get("rows", []), list) else []:
            if not isinstance(item, dict):
                continue
            model = str(item.get("model", ""))
            key = (model, str(item.get("seed", "")), str(robustness_path))
            if any(
                (str(existing.get("model")), str(existing.get("seed")), str(existing.get("source"))) == key
                for existing in rows
            ):
                continue
            out: dict[str, Any] = {
                "source": str(robustness_path.relative_to(root)),
                "model": model,
                "model_family": normalize_model_family(model),
                "task": item.get("task", ""),
                "seed": item.get("seed", ""),
                "formal_evidence": "false" if item.get("fast_dev_run") else "true",
                "evidence_level": "multiseed_raw",
                "run_dir": item.get("run_dir", ""),
                "config_path": item.get("config_path", ""),
            }
            for metric in CORE_METRICS:
                if metric in item:
                    out[metric] = item.get(metric)
            rows.append(out)
    for csv_path in sorted((root / "results").glob("*multiseed_summary.csv")):
        for row in read_csv(csv_path):
            key = (row.get("model"), row.get("seed"))
            if any((str(existing.get("model")), str(existing.get("seed"))) == key for existing in rows):
                continue
            model = str(row.get("model", ""))
            out = {
                "source": str(csv_path.relative_to(root)),
                "model": model,
                "model_family": normalize_model_family(model),
                "task": row.get("task", ""),
                "seed": row.get("seed", ""),
                "formal_evidence": "false" if str(row.get("fast_dev_run", "")).lower() == "true" else "true",
                "evidence_level": "multiseed_raw",
            }
            for metric in CORE_METRICS:
                if metric in row:
                    out[metric] = row.get(metric)
            rows.append(out)
    return rows


def collect_runs_inventory(root: Path) -> list[dict[str, Any]]:
    rows = []
    for metrics_path in sorted((root / "runs").rglob("metrics.csv")) if (root / "runs").is_dir() else []:
        history = read_csv(metrics_path)
        last = history[-1] if history else {}
        val_losses = [float_or_none(item.get("val_loss")) for item in history]
        val_losses = [value for value in val_losses if value is not None]
        rows.append(
            {
                "run_dir": str(metrics_path.parent.relative_to(root)),
                "metrics_path": str(metrics_path.relative_to(root)),
                "epoch_count": len(history),
                "last_epoch": last.get("epoch", ""),
                "last_train_loss": last.get("train_loss", ""),
                "last_val_loss": last.get("val_loss", ""),
                "best_val_loss": min(val_losses) if val_losses else "",
                "device": last.get("device", ""),
            }
        )
    return rows


def dataset_summary(root: Path, config_path: str = "configs/chorale_main.yaml") -> dict[str, Any]:
    config_file = root / config_path
    if not config_file.is_file():
        return {"status": "missing_config", "config": config_path}
    config = load_config(config_file)
    data_cfg = config.get("data", {})
    processed = root / str(data_cfg.get("processed_path", ""))
    summary: dict[str, Any] = {
        "schema": "project1_dataset_summary_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "config": config_path,
        "processed_path": str(data_cfg.get("processed_path", "")),
        "grid_quarter_length": data_cfg.get("grid_quarter_length"),
        "max_seq_len": data_cfg.get("max_seq_len"),
        "voice_order": ["soprano", "alto", "tenor", "bass"],
        "mask_strategy": {
            "soprano_to_satb": "soprano known, alto/tenor/bass predicted",
            "masked_infill": "Bernoulli token mask using task.mask_prob",
        },
        "status": "missing_dataset",
    }
    if processed.is_file():
        with np.load(processed, allow_pickle=False) as data:
            unique, counts = np.unique(data["splits"].astype(str), return_counts=True)
            summary.update(
                {
                    "status": "available",
                    "tokens_shape": [int(value) for value in data["tokens"].shape],
                    "split_counts": {str(key): int(value) for key, value in zip(unique, counts)},
                    "encoded_scores": int(data["tokens"].shape[0]),
                    "grid_quarter_length_from_dataset": float(np.asarray(data["grid_quarter_length"]).item()),
                    "max_seq_len_from_dataset": int(np.asarray(data["max_seq_len"]).item()),
                    "vocab_size": int(np.asarray(data["vocab_size"]).item()),
                }
            )
    return summary


def make_dataset_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Project1 Dataset Summary",
        "",
        f"Status: `{summary.get('status')}`",
        f"Config: `{summary.get('config')}`",
        f"Processed dataset: `{summary.get('processed_path')}`",
        f"Encoded scores: {summary.get('encoded_scores', 'n/a')}",
        f"Token shape: `{summary.get('tokens_shape', 'n/a')}`",
        f"Split counts: `{summary.get('split_counts', 'n/a')}`",
        f"Grid quarter length: {summary.get('grid_quarter_length_from_dataset', summary.get('grid_quarter_length'))}",
        f"Max sequence length: {summary.get('max_seq_len_from_dataset', summary.get('max_seq_len'))}",
        f"Voice order: {', '.join(summary.get('voice_order', []))}",
        "",
        "The split is deterministic for the configured seed. These counts should be reported exactly in the manuscript.",
        "",
    ]
    return "\n".join(lines)


def aggregate(root: str | Path = ROOT) -> dict[str, str]:
    root = Path(root)
    results_dir = root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    aggregate_rows = normalize_project_metrics(root)
    for path in [
        results_dir / "cih_s2s_smoke_metrics.json",
        results_dir / "hierarchical_score_transformer_smoke_metrics.json",
        results_dir / "bcfb_external_musicxml_pilot_metrics.json",
        results_dir / "bcfb_external_musicxml_rule_baseline_metrics.json",
        results_dir / "cpdl_external_musicxml_expanded_metrics.json",
        results_dir / "cpdl_external_musicxml_expanded_rule_baseline_metrics.json",
        results_dir / "rule_only_bach_metrics.json",
    ]:
        normalized = normalize_metrics_json(path, source_label="json_metrics")
        if normalized is not None and not any(row.get("source") == normalized.get("source") for row in aggregate_rows):
            aggregate_rows.append(normalized)

    multiseed_rows = collect_multiseed_rows(root)
    runs_rows = collect_runs_inventory(root)
    dataset = dataset_summary(root)

    aggregate_fields = [
        "source",
        "model",
        "model_family",
        "task",
        "seed",
        "formal_evidence",
        "evidence_level",
        *CORE_METRICS,
    ]
    write_csv(results_dir / "experiment_results_aggregated.csv", aggregate_rows, aggregate_fields)
    write_csv(results_dir / "experiment_multiseed_raw.csv", multiseed_rows)
    write_csv(results_dir / "runs_metrics_inventory.csv", runs_rows)
    (results_dir / "experiment_dataset_summary.json").write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    (results_dir / "experiment_dataset_summary.md").write_text(make_dataset_markdown(dataset), encoding="utf-8")

    source_dir = root / "paper" / "figures" / "source_data"
    source_dir.mkdir(parents=True, exist_ok=True)
    write_csv(source_dir / "project1_experiment_results_source_data.csv", aggregate_rows, aggregate_fields)
    return {
        "aggregated_csv": "results/experiment_results_aggregated.csv",
        "multiseed_raw_csv": "results/experiment_multiseed_raw.csv",
        "runs_inventory_csv": "results/runs_metrics_inventory.csv",
        "dataset_summary_json": "results/experiment_dataset_summary.json",
        "source_data_csv": "paper/figures/source_data/project1_experiment_results_source_data.csv",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate Project1 SCI experiment outputs without fabricating missing results.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    outputs = aggregate(args.root)
    print(json.dumps(outputs, indent=2))


if __name__ == "__main__":
    main()
