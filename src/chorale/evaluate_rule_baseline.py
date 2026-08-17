from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from chorale.data.build_dataset import build_dataset_from_config
from chorale.data.chorale_dataset import ChoraleDataset
from chorale.export_musicxml import export_tokens_to_musicxml
from chorale.models.rule_baseline import RuleBaseline
from chorale.theory.explain_report import build_explanation_report
from chorale.utils import ensure_dir, load_config, write_json


def evaluate_rule_baseline(config_path: str | Path, output_path: str | Path | None = None) -> dict:
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
    baseline = RuleBaseline(ds.tokenizer)
    model_label = str(config.get("experiment", {}).get("label", config.get("run", {}).get("name", "rule_baseline")))
    export_dir = ensure_dir(Path(config["run"]["output_dir"]) / "rule_baseline_exports")
    export_limit = int(config.get("eval", {}).get("export_samples", 0))

    total_correct = 0
    total_targets = 0
    voice_correct = [0, 0, 0, 0]
    voice_total = [0, 0, 0, 0]
    rule_counts: dict[str, int] = {}
    total_steps = 0
    total_penalty = 0.0
    total_generations = 0
    valid_generations = 0
    export_attempts = 0
    export_success = 0
    cadence_unknown_count = 0
    cadence_checks = 0

    for item_idx in range(len(ds)):
        item = ds[item_idx]
        tokens = item["tokens"].numpy()
        input_tokens = item["input_tokens"].numpy()
        target_mask = item["target_mask"].numpy().astype(bool)
        length = int(item["length"].item())
        source_idx = int(item["source_index"].item())
        generated = baseline.harmonize(input_tokens, length=length)
        generated = ds.tokenizer.sanitize_for_export(generated, length=length)

        active = target_mask & (tokens != ds.tokenizer.PAD)
        total_correct += int((generated[active] == tokens[active]).sum())
        total_targets += int(active.sum())
        for voice in range(4):
            voice_mask = active[:, voice]
            voice_correct[voice] += int((generated[:, voice][voice_mask] == tokens[:, voice][voice_mask]).sum())
            voice_total[voice] += int(voice_mask.sum())

        source_harmony = ds.get_harmonic_labels(source_idx, length=length)
        report = build_explanation_report(
            generated,
            ds.tokenizer,
            length=length,
            title=str(item["name"]),
            key_tonic_pc=int(source_harmony.get("key_tonic_pc", 0)),
            harmonic_labels=source_harmony,
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

        if export_attempts < export_limit:
            export_attempts += 1
            try:
                export_tokens_to_musicxml(
                    generated,
                    ds.tokenizer,
                    export_dir / f"rule_baseline_sample{export_attempts}.musicxml",
                    length=length,
                    title=f"RuleBaseline sample {export_attempts}",
                )
                export_success += 1
            except Exception:
                pass

    parallel_fifths = int(rule_counts.get("parallel_fifth", 0))
    parallel_octaves = int(rule_counts.get("parallel_octave", 0))
    metrics = {
        "model": f"{model_label}_rule_baseline",
        "task": str(task_cfg.get("name", "soprano_to_satb")),
        "checkpoint": None,
        "cross_entropy": None,
        "negative_log_likelihood": None,
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
        "notes": [
            "RuleBaseline is deterministic and has no likelihood output, so cross_entropy and negative_log_likelihood are null.",
            "This output is a baseline comparison for the selected dataset split, not a standalone external-corpus robustness claim.",
        ],
    }
    if output_path:
        write_json(metrics, output_path)
    return metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate the deterministic SATB RuleBaseline on a dataset split.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()
    metrics = evaluate_rule_baseline(args.config, args.output)
    print(metrics)


if __name__ == "__main__":
    main()
