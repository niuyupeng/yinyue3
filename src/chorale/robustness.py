from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from typing import Any

from chorale.evaluate import evaluate
from chorale.train import train
from chorale.utils import ensure_dir, load_config, save_config, write_json


METRIC_FIELDS = [
    "pitch_accuracy",
    "cross_entropy",
    "rule_violations_per_100_timesteps",
    "parallel_fifths_per_100_timesteps",
    "parallel_octaves_per_100_timesteps",
    "seventh_resolution_violation_rate",
    "cadence_unknown_rate",
    "musicxml_export_success_rate",
]


def run_multiseed_robustness(
    config_path: str | Path = "configs/chorale_rule_guided_decoding.yaml",
    seeds: list[int] | None = None,
    run_root: str | Path = "runs/project1_multiseed",
    out_csv: str | Path = "results/project1_multiseed_summary.csv",
    out_json: str | Path = "results/project1_robustness_summary.json",
    include_existing_primary: bool = False,
    existing_metrics_path: str | Path = "results/rule_guided_decoding_metrics.json",
    fast_dev_run: bool = False,
    max_eval_batches: int | None = None,
    reuse_existing: bool = True,
) -> dict[str, Any]:
    base_config_path = Path(config_path)
    base_config = load_config(base_config_path)
    seeds = list(seeds or [2027, 2028])
    run_root_path = ensure_dir(run_root)

    rows: list[dict[str, Any]] = []
    if include_existing_primary:
        rows.append(load_existing_primary_record(base_config_path, Path(existing_metrics_path)))

    for seed in seeds:
        run_dir = run_root_path / f"seed_{seed}"
        seed_config = make_seed_config(base_config, seed, run_dir, max_eval_batches)
        seed_config_path = run_dir / "input_config.yaml"
        save_config(seed_config, seed_config_path)
        metrics_path = run_dir / "eval_metrics.json"
        if reuse_existing and (run_dir / "best.pt").is_file() and metrics_path.is_file():
            train_summary = read_train_summary(run_dir)
            metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
        else:
            train_summary = train(seed_config_path, fast_dev_run=fast_dev_run, run_dir_override=str(run_dir))
            metrics = evaluate(
                seed_config_path,
                checkpoint_path=run_dir / "best.pt",
                output_path=metrics_path,
                write_project_outputs=False,
            )
        rows.append(
            build_record(
                seed=seed,
                config_path=seed_config_path,
                run_dir=run_dir,
                metrics=metrics,
                fast_dev_run=fast_dev_run,
                source="trained_multiseed",
                train_summary=train_summary,
            )
        )

    summary = summarize_records(
        rows=rows,
        config_path=base_config_path,
        out_csv=Path(out_csv),
        out_json=Path(out_json),
        fast_dev_run=fast_dev_run,
        max_eval_batches=max_eval_batches,
    )
    write_rows_csv(rows, Path(out_csv))
    write_json(summary, out_json)
    return summary


def make_seed_config(base_config: dict[str, Any], seed: int, run_dir: Path, max_eval_batches: int | None) -> dict[str, Any]:
    config = json.loads(json.dumps(base_config))
    config["seed"] = int(seed)
    config.setdefault("run", {})["name"] = f"{config.get('run', {}).get('name', 'project1')}_seed_{seed}"
    config.setdefault("run", {})["output_dir"] = str(run_dir)
    config.setdefault("eval", {})
    if max_eval_batches is not None:
        config["eval"]["max_batches"] = int(max_eval_batches)
    return config


def load_existing_primary_record(config_path: Path, metrics_path: Path) -> dict[str, Any]:
    config = load_config(config_path)
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    output_dir = config.get("run", {}).get("output_dir")
    run_dir = Path(output_dir) if output_dir else Path(metrics.get("checkpoint", "")).parent
    return build_record(
        seed=int(config.get("seed", 0)),
        config_path=config_path,
        run_dir=run_dir,
        metrics=metrics,
        fast_dev_run=False,
        source="existing_primary_metrics",
        train_summary=read_train_summary(run_dir),
    )


