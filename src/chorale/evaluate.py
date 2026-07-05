from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader

from chorale.data.build_dataset import build_dataset_from_config
from chorale.data.chorale_dataset import ChoraleDataset
from chorale.decoding import decode_predictions
from chorale.export_musicxml import export_tokens_to_musicxml
from chorale.make_tables import build_project1_tables_from_csv
from chorale.theory.explain_report import build_explanation_report
from chorale.theory.roman_numeral import annotate_tokens_harmony
from chorale.theory.rule_guided_decoding import apply_constraint_reranking, apply_rule_guided_decoding
from chorale.train import batch_to_device, build_model, model_forward
from chorale.utils import ensure_dir, get_device, load_config, safe_torch_load, write_json


@torch.no_grad()
def evaluate(config_path: str | Path, checkpoint_path: str | Path | None = None, output_path: str | Path | None = None) -> dict:
    config = load_config(config_path)
    data_path = Path(config["data"]["processed_path"])
    if not data_path.exists():
        build_dataset_from_config(config)
    task_cfg = config.get("task", {})
    ds = ChoraleDataset(
        data_path,
        split="test",
        task=task_cfg.get("name", "soprano_to_satb"),
        mask_prob=task_cfg.get("mask_prob", 0.45),
        seed=int(config.get("seed", 1234)) + 2,
    )
    eval_cfg = config.get("eval", {})
    loader = DataLoader(ds, batch_size=int(eval_cfg.get("batch_size", 8)), shuffle=False, num_workers=0)
    device = get_device()
    checkpoint_path = Path(checkpoint_path or Path(config["run"]["output_dir"]) / "best.pt")
    checkpoint = safe_torch_load(checkpoint_path, map_location=device)
    model = build_model(checkpoint.get("config", config), vocab_size=int(checkpoint["vocab_size"])).to(device)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    model_label = str(config.get("experiment", {}).get("label", config.get("run", {}).get("name", "model")))
    task_name = str(config.get("task", {}).get("name", "soprano_to_satb"))
    use_rule_guided = bool(config.get("constraints", {}).get("use_rule_guided_decoding", False))
    decoding_cfg = config.get("decoding", {})
    refinement_steps = int(decoding_cfg.get("refinement_steps", 1)) if bool(decoding_cfg.get("iterative_refinement", False)) else 1
    refinement_strategy = str(decoding_cfg.get("refinement_strategy", "confidence"))
    remask_fraction = float(decoding_cfg.get("remask_fraction", 0.35))
    constraints_cfg = config.get("constraints", {})

    max_batches = eval_cfg.get("max_batches")
    max_batches = int(max_batches) if max_batches is not None else None
    losses = []
    total_correct = 0
    total_targets = 0
    voice_correct = [0, 0, 0, 0]
    voice_total = [0, 0, 0, 0]
    rule_counts: dict[str, int] = {}
    total_penalty = 0.0
    total_steps = 0
    valid_generations = 0
    total_generations = 0
    export_success = 0
    export_attempts = 0
    export_dir = ensure_dir(Path(config["run"]["output_dir"]) / "eval_exports")
    example_records: list[dict[str, str | int | float | bool]] = []
    roman_known_total = 0
    chord_known_total = 0
    generated_roman_known_total = 0
    generated_chord_known_total = 0
    harmony_label_steps = 0
    cadence_unknown_count = 0
    cadence_checks = 0

    for batch_idx, batch in enumerate(loader):
        if max_batches is not None and batch_idx >= max_batches:
            break
        batch_dev = batch_to_device(batch, device)
        logits = model_forward(model, batch_dev)
        targets = batch_dev["tokens"]
        mask = batch_dev["target_mask"] & (targets != 0)
        if mask.any():
            loss = F.cross_entropy(logits[mask], targets[mask])
            losses.append(float(loss.item()))
            pred, decode_logits = decode_predictions(
                model,
                batch_dev,
                mask_token=ds.tokenizer.MASK,
                refinement_steps=refinement_steps,
                refinement_strategy=refinement_strategy,
                remask_fraction=remask_fraction,
            )
            total_correct += int((pred[mask] == targets[mask]).sum().item())
            total_targets += int(mask.sum().item())
            for voice in range(4):
                voice_mask = mask[:, :, voice]
                if voice_mask.any():
                    voice_correct[voice] += int((pred[:, :, voice][voice_mask] == targets[:, :, voice][voice_mask]).sum().item())
                    voice_total[voice] += int(voice_mask.sum().item())
        else:
            pred, decode_logits = decode_predictions(
                model,
                batch_dev,
                mask_token=ds.tokenizer.MASK,
                refinement_steps=refinement_steps,
                refinement_strategy=refinement_strategy,
                remask_fraction=remask_fraction,
            )

        pred_cpu = pred.detach().cpu()
        decode_logits_cpu = decode_logits.detach().cpu()
        tokens_cpu = batch["tokens"].clone()
        target_mask_cpu = batch["target_mask"]
        for item_idx in range(pred_cpu.shape[0]):
            length = int(batch["length"][item_idx].item())
            source_idx = int(batch["source_index"][item_idx].item()) if "source_index" in batch else item_idx
            source_harmony = ds.get_harmonic_labels(source_idx, length=length)
            roman_known_total += int(np_count_true(source_harmony["roman_numeral_known"][:length]))
            chord_known_total += int(np_count_true(source_harmony["chord_label_known"][:length]))
            harmony_label_steps += length
            generated = tokens_cpu[item_idx].numpy()
            mask_np = target_mask_cpu[item_idx].numpy()
            generated[mask_np] = pred_cpu[item_idx].numpy()[mask_np]
            generated = ds.tokenizer.sanitize_for_export(generated, length=length)
            if bool(constraints_cfg.get("use_constraint_reranking", False)):
                generated = apply_constraint_reranking(
                    generated,
                    decode_logits_cpu[item_idx],
                    target_mask_cpu[item_idx].numpy(),
                    ds.tokenizer,
                    length=length,
                    harmonic_labels=source_harmony,
                    top_k=int(constraints_cfg.get("rerank_top_k", 4)),
                    rule_weight=float(constraints_cfg.get("rerank_rule_weight", 1.0)),
                    harmony_weight=float(constraints_cfg.get("rerank_harmony_weight", 0.25)),
                    temporal_weight=float(constraints_cfg.get("rerank_temporal_weight", 1.0)),
                    seventh_weight=float(constraints_cfg.get("rerank_seventh_weight", 1.0)),
                )
            if use_rule_guided:
                generated = apply_rule_guided_decoding(generated, ds.tokenizer, length=length)
            generated_harmony = annotate_tokens_harmony(
                generated,
                ds.tokenizer,
                length=length,
                key_label=source_harmony.get("key_label", "UNKNOWN"),
                key_tonic_pc=int(source_harmony.get("key_tonic_pc", 0)),
                measure_indices=batch["measure_indices"][item_idx].numpy(),
                beat_positions=batch["beat_positions"][item_idx].numpy(),
            )
            generated_roman_known_total += int(np_count_true(generated_harmony["roman_numeral_known"][:length]))
            generated_chord_known_total += int(np_count_true(generated_harmony["chord_label_known"][:length]))
            report = build_explanation_report(
                generated,
                ds.tokenizer,
                length=length,
                title=str(batch["name"][item_idx]),
                key_tonic_pc=int(generated_harmony["key_tonic_pc"]),
                harmonic_labels=generated_harmony,
            )
            cadence_unknown_count += int(report.get("cadence_unknown_count", 0))
            cadence_checks += int(report.get("cadence_checks", 0))
            for key, value in report["counts"].items():
                rule_counts[key] = rule_counts.get(key, 0) + int(value)
            total_penalty += float(report["total_penalty"])
            total_steps += length
            total_generations += 1
            if report["total_violations"] == 0:
                valid_generations += 1
            if export_attempts < int(eval_cfg.get("export_samples", 0)):
                export_attempts += 1
                export_path = export_dir / f"eval_sample{export_attempts}.musicxml"
                try:
                    export_tokens_to_musicxml(
                        generated,
                        ds.tokenizer,
                        export_path,
                        length=length,
                        title=f"Evaluation sample {export_attempts}",
                    )
                    export_success += 1
                    example_records.append(
                        {
                            "model": model_label,
                            "task": task_name,
                            "rule_guided_decoding": use_rule_guided,
                            "source_name": str(batch["name"][item_idx]),
                            "length": length,
                            "musicxml": str(export_path),
                            "total_violations": int(report["total_violations"]),
                            "violations_per_100_timesteps": float(report["violations_per_100_timesteps"]),
                        }
                    )
                except Exception:
                    pass

    parallel_fifths = int(rule_counts.get("parallel_fifth", 0))
    parallel_octaves = int(rule_counts.get("parallel_octave", 0))
    metrics = {
        "model": model_label,
        "task": task_name,
        "rule_guided_decoding": use_rule_guided,
        "checkpoint": str(checkpoint_path),
        "cross_entropy": float(sum(losses) / max(1, len(losses))),
        "negative_log_likelihood": float(sum(losses) / max(1, len(losses))),
        "pitch_token_accuracy": float(total_correct / max(1, total_targets)),
        "voice_wise_accuracy": {
            "soprano": float(voice_correct[0] / max(1, voice_total[0])),
            "alto": float(voice_correct[1] / max(1, voice_total[1])),
            "tenor": float(voice_correct[2] / max(1, voice_total[2])),
            "bass": float(voice_correct[3] / max(1, voice_total[3])),
        },
        "rule_violations_per_100_timesteps": float(100.0 * sum(rule_counts.values()) / max(1, total_steps)),
        "parallel_fifths_per_100_timesteps": float(100.0 * parallel_fifths / max(1, total_steps)),
        "parallel_octaves_per_100_timesteps": float(100.0 * parallel_octaves / max(1, total_steps)),
        "seventh_resolution_violation_rate": float(rule_counts.get("seventh_resolution", 0) / max(1, total_steps)),
        "cadence_unknown_rate": float(cadence_unknown_count / max(1, cadence_checks)),
        "cadence_correctness_rate": float(
            1.0 - (rule_counts.get("cadence_correctness", 0) / max(1, cadence_checks - cadence_unknown_count))
        )
        if cadence_checks > cadence_unknown_count
        else None,
        "roman_numeral_extraction_coverage": float(roman_known_total / max(1, harmony_label_steps)),
        "chord_label_coverage": float(chord_known_total / max(1, harmony_label_steps)),
        "generated_roman_numeral_coverage": float(generated_roman_known_total / max(1, harmony_label_steps)),
        "generated_chord_label_coverage": float(generated_chord_known_total / max(1, harmony_label_steps)),
        "voice_range_violation_rate": float(rule_counts.get("voice_range", 0) / max(1, total_steps * 4)),
        "voice_crossing_rate": float(rule_counts.get("voice_crossing", 0) / max(1, total_steps * 3)),
        "parallel_fifth_count": parallel_fifths,
        "parallel_octave_count": parallel_octaves,
        "spacing_violation_rate": float(rule_counts.get("spacing", 0) / max(1, total_steps * 3)),
        "generation_validity_rate": float(valid_generations / max(1, total_generations)),
        "musicxml_export_success_rate": float(export_success / max(1, export_attempts)) if export_attempts else None,
        "total_rule_penalty": total_penalty,
        "rule_counts": rule_counts,
        "evaluated_generations": int(total_generations),
    }
    if output_path:
        write_json(metrics, output_path)
    write_project1_outputs(
        metrics,
        rule_counts,
        total_steps,
        example_records,
        harmony_summary={
            "roman_known_total": roman_known_total,
            "chord_known_total": chord_known_total,
            "generated_roman_known_total": generated_roman_known_total,
            "generated_chord_known_total": generated_chord_known_total,
            "harmony_label_steps": harmony_label_steps,
            "cadence_unknown_count": cadence_unknown_count,
            "cadence_checks": cadence_checks,
        },
    )
    return metrics


