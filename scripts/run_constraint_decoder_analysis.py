from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from torch.utils.data import DataLoader

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from chorale.constraint_decoding.constrained_beam import apply_cih_constrained_beam_search  # noqa: E402
from chorale.data.build_dataset import build_dataset_from_config  # noqa: E402
from chorale.data.chorale_dataset import ChoraleDataset  # noqa: E402
from chorale.decoding import decode_predictions  # noqa: E402
from chorale.theory.explain_report import build_explanation_report  # noqa: E402
from chorale.theory.roman_numeral import annotate_tokens_harmony  # noqa: E402
from chorale.theory.rule_guided_decoding import apply_rule_guided_decoding  # noqa: E402
from chorale.train import batch_to_device, build_model  # noqa: E402
from chorale.utils import ensure_dir, get_device, load_config, safe_torch_load, write_json  # noqa: E402


@dataclass(frozen=True)
class DecoderVariant:
    variant_id: str
    label: str
    decoder_type: str
    beam_size: int = 0
    top_k: int = 0
    max_row_candidates: int = 0
    lambda_rule: float = 1.0
    hard_constraints: list[str] | None = None
    soft_constraint_weights: dict[str, float] | None = None


def default_variants(config: dict[str, Any]) -> list[DecoderVariant]:
    decoder_cfg = config.get("constraint_decoder", {}) or {}
    hard = list(decoder_cfg.get("hard_constraints", []))
    soft = dict(decoder_cfg.get("soft_constraint_weights", {}))
    return [
        DecoderVariant("neural_argmax", "Neural argmax", "none"),
        DecoderVariant("local_rule_repair", "Local repair", "local_rule_repair"),
        DecoderVariant(
            "beam_b2_k4",
            "Beam b=2, k=4",
            "cih_beam",
            beam_size=2,
            top_k=4,
            max_row_candidates=24,
            hard_constraints=hard,
            soft_constraint_weights=soft,
        ),
        DecoderVariant(
            "beam_b4_k8",
            "Beam b=4, k=8",
            "cih_beam",
            beam_size=4,
            top_k=8,
            max_row_candidates=48,
            hard_constraints=hard,
            soft_constraint_weights=soft,
        ),
        DecoderVariant(
            "beam_b8_k12",
            "Beam b=8, k=12",
            "cih_beam",
            beam_size=int(decoder_cfg.get("beam_size", 8)),
            top_k=int(decoder_cfg.get("top_k", 12)),
            max_row_candidates=int(decoder_cfg.get("max_row_candidates", 96)),
            hard_constraints=hard,
            soft_constraint_weights=soft,
        ),
    ]