def build_record(
    *,
    seed: int,
    config_path: Path,
    run_dir: Path,
    metrics: dict[str, Any],
    fast_dev_run: bool,
    source: str,
    train_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    train_summary = train_summary or {}
    voice_wise = metrics.get("voice_wise_accuracy") or {}
    return {
        "seed": int(seed),
        "model": metrics.get("model", ""),
        "task": metrics.get("task", ""),
        "rule_guided_decoding": bool(metrics.get("rule_guided_decoding", False)),
        "config_path": str(config_path),
        "run_dir": str(run_dir),
        "checkpoint": str(metrics.get("checkpoint", run_dir / "best.pt")),
        "source": source,
        "fast_dev_run": bool(fast_dev_run),
        "best_epoch": int(train_summary.get("best_epoch", 0) or 0),
        "best_val_loss": float_or_none(train_summary.get("best_val_loss")),
        "device": str(train_summary.get("device", "")),
        "pitch_accuracy": float_or_none(metrics.get("pitch_token_accuracy")),
        "cross_entropy": float_or_none(metrics.get("cross_entropy")),
        "soprano_accuracy": float_or_none(voice_wise.get("soprano")),
        "alto_accuracy": float_or_none(voice_wise.get("alto")),
        "tenor_accuracy": float_or_none(voice_wise.get("tenor")),
        "bass_accuracy": float_or_none(voice_wise.get("bass")),
        "rule_violations_per_100_timesteps": float_or_none(metrics.get("rule_violations_per_100_timesteps")),
        "parallel_fifths_per_100_timesteps": float_or_none(metrics.get("parallel_fifths_per_100_timesteps")),
        "parallel_octaves_per_100_timesteps": float_or_none(metrics.get("parallel_octaves_per_100_timesteps")),
        "seventh_resolution_violation_rate": float_or_none(metrics.get("seventh_resolution_violation_rate")),
        "cadence_unknown_rate": float_or_none(metrics.get("cadence_unknown_rate")),
        "musicxml_export_success_rate": float_or_none(metrics.get("musicxml_export_success_rate")),
        "evaluated_generations": int(float(metrics.get("evaluated_generations", 0) or 0)),
    }


def read_train_summary(run_dir: Path) -> dict[str, Any]:
    metrics_path = run_dir / "metrics.json"
    if not metrics_path.is_file():
        return {}
    try:
        history = json.loads(metrics_path.read_text(encoding="utf-8")).get("history", [])
    except json.JSONDecodeError:
        return {}
    if not history:
        return {}
    best_row = min(history, key=lambda row: float(row.get("val_loss", float("inf"))))
    return {
        "best_epoch": int(best_row.get("epoch", 0)),
        "best_val_loss": float_or_none(best_row.get("val_loss")),
        "device": str(best_row.get("device", "")),
    }


def summarize_records(
    *,
    rows: list[dict[str, Any]],
    config_path: Path,
    out_csv: Path,
    out_json: Path,
    fast_dev_run: bool,
    max_eval_batches: int | None,
) -> dict[str, Any]:
    distinct_seeds = sorted({int(row["seed"]) for row in rows})
    all_full_protocol = all(not bool(row.get("fast_dev_run")) for row in rows) and max_eval_batches is None
    enough_generations = all(int(row.get("evaluated_generations", 0)) >= 37 for row in rows)
    formal = len(distinct_seeds) >= 3 and all_full_protocol and enough_generations
    return {
        "schema": "project1_multiseed_robustness_v1",
        "config_path": str(config_path),
        "config_sha256": sha256_text(Path(config_path).read_text(encoding="utf-8")),
        "out_csv": str(out_csv),
        "out_json": str(out_json),
        "seed_count": len(distinct_seeds),
        "seeds": distinct_seeds,
        "fast_dev_run": bool(fast_dev_run),
        "max_eval_batches": max_eval_batches,
        "formal_robustness_evidence": formal,
        "formal_robustness_rule": "requires at least 3 distinct seeds, non-fast-dev training, full test evaluation, and at least 37 evaluated generations per seed",
        "status": "formal robustness evidence" if formal else "software check only - not publishable robustness evidence",
        "aggregates": aggregate_metrics(rows),
        "rows": rows,
    }


def aggregate_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, float | None]]:
    aggregates: dict[str, dict[str, float | None]] = {}
    for field in METRIC_FIELDS:
        values = [float(row[field]) for row in rows if row.get(field) is not None]
        if not values:
            aggregates[field] = {"mean": None, "std": None, "min": None, "max": None}
            continue
        aggregates[field] = {
            "mean": float(statistics.fmean(values)),
            "std": float(statistics.stdev(values)) if len(values) > 1 else 0.0,
            "min": float(min(values)),
            "max": float(max(values)),
        }
    return aggregates


def write_rows_csv(rows: list[dict[str, Any]], out_csv: Path) -> None:
    ensure_dir(out_csv.parent)
    fieldnames = list(rows[0].keys()) if rows else []
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def float_or_none(value: object) -> float | None:
    try:
        out = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(out):
        return None
    return out


def parse_seed_args(values: list[str]) -> list[int]:
    seeds: list[int] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part:
                seeds.append(int(part))
    return seeds


def main() -> None:
    parser = argparse.ArgumentParser(description="Run and summarize Project1 multi-seed robustness experiments.")
    parser.add_argument("--config", default="configs/chorale_rule_guided_decoding.yaml")
    parser.add_argument("--seeds", nargs="+", default=["2027", "2028"])
    parser.add_argument("--run-root", default="runs/project1_multiseed")
    parser.add_argument("--out-csv", default="results/project1_multiseed_summary.csv")
    parser.add_argument("--out-json", default="results/project1_robustness_summary.json")
    parser.add_argument("--include-existing-primary", action="store_true")
    parser.add_argument("--existing-metrics", default="results/rule_guided_decoding_metrics.json")
    parser.add_argument("--fast-dev-run", action="store_true")
    parser.add_argument("--max-eval-batches", type=int, default=None)
    parser.add_argument("--force-rerun", action="store_true")
    args = parser.parse_args()
    summary = run_multiseed_robustness(
        config_path=args.config,
        seeds=parse_seed_args(args.seeds),
        run_root=args.run_root,
        out_csv=args.out_csv,
        out_json=args.out_json,
        include_existing_primary=args.include_existing_primary,
        existing_metrics_path=args.existing_metrics,
        fast_dev_run=args.fast_dev_run,
        max_eval_batches=args.max_eval_batches,
        reuse_existing=not args.force_rerun,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