def write_project1_outputs(
    metrics: dict,
    rule_counts: dict[str, int],
    total_steps: int,
    example_records: list[dict[str, str | int | float | bool]],
    harmony_summary: dict | None = None,
    results_dir: str | Path = "results",
    paper_tables_dir: str | Path = "paper/tables",
) -> None:
    results_dir = ensure_dir(results_dir)
    paper_tables_dir = ensure_dir(paper_tables_dir)
    metrics_csv = results_dir / "project1_metrics.csv"
    rule_csv = results_dir / "project1_rule_violations.csv"
    harmony_csv = results_dir / "project1_harmony_labels_summary.csv"
    examples_json = results_dir / "project1_generation_examples.json"

    row = {
        "model": metrics["model"],
        "task": metrics["task"],
        "rule_guided_decoding": metrics["rule_guided_decoding"],
        "checkpoint": metrics["checkpoint"],
        "pitch_accuracy": metrics["pitch_token_accuracy"],
        "cross_entropy": metrics["cross_entropy"],
        "negative_log_likelihood": metrics["negative_log_likelihood"],
        "soprano_accuracy": metrics["voice_wise_accuracy"]["soprano"],
        "alto_accuracy": metrics["voice_wise_accuracy"]["alto"],
        "tenor_accuracy": metrics["voice_wise_accuracy"]["tenor"],
        "bass_accuracy": metrics["voice_wise_accuracy"]["bass"],
        "rule_violations_per_100_timesteps": metrics["rule_violations_per_100_timesteps"],
        "parallel_fifths_per_100_timesteps": metrics["parallel_fifths_per_100_timesteps"],
        "parallel_octaves_per_100_timesteps": metrics["parallel_octaves_per_100_timesteps"],
        "seventh_resolution_violation_rate": metrics["seventh_resolution_violation_rate"],
        "cadence_correctness_rate": metrics["cadence_correctness_rate"],
        "cadence_unknown_rate": metrics["cadence_unknown_rate"],
        "roman_numeral_extraction_coverage": metrics["roman_numeral_extraction_coverage"],
        "chord_label_coverage": metrics["chord_label_coverage"],
        "generated_roman_numeral_coverage": metrics["generated_roman_numeral_coverage"],
        "generated_chord_label_coverage": metrics["generated_chord_label_coverage"],
        "voice_crossing_rate": metrics["voice_crossing_rate"],
        "range_violation_rate": metrics["voice_range_violation_rate"],
        "spacing_violation_rate": metrics["spacing_violation_rate"],
        "musicxml_export_success_rate": metrics["musicxml_export_success_rate"],
        "evaluated_generations": metrics["evaluated_generations"],
    }
    append_unique_csv(metrics_csv, row, unique_key=("model", "task", "rule_guided_decoding"))

    remove_csv_group(
        rule_csv,
        {
            "model": metrics["model"],
            "task": metrics["task"],
            "rule_guided_decoding": metrics["rule_guided_decoding"],
        },
    )
    for rule, count in sorted(rule_counts.items()):
        append_unique_csv(
            rule_csv,
            {
                "model": metrics["model"],
                "task": metrics["task"],
                "rule_guided_decoding": metrics["rule_guided_decoding"],
                "rule": rule,
                "count": int(count),
                "per_100_timesteps": float(100.0 * int(count) / max(1, total_steps)),
            },
            unique_key=("model", "task", "rule_guided_decoding", "rule"),
        )

    harmony_summary = harmony_summary or {}
    append_unique_csv(
        harmony_csv,
        {
            "model": metrics["model"],
            "task": metrics["task"],
            "rule_guided_decoding": metrics["rule_guided_decoding"],
            "roman_numeral_extraction_coverage": metrics["roman_numeral_extraction_coverage"],
            "chord_label_coverage": metrics["chord_label_coverage"],
            "roman_known_total": int(harmony_summary.get("roman_known_total", 0)),
            "chord_known_total": int(harmony_summary.get("chord_known_total", 0)),
            "generated_roman_known_total": int(harmony_summary.get("generated_roman_known_total", 0)),
            "generated_chord_known_total": int(harmony_summary.get("generated_chord_known_total", 0)),
            "harmony_label_steps": int(harmony_summary.get("harmony_label_steps", 0)),
            "cadence_unknown_count": int(harmony_summary.get("cadence_unknown_count", 0)),
            "cadence_checks": int(harmony_summary.get("cadence_checks", 0)),
        },
        unique_key=("model", "task", "rule_guided_decoding"),
    )

    existing_examples = []
    if examples_json.exists():
        try:
            loaded_examples = json.loads(examples_json.read_text(encoding="utf-8"))
            if isinstance(loaded_examples, dict):
                existing_examples = loaded_examples.get("examples", [])
            elif isinstance(loaded_examples, list):
                existing_examples = loaded_examples
        except json.JSONDecodeError:
            existing_examples = []
    existing_examples = [
        item
        for item in existing_examples
        if isinstance(item, dict)
        if not (
            item.get("model") == metrics["model"]
            and item.get("task") == metrics["task"]
            and item.get("rule_guided_decoding") == metrics["rule_guided_decoding"]
        )
    ]
    existing_examples.extend(example_records)
    write_json({"examples": existing_examples}, examples_json)
    build_project1_tables_from_csv(metrics_csv, paper_tables_dir)


def append_unique_csv(path: Path, row: dict, unique_key: tuple[str, ...]) -> None:
    rows: list[dict] = []
    if path.exists():
        with path.open("r", newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    row_as_str = {key: "" if value is None else str(value) for key, value in row.items()}
    rows = [old for old in rows if tuple(old.get(key, "") for key in unique_key) != tuple(row_as_str[key] for key in unique_key)]
    rows.append(row_as_str)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row_as_str.keys()))
        writer.writeheader()
        writer.writerows(rows)


def remove_csv_group(path: Path, match: dict[str, object]) -> None:
    if not path.exists():
        return
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    if not fieldnames:
        return
    match_as_str = {key: "" if value is None else str(value) for key, value in match.items()}
    rows = [
        row
        for row in rows
        if not all(row.get(key, "") == expected for key, expected in match_as_str.items())
    ]
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def np_count_true(values) -> int:
    import numpy as np

    return int(np.asarray(values, dtype=bool).sum())


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate a SATB chorale harmonizer.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    metrics = evaluate(args.config, args.checkpoint, args.output)
    print(metrics)


if __name__ == "__main__":
    main()