@torch.no_grad()
def run_analysis(
    config_path: str | Path,
    checkpoint_path: str | Path,
    out_csv: str | Path,
    out_json: str | Path,
    *,
    max_batches: int | None = None,
    export_samples: int = 0,
    export_dir: str | Path = "generated_scores/constraint_decoder_analysis",
) -> dict[str, Any]:
    config_path = Path(config_path)
    checkpoint_path = Path(checkpoint_path)
    out_csv = Path(out_csv)
    out_json = Path(out_json)
    config = load_config(config_path)
    data_path = Path(config["data"]["processed_path"])
    if not data_path.exists():
        build_dataset_from_config(config)

    task_cfg = config.get("task", {})
    eval_cfg = config.get("eval", {})
    ds = ChoraleDataset(
        data_path,
        split="test",
        task=task_cfg.get("name", "soprano_to_satb"),
        mask_prob=task_cfg.get("mask_prob", 0.45),
        seed=int(config.get("seed", 1234)) + 2,
    )
    loader = DataLoader(ds, batch_size=int(eval_cfg.get("batch_size", 4)), shuffle=False, num_workers=0)
    device = get_device(config.get("device"))
    checkpoint = safe_torch_load(checkpoint_path, map_location=device)
    model_config = checkpoint.get("config", config)
    model = build_model(model_config, vocab_size=int(checkpoint["vocab_size"])).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()

    decoding_cfg = config.get("decoding", {}) or {}
    refinement_steps = int(decoding_cfg.get("refinement_steps", 1)) if bool(decoding_cfg.get("iterative_refinement", False)) else 1
    variants = default_variants(config)
    records: list[dict[str, Any]] = []
    export_root = ensure_dir(export_dir)
    exported = 0

    for batch_idx, batch in enumerate(loader):
        if max_batches is not None and batch_idx >= max_batches:
            break
        batch_dev = batch_to_device(batch, device)
        pred, decode_logits = decode_predictions(
            model,
            batch_dev,
            mask_token=ds.tokenizer.MASK,
            refinement_steps=refinement_steps,
            refinement_strategy=str(decoding_cfg.get("refinement_strategy", "confidence")),
            remask_fraction=float(decoding_cfg.get("remask_fraction", 0.35)),
        )
        pred_cpu = pred.detach().cpu()
        logits_cpu = decode_logits.detach().cpu()
        tokens_cpu = batch["tokens"].clone()
        target_mask_cpu = batch["target_mask"]
        for item_idx in range(pred_cpu.shape[0]):
            length = int(batch["length"][item_idx].item())
            source_idx = int(batch["source_index"][item_idx].item()) if "source_index" in batch else item_idx
            source_harmony = ds.get_harmonic_labels(source_idx, length=length)
            base = tokens_cpu[item_idx].numpy()
            mask_np = target_mask_cpu[item_idx].numpy()
            base[mask_np] = pred_cpu[item_idx].numpy()[mask_np]
            base = ds.tokenizer.sanitize_for_export(base, length=length)
            for variant in variants:
                start = time.perf_counter()
                decoded = apply_variant(
                    variant,
                    base,
                    logits_cpu[item_idx],
                    mask_np,
                    ds,
                    source_harmony,
                    length,
                )
                runtime = time.perf_counter() - start
                generated_harmony = annotate_tokens_harmony(
                    decoded,
                    ds.tokenizer,
                    length=length,
                    key_label=source_harmony.get("key_label", "UNKNOWN"),
                    key_tonic_pc=int(source_harmony.get("key_tonic_pc", 0)),
                    measure_indices=batch["measure_indices"][item_idx].numpy(),
                    beat_positions=batch["beat_positions"][item_idx].numpy(),
                )
                report = build_explanation_report(
                    decoded,
                    ds.tokenizer,
                    length=length,
                    title=str(batch["name"][item_idx]),
                    key_tonic_pc=int(generated_harmony["key_tonic_pc"]),
                    harmonic_labels=generated_harmony,
                )
                row = {
                    "source_file": str(out_csv),
                    "config_path": str(config_path),
                    "checkpoint": str(checkpoint_path),
                    "seed": int(config.get("seed", 0)),
                    "source_index": source_idx,
                    "source_name": str(batch["name"][item_idx]),
                    "task": task_cfg.get("name", "soprano_to_satb"),
                    "variant_id": variant.variant_id,
                    "variant_label": variant.label,
                    "decoder_type": variant.decoder_type,
                    "beam_size": variant.beam_size,
                    "top_k": variant.top_k,
                    "max_row_candidates": variant.max_row_candidates,
                    "lambda_rule": variant.lambda_rule,
                    "length": length,
                    "runtime_seconds": runtime,
                    "total_violations": int(report["total_violations"]),
                    "rule_violations_per_100_timesteps": float(report["violations_per_100_timesteps"]),
                    "parallel_fifths_per_100_timesteps": per_100(report, "parallel_fifth", length),
                    "parallel_octaves_per_100_timesteps": per_100(report, "parallel_octave", length),
                    "voice_crossing_per_100_timesteps": per_100(report, "voice_crossing", length),
                    "spacing_per_100_timesteps": per_100(report, "spacing", length),
                    "seventh_resolution_violation_rate": float(report["seventh_resolution_violation_rate"]),
                    "cadence_unknown_rate": float(report["cadence_unknown_rate"]),
                    "claim_boundary": "full-test decoder analysis for a trained CIH checkpoint; automatic rule diagnostics only",
                }
                records.append(row)
                if export_samples > 0 and exported < export_samples and variant.variant_id in {"local_rule_repair", "beam_b8_k12"}:
                    exported += 1
                    from chorale.export_musicxml import export_tokens_to_musicxml

                    export_tokens_to_musicxml(
                        decoded,
                        ds.tokenizer,
                        export_root / f"decoder_analysis_{exported:02d}_{variant.variant_id}.musicxml",
                        length=length,
                        title=f"Constraint decoder analysis {variant.label}",
                    )

    summary_rows = summarize(records)
    write_csv(out_csv, records)
    write_json(
        {
            "schema": "constraint_decoder_analysis_v1",
            "config_path": str(config_path),
            "checkpoint": str(checkpoint_path),
            "formal_full_test": max_batches is None,
            "variant_count": len(variants),
            "score_count": len({row["source_index"] for row in records}),
            "rows": summary_rows,
        },
        out_json,
    )
    write_csv(out_csv.with_name(out_csv.stem + "_summary.csv"), summary_rows)
    return {"out_csv": str(out_csv), "out_json": str(out_json), "summary_rows": len(summary_rows)}


