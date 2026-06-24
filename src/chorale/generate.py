from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import torch
from torch.utils.data import DataLoader

from chorale.data.build_dataset import build_dataset_from_config
from chorale.data.chorale_dataset import ChoraleDataset
from chorale.decoding import decode_predictions
from chorale.export_musicxml import export_tokens_to_musicxml
from chorale.models.rule_baseline import RuleBaseline
from chorale.theory.explain_report import build_explanation_report, write_explanation_report
from chorale.theory.roman_numeral import annotate_tokens_harmony
from chorale.theory.rule_guided_decoding import apply_constraint_reranking, apply_rule_guided_decoding
from chorale.train import batch_to_device, build_model
from chorale.utils import ensure_dir, get_device, load_config, safe_torch_load


@torch.no_grad()
def generate(
    config_path: str | Path,
    checkpoint_path: str | Path | None = None,
    output_dir: str | Path = "generated_scores",
    num_samples: int = 1,
    prefix: str = "sample",
) -> list[dict[str, str]]:
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
        seed=int(config.get("seed", 1234)) + 3,
    )
    loader = DataLoader(ds, batch_size=1, shuffle=False, num_workers=0)
    output_dir = ensure_dir(output_dir)
    use_rule_guided = bool(config.get("constraints", {}).get("use_rule_guided_decoding", False))
    decoding_cfg = config.get("decoding", {})
    refinement_steps = int(decoding_cfg.get("refinement_steps", 1)) if bool(decoding_cfg.get("iterative_refinement", False)) else 1
    refinement_strategy = str(decoding_cfg.get("refinement_strategy", "confidence"))
    remask_fraction = float(decoding_cfg.get("remask_fraction", 0.35))
    constraints_cfg = config.get("constraints", {})

    model = None
    device = get_device()
    checkpoint_path = Path(checkpoint_path) if checkpoint_path else Path(config["run"]["output_dir"]) / "best.pt"
    if checkpoint_path.exists():
        checkpoint = safe_torch_load(checkpoint_path, map_location=device)
        model = build_model(checkpoint.get("config", config), vocab_size=int(checkpoint["vocab_size"])).to(device)
        model.load_state_dict(checkpoint["model_state"])
        model.eval()
    else:
        baseline = RuleBaseline(ds.tokenizer)

    outputs: list[dict[str, str]] = []
    for sample_idx, batch in enumerate(loader):
        if sample_idx >= num_samples:
            break
        length = int(batch["length"][0].item())
        source_idx = int(batch["source_index"][0].item()) if "source_index" in batch else sample_idx
        source_harmony = ds.get_harmonic_labels(source_idx, length=length)
        truth = batch["tokens"][0].numpy()
        if model is not None:
            batch_dev = batch_to_device(batch, device)
            pred, decode_logits = decode_predictions(
                model,
                batch_dev,
                mask_token=ds.tokenizer.MASK,
                refinement_steps=refinement_steps,
                refinement_strategy=refinement_strategy,
                remask_fraction=remask_fraction,
            )
            pred = pred[0].detach().cpu().numpy()
            generated = truth.copy()
            mask = batch["target_mask"][0].numpy()
            generated[mask] = pred[mask]
        else:
            generated = baseline.harmonize(batch["input_tokens"][0].numpy(), length=length)
        generated = ds.tokenizer.sanitize_for_export(generated, length=length)
        if model is not None and bool(constraints_cfg.get("use_constraint_reranking", False)):
            generated = apply_constraint_reranking(
                generated,
                decode_logits[0],
                batch["target_mask"][0].numpy(),
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

        base = f"{prefix}_sample{sample_idx}"
        truth_xml = output_dir / f"{base}_ground_truth.musicxml"
        gen_xml = output_dir / f"{base}_generated.musicxml"
        report_txt = output_dir / f"{base}_report.txt"
        report_json = output_dir / f"{base}_report.json"
        export_tokens_to_musicxml(truth, ds.tokenizer, truth_xml, length=length, title=f"{base} ground truth")
        export_tokens_to_musicxml(generated, ds.tokenizer, gen_xml, length=length, title=f"{base} generated")
        generated_harmony = annotate_tokens_harmony(
            generated,
            ds.tokenizer,
            length=length,
            key_label=source_harmony.get("key_label", "UNKNOWN"),
            key_tonic_pc=int(source_harmony.get("key_tonic_pc", 0)),
            measure_indices=batch["measure_indices"][0].numpy(),
            beat_positions=batch["beat_positions"][0].numpy(),
        )
        report = build_explanation_report(
            generated,
            ds.tokenizer,
            length=length,
            title=f"{base} generated rule report",
            key_tonic_pc=int(generated_harmony["key_tonic_pc"]),
            harmonic_labels=generated_harmony,
        )
        write_explanation_report(report, report_txt, report_json)
        outputs.append(
            {
                "ground_truth": str(truth_xml),
                "generated": str(gen_xml),
                "report_txt": str(report_txt),
                "report_json": str(report_json),
            }
        )
    return outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SATB MusicXML from soprano-conditioned examples.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--output-dir", default="generated_scores")
    parser.add_argument("--num-samples", type=int, default=1)
    parser.add_argument("--prefix", default="sample")
    args = parser.parse_args()
    outputs = generate(args.config, args.checkpoint, args.output_dir, args.num_samples, args.prefix)
    for item in outputs:
        print(item)


if __name__ == "__main__":
    main()
