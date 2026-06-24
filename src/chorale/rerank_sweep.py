from __future__ import annotations

import argparse
import copy
import csv
import time
from pathlib import Path
from typing import Any

import torch

from chorale.evaluate import evaluate
from chorale.utils import ensure_dir, load_config, save_config, write_json


DEFAULT_GRID = [
    {"name": "old_vertical_only", "rule": 1.0, "harmony": 0.25, "temporal": 0.0, "seventh": 0.0, "top_k": 4},
    {"name": "balanced_t1_s1", "rule": 1.0, "harmony": 0.10, "temporal": 1.0, "seventh": 1.0, "top_k": 4},
    {"name": "temporal2_seventh2", "rule": 1.0, "harmony": 0.10, "temporal": 2.0, "seventh": 2.0, "top_k": 4},
    {"name": "temporal3_seventh2", "rule": 0.8, "harmony": 0.05, "temporal": 3.0, "seventh": 2.0, "top_k": 4},
    {"name": "temporal4_seventh3", "rule": 0.6, "harmony": 0.00, "temporal": 4.0, "seventh": 3.0, "top_k": 4},
]


def run_sweep(
    base_config_path: str | Path,
    checkpoint_path: str | Path,
    output_csv: str | Path = "results/project1_rerank_sweep_latest.csv",
    output_json: str | Path = "results/project1_rerank_sweep_latest.json",
    max_batches: int | None = None,
    export_samples: int = 0,
    limit: int | None = None,
    require_cuda: bool = False,
) -> dict[str, Any]:
    if require_cuda and not torch.cuda.is_available():
        raise RuntimeError("CUDA is required for this reranking sweep, but torch.cuda.is_available() is False.")

    base_config = load_config(base_config_path)
    checkpoint_path = Path(checkpoint_path)
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_path}")

    stamp = time.strftime("%Y%m%d_%H%M%S")
    sweep_dir = ensure_dir(Path("runs") / f"rerank_sweep_{stamp}")
    config_dir = ensure_dir(sweep_dir / "configs")
    output_dir = ensure_dir(sweep_dir / "metrics")

    grid = DEFAULT_GRID[: limit if limit is not None else None]
    rows: list[dict[str, Any]] = []
    metrics_by_trial: dict[str, dict[str, Any]] = {}

    for trial in grid:
        trial_name = str(trial["name"])
        trial_config = copy.deepcopy(base_config)
        trial_config.setdefault("experiment", {})["label"] = f"rerank_sweep_{trial_name}"
        trial_config.setdefault("run", {})["name"] = f"rerank_sweep_{trial_name}"
        trial_config["run"]["output_dir"] = str(sweep_dir / trial_name)
        trial_config.setdefault("eval", {})["export_samples"] = int(export_samples)
        if max_batches is not None:
            trial_config["eval"]["max_batches"] = int(max_batches)
        constraints = trial_config.setdefault("constraints", {})
        constraints["use_rule_guided_decoding"] = True
        constraints["use_constraint_reranking"] = True
        constraints["rerank_top_k"] = int(trial["top_k"])
        constraints["rerank_rule_weight"] = float(trial["rule"])
        constraints["rerank_harmony_weight"] = float(trial["harmony"])
        constraints["rerank_temporal_weight"] = float(trial["temporal"])
        constraints["rerank_seventh_weight"] = float(trial["seventh"])

        config_path = config_dir / f"{trial_name}.yaml"
        metrics_path = output_dir / f"{trial_name}.json"
        save_config(trial_config, config_path)
        metrics = evaluate(config_path, checkpoint_path=checkpoint_path, output_path=metrics_path)
        metrics_by_trial[trial_name] = metrics

        row = {
            "trial": trial_name,
            "config": str(config_path),
            "checkpoint": str(checkpoint_path),
            "rerank_top_k": int(trial["top_k"]),
            "rerank_rule_weight": float(trial["rule"]),
            "rerank_harmony_weight": float(trial["harmony"]),
            "rerank_temporal_weight": float(trial["temporal"]),
            "rerank_seventh_weight": float(trial["seventh"]),
            "pitch_accuracy": metrics["pitch_token_accuracy"],
            "cross_entropy": metrics["cross_entropy"],
            "rule_violations_per_100_timesteps": metrics["rule_violations_per_100_timesteps"],
            "parallel_fifths_per_100_timesteps": metrics["parallel_fifths_per_100_timesteps"],
            "parallel_octaves_per_100_timesteps": metrics["parallel_octaves_per_100_timesteps"],
            "seventh_resolution_violation_rate": metrics["seventh_resolution_violation_rate"],
            "voice_crossing_rate": metrics["voice_crossing_rate"],
            "spacing_violation_rate": metrics["spacing_violation_rate"],
            "musicxml_export_success_rate": metrics["musicxml_export_success_rate"],
        }
        row["constraint_stability_score"] = (
            float(row["rule_violations_per_100_timesteps"])
            + float(row["parallel_fifths_per_100_timesteps"])
            + float(row["parallel_octaves_per_100_timesteps"])
            + 100.0 * float(row["seventh_resolution_violation_rate"])
        )
        rows.append(row)

    best = min(
        rows,
        key=lambda item: (
            float(item["constraint_stability_score"]),
            float(item["rule_violations_per_100_timesteps"]),
            -float(item["pitch_accuracy"]),
        ),
    )
    write_rows_csv(output_csv, rows)
    write_json(
        {
            "base_config": str(base_config_path),
            "checkpoint": str(checkpoint_path),
            "sweep_dir": str(sweep_dir),
            "selection_rule": "minimize constraint_stability_score, then rule violations, then maximize pitch accuracy",
            "best_trial": best,
            "trials": rows,
            "metrics": metrics_by_trial,
        },
        output_json,
    )
    return {"best_trial": best, "trials": rows, "sweep_dir": str(sweep_dir)}


def write_rows_csv(path: str | Path, rows: list[dict[str, Any]]) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a small rule-guided reranking weight sweep without retraining.")
    parser.add_argument("--base-config", default="configs/chorale_rule_guided_decoding.yaml")
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--output-csv", default="results/project1_rerank_sweep_latest.csv")
    parser.add_argument("--output-json", default="results/project1_rerank_sweep_latest.json")
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--export-samples", type=int, default=0)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--require-cuda", action="store_true")
    args = parser.parse_args()
    result = run_sweep(
        base_config_path=args.base_config,
        checkpoint_path=args.checkpoint,
        output_csv=args.output_csv,
        output_json=args.output_json,
        max_batches=args.max_batches,
        export_samples=args.export_samples,
        limit=args.limit,
        require_cuda=args.require_cuda,
    )
    print(result)


if __name__ == "__main__":
    main()