def apply_variant(
    variant: DecoderVariant,
    base: np.ndarray,
    logits: torch.Tensor,
    mask_np: np.ndarray,
    ds: ChoraleDataset,
    source_harmony: dict[str, Any],
    length: int,
) -> np.ndarray:
    if variant.decoder_type == "none":
        return ds.tokenizer.sanitize_for_export(base.copy(), length=length)
    if variant.decoder_type == "local_rule_repair":
        return apply_rule_guided_decoding(base.copy(), ds.tokenizer, length=length)
    if variant.decoder_type == "cih_beam":
        return apply_cih_constrained_beam_search(
            base.copy(),
            logits,
            mask_np,
            ds.tokenizer,
            length=length,
            harmonic_labels=source_harmony,
            beam_size=variant.beam_size,
            top_k=variant.top_k,
            max_row_candidates=variant.max_row_candidates,
            lambda_rule=variant.lambda_rule,
            hard_constraints=list(variant.hard_constraints or []),
            soft_constraint_weights=dict(variant.soft_constraint_weights or {}),
        )
    raise ValueError(f"Unknown decoder_type: {variant.decoder_type}")


def per_100(report: dict[str, Any], key: str, length: int) -> float:
    return 100.0 * float((report.get("counts") or {}).get(key, 0)) / max(1, int(length))


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    baseline = None
    for variant_id in sorted({str(row["variant_id"]) for row in records}):
        variant_rows = [row for row in records if row["variant_id"] == variant_id]
        rule_values = [float(row["rule_violations_per_100_timesteps"]) for row in variant_rows]
        runtime_values = [float(row["runtime_seconds"]) for row in variant_rows]
        p5_values = [float(row["parallel_fifths_per_100_timesteps"]) for row in variant_rows]
        p8_values = [float(row["parallel_octaves_per_100_timesteps"]) for row in variant_rows]
        row = {
            "variant_id": variant_id,
            "variant_label": variant_rows[0]["variant_label"],
            "decoder_type": variant_rows[0]["decoder_type"],
            "beam_size": variant_rows[0]["beam_size"],
            "top_k": variant_rows[0]["top_k"],
            "score_count": len(variant_rows),
            "total_length": sum(int(item["length"]) for item in variant_rows),
            "mean_runtime_seconds_per_score": mean(runtime_values),
            "total_runtime_seconds": sum(runtime_values),
            "rule_violations_per_100_timesteps": mean(rule_values),
            "parallel_fifths_per_100_timesteps": mean(p5_values),
            "parallel_octaves_per_100_timesteps": mean(p8_values),
            "claim_boundary": "full-test decoder analysis; automatic rule diagnostics only",
        }
        rows.append(row)
        if variant_id == "neural_argmax":
            baseline = row
    if baseline is not None:
        base_rules = float(baseline["rule_violations_per_100_timesteps"])
        for row in rows:
            row["rule_reduction_vs_argmax_per_100"] = base_rules - float(row["rule_violations_per_100_timesteps"])
            row["rule_reduction_vs_argmax_percent"] = 100.0 * (base_rules - float(row["rule_violations_per_100_timesteps"])) / max(1e-9, base_rules)
    return rows


def mean(values: list[float]) -> float:
    return float(sum(values) / max(1, len(values)))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    fieldnames = list(rows[0]) if rows else []
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run formal CIH constraint-decoder analysis for Figure 5.")
    parser.add_argument("--config", default="runs/cih_s2s_formal_multiseed/seed_2026/input_config.yaml")
    parser.add_argument("--checkpoint", default="runs/cih_s2s_formal_multiseed/seed_2026/best.pt")
    parser.add_argument("--out-csv", default="results/constraint_decoder_analysis.csv")
    parser.add_argument("--out-json", default="results/constraint_decoder_analysis_summary.json")
    parser.add_argument("--max-batches", type=int, default=None)
    parser.add_argument("--export-samples", type=int, default=0)
    args = parser.parse_args()
    print(
        json.dumps(
            run_analysis(
                args.config,
                args.checkpoint,
                args.out_csv,
                args.out_json,
                max_batches=args.max_batches,
                export_samples=args.export_samples,
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
