from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


PYTHON = r".\.venv\Scripts\python.exe"


@dataclass(frozen=True)
class PlannedExperiment:
    experiment_id: str
    section: str
    task: str
    model_or_component: str
    comparison_role: str
    config_path: str
    seeds_required: str
    seeds_available: str
    status: str
    evidence_path: str
    train_command: str
    evaluate_command: str
    expected_artifact: str
    claim_boundary: str
    notes: str

    def as_row(self) -> dict[str, str]:
        return dict(self.__dict__)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else [
        "experiment_id",
        "section",
        "task",
        "model_or_component",
        "comparison_role",
        "config_path",
        "seeds_required",
        "seeds_available",
        "status",
        "evidence_path",
        "train_command",
        "evaluate_command",
        "expected_artifact",
        "claim_boundary",
        "notes",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def model_row_exists(rows: list[dict[str, str]], aliases: set[str], *, task: str | None = None) -> bool:
    aliases = {alias.lower() for alias in aliases}
    for row in rows:
        model = str(row.get("model", "")).lower()
        if task is not None and str(row.get("task", "")) != task:
            continue
        if model in aliases or any(alias in model for alias in aliases):
            return True
    return False


def evidence_status(root: Path, evidence_path: str, default_pending: str = "pending") -> str:
    if not evidence_path:
        return default_pending
    evidence = root / evidence_path
    return "completed" if evidence.exists() else default_pending


def build_experiment_matrix(root: str | Path = ROOT) -> list[dict[str, str]]:
    root = Path(root)
    metrics_rows = read_csv(root / "results" / "project1_metrics.csv")
    robustness = read_json(root / "results" / "project1_robustness_summary.json")
    vanilla_robustness = read_json(root / "results" / "vanilla_transformer_robustness_summary.json")
    cih_robustness = read_json(root / "results" / "cih_s2s_robustness_summary.json")
    robustness_seed_count = int(robustness.get("seed_count", 0) or 0)
    robustness_seeds = ",".join(str(seed) for seed in robustness.get("seeds", []) if seed is not None)
    vanilla_seed_count = int(vanilla_robustness.get("seed_count", 0) or 0)
    vanilla_seeds = ",".join(str(seed) for seed in vanilla_robustness.get("seeds", []) if seed is not None)
    cih_seed_count = int(cih_robustness.get("seed_count", 0) or 0)
    cih_seeds = ",".join(str(seed) for seed in cih_robustness.get("seeds", []) if seed is not None)

    def row(
        experiment_id: str,
        section: str,
        task: str,
        model_or_component: str,
        comparison_role: str,
        config_path: str = "",
        seeds_required: str = "1",
        seeds_available: str = "0",
        status: str = "pending",
        evidence_path: str = "",
        train_command: str = "",
        evaluate_command: str = "",
        expected_artifact: str = "",
        claim_boundary: str = "",
        notes: str = "",
    ) -> PlannedExperiment:
        return PlannedExperiment(
            experiment_id=experiment_id,
            section=section,
            task=task,
            model_or_component=model_or_component,
            comparison_role=comparison_role,
            config_path=config_path,
            seeds_required=seeds_required,
            seeds_available=seeds_available,
            status=status,
            evidence_path=evidence_path,
            train_command=train_command,
            evaluate_command=evaluate_command,
            expected_artifact=expected_artifact,
            claim_boundary=claim_boundary,
            notes=notes,
        )

    experiments: list[PlannedExperiment] = []
    has_lstm = model_row_exists(metrics_rows, {"lstm_baseline"}, task="soprano_to_satb")
    has_vanilla = model_row_exists(metrics_rows, {"transformer_no_constraints"}, task="soprano_to_satb")
    has_current = model_row_exists(metrics_rows, {"proposed_neural_symbolic_rule_guided_enhanced"}, task="soprano_to_satb")
    has_masked = model_row_exists(metrics_rows, {"proposed_neural_symbolic_masked_infilling_enhanced", "proposed_neural_symbolic_masked_infilling"}, task="masked_infill")
    has_no_harmony = model_row_exists(metrics_rows, {"ablation_no_harmony_conditioning_enhanced", "ablation_no_harmony_conditioning"}, task="soprano_to_satb")
    has_no_voice = model_row_exists(metrics_rows, {"ablation_no_voice_relation_attention_enhanced"}, task="soprano_to_satb")
    has_no_refinement = model_row_exists(metrics_rows, {"ablation_no_iterative_refinement_enhanced", "ablation_no_iterative_refinement"}, task="soprano_to_satb")
    has_no_rules = model_row_exists(metrics_rows, {"ablation_no_rule_guided_decoding_enhanced", "ablation_no_rule_guided_decoding"}, task="soprano_to_satb")
    cih_smoke = (root / "results" / "cih_s2s_smoke_metrics.json").exists()
    constraint_decoder_summary = (root / "results" / "constraint_decoder_analysis_summary.csv").exists()

    experiments.extend(
        [
            row(
                "baseline_rule_only_bach_s2s",
                "matched_baseline",
                "soprano_to_satb",
                "Rule-only baseline",
                "baseline",
                "configs/chorale_main.yaml",
                status=evidence_status(root, "results/rule_only_bach_metrics.json"),
                evidence_path="results/rule_only_bach_metrics.json",
                evaluate_command=f"{PYTHON} -m chorale.evaluate_rule_baseline --config configs\\chorale_main.yaml --output results\\rule_only_bach_metrics.json",
                expected_artifact="results/rule_only_bach_metrics.json",
                claim_boundary="No likelihood metrics are available for this deterministic baseline.",
                notes="Run this before presenting a complete matched-baseline table.",
            ),
            row(
                "baseline_lstm_bach_s2s",
                "matched_baseline",
                "soprano_to_satb",
                "LSTM baseline",
                "baseline",
                "configs/chorale_lstm.yaml",
                seeds_available="1" if has_lstm else "0",
                status="completed" if has_lstm else "pending",
                evidence_path="results/lstm_metrics.json",
                train_command=f"{PYTHON} -m chorale.train --config configs\\chorale_lstm.yaml",
                evaluate_command=f"{PYTHON} -m chorale.evaluate --config configs\\chorale_lstm.yaml --output results\\lstm_metrics.json",
                expected_artifact="results/project1_metrics.csv",
                claim_boundary="Single-seed aggregate unless repeated seeds are run.",
            ),
            row(
                "baseline_vanilla_transformer_bach_s2s",
                "matched_baseline",
                "soprano_to_satb",
                "Vanilla Transformer",
                "baseline",
                "configs/chorale_transformer_no_constraints.yaml",
                seeds_required="3",
                seeds_available=str(vanilla_seed_count) if vanilla_seed_count else ("1" if has_vanilla else "0"),
                status="completed_multiseed" if vanilla_seed_count >= 3 else ("single_seed_completed_needs_multiseed" if has_vanilla else "pending"),
                evidence_path="results/vanilla_transformer_robustness_summary.json" if vanilla_seed_count >= 3 else "results/transformer_no_constraints_metrics.json",
                train_command=f"{PYTHON} -m chorale.robustness --config configs\\chorale_transformer_no_constraints.yaml --seeds 2026 2027 2028 --run-root runs\\vanilla_transformer_formal_multiseed --out-csv results\\vanilla_transformer_multiseed_summary.csv --out-json results\\vanilla_transformer_robustness_summary.json",
                expected_artifact="results/vanilla_transformer_multiseed_summary.csv",
                claim_boundary="Same-corpus Bach split only; no SOTA claim.",
                notes=f"Existing seeds: {vanilla_seeds or 'none'}",
            ),
            row(
                "baseline_transformer_without_constraints_bach_s2s",
                "matched_baseline",
                "soprano_to_satb",
                "Transformer without constraints",
                "baseline",
                "configs/chorale_transformer_no_constraints.yaml",
                seeds_required="3",
                seeds_available=str(vanilla_seed_count) if vanilla_seed_count else ("1" if has_vanilla else "0"),
                status="completed_multiseed_same_as_vanilla" if vanilla_seed_count >= 3 else ("same_checkpoint_as_vanilla_needs_multiseed" if has_vanilla else "pending"),
                evidence_path="results/vanilla_transformer_robustness_summary.json" if vanilla_seed_count >= 3 else "results/transformer_no_constraints_metrics.json",
                claim_boundary="This row is the same no-constraints model family as the vanilla Transformer.",
            ),
            row(
                "baseline_current_rule_guided_bach_s2s",
                "matched_baseline",
                "soprano_to_satb",
                "Current rule-guided Transformer",
                "current_model",
                "configs/chorale_rule_guided_decoding.yaml",
                seeds_required="3",
                seeds_available=str(robustness_seed_count) if robustness_seed_count else ("1" if has_current else "0"),
                status="completed_multiseed" if robustness_seed_count >= 3 else ("single_seed_completed_needs_multiseed" if has_current else "pending"),
                evidence_path="results/project1_robustness_summary.json",
                train_command=f"{PYTHON} -m chorale.robustness --config configs\\chorale_rule_guided_decoding.yaml --seeds 2026 2027 2028",
                expected_artifact="results/project1_multiseed_summary.csv",
                claim_boundary="Same-corpus Bach split only.",
                notes=f"Existing seeds: {robustness_seeds or 'none'}",
            ),
            row(
                "baseline_cih_s2s_bach_s2s",
                "matched_baseline",
                "soprano_to_satb",
                "CIH-S2S Transformer",
                "new_model",
                "configs/cih_s2s_4060ti_16gb.yaml",
                seeds_required="3",
                seeds_available=str(cih_seed_count) if cih_seed_count else ("1 smoke" if cih_smoke else "0"),
                status="completed_multiseed" if cih_seed_count >= 3 else ("smoke_only_needs_formal_multiseed" if cih_smoke else "pending"),
                evidence_path="results/cih_s2s_robustness_summary.json" if cih_seed_count >= 3 else ("results/cih_s2s_smoke_metrics.json" if cih_smoke else ""),
                train_command=f"{PYTHON} -m chorale.robustness --config configs\\cih_s2s_4060ti_16gb.yaml --seeds 2026 2027 2028 --run-root runs\\cih_s2s_formal_multiseed --out-csv results\\cih_s2s_multiseed_summary.csv --out-json results\\cih_s2s_robustness_summary.json",
                expected_artifact="results/cih_s2s_multiseed_summary.csv",
                claim_boundary="Same-corpus Bach split only; no SOTA, expert-preference, or external-robustness claim.",
                notes=f"Existing seeds: {cih_seeds or 'none'}",
            ),
            row(
                "baseline_deepbach_style_pseudogibbs",
                "matched_baseline",
                "masked_infill",
                "DeepBach-style pseudo-Gibbs baseline",
                "todo_baseline",
                status="todo_not_implemented",
                claim_boundary="Do not report results until a real baseline is implemented and evaluated.",
                notes="Feasible future implementation: conditional pseudo-Gibbs over SATB tokens with the same split and tokenizer.",
            ),
            row(
                "baseline_coconet_style_infilling",
                "matched_baseline",
                "masked_infill",
                "Coconet-style infilling baseline",
                "todo_baseline",
                status="todo_not_implemented",
                claim_boundary="Do not report results until a real baseline is implemented and evaluated.",
                notes="Feasible future implementation: orderless masked self-attention infilling on the same symbolic grid.",
            ),
        ]
    )

    experiments.extend(
        [
            row(
                "task_masked_satb_infilling",
                "task",
                "masked_infill",
                "Masked SATB infilling",
                "main_task",
                "configs/chorale_masked_infilling.yaml",
                seeds_available="1" if has_masked else "0",
                status="completed_single_seed" if has_masked else "pending",
                evidence_path="results/masked_infilling_metrics.json",
                claim_boundary="Single-seed unless repeated seeds are run.",
            ),
            row("task_bass_to_satb", "task", "bass_to_satb", "Bass-to-SATB", "optional_task", status="todo_protocol_only", claim_boundary="Optional task; no result can be claimed yet."),
            row("task_partial_score_completion", "task", "partial_score_completion", "Partial-score completion", "optional_task", status="covered_by_masked_infill_protocol_pending_formal_split", claim_boundary="Needs a dedicated mask taxonomy before a separate claim."),
        ]
    )

    experiments.extend(
        [
            row("ablation_no_harmonic_conditioning", "component_ablation", "soprano_to_satb", "No harmonic conditioning", "ablation", "configs/chorale_ablation_no_harmony.yaml", seeds_available="1" if has_no_harmony else "0", status="completed_single_seed" if has_no_harmony else "pending", evidence_path="results/ablation_no_harmony_metrics.json"),
            row("ablation_no_voice_relation_attention", "component_ablation", "soprano_to_satb", "No voice-relation attention", "ablation", "configs/chorale_ablation_no_voice_relation.yaml", seeds_available="1" if has_no_voice else "0", status="completed_single_seed" if has_no_voice else "pending", evidence_path="results/ablation_no_voice_relation_enhanced_metrics.json"),
            row("ablation_no_bar_level_attention_cih", "component_ablation", "soprano_to_satb", "CIH no bar-level attention", "ablation", "configs/cih_s2s_no_bar_summary.yaml", status="planned_config_pending", claim_boundary="CIH ablation must be trained before reporting."),
            row("ablation_no_iterative_refinement", "component_ablation", "soprano_to_satb", "No iterative refinement", "ablation", "configs/chorale_ablation_no_iterative_refinement.yaml", seeds_available="1" if has_no_refinement else "0", status="completed_single_seed" if has_no_refinement else "pending", evidence_path="results/ablation_no_iterative_refinement_metrics.json"),
            row("ablation_no_constrained_decoding_cih", "constraint_decoding_analysis", "soprano_to_satb", "CIH no constrained decoding", "ablation", "configs/cih_s2s_no_constrained_decoding.yaml", status="planned_config_pending", claim_boundary="Must compare to the same checkpoint/config family."),
            row("ablation_local_repair_vs_constrained_beam", "constraint_decoding_analysis", "soprano_to_satb", "Local rule repair vs constrained beam", "ablation", "configs/cih_s2s_4060ti_16gb.yaml", status="completed_single_checkpoint" if constraint_decoder_summary else "planned", evidence_path="results/constraint_decoder_analysis_summary.csv" if constraint_decoder_summary else "results/project1_rerank_sweep_latest.csv", train_command=f"{PYTHON} scripts\\run_constraint_decoder_analysis.py --config runs\\cih_s2s_formal_multiseed\\seed_2026\\input_config.yaml --checkpoint runs\\cih_s2s_formal_multiseed\\seed_2026\\best.pt --out-csv results\\constraint_decoder_analysis.csv --out-json results\\constraint_decoder_analysis_summary.json --export-samples 4", claim_boundary="One trained CIH checkpoint; automatic diagnostics only; not a complete solver or universal rule-reduction claim."),
            row("ablation_hard_constraints_only", "constraint_decoding_analysis", "soprano_to_satb", "Hard constraints only", "ablation", "configs/cih_s2s_hard_constraints_only.yaml", status="planned_config_pending"),
            row("ablation_soft_constraints_only", "constraint_decoding_analysis", "soprano_to_satb", "Soft constraints only", "ablation", "configs/cih_s2s_soft_constraints_only.yaml", status="planned_config_pending"),
            row("sensitivity_topk_beamsize", "constraint_decoding_analysis", "soprano_to_satb", "Top-k / beam-size sensitivity", "sensitivity", "configs/cih_s2s_4060_8gb.yaml", status="completed_single_checkpoint" if constraint_decoder_summary else "planned", evidence_path="results/constraint_decoder_analysis_summary.csv" if constraint_decoder_summary else "", claim_boundary="Limit grid to 4060-friendly beam sizes; current evidence is one trained CIH checkpoint."),
            row("sensitivity_hidden_depth_4060", "component_ablation", "soprano_to_satb", "Hidden-size/depth sensitivity", "sensitivity", "configs/cih_s2s_4060_8gb.yaml", status="planned", claim_boundary="Do not exceed 4060/4060 Ti memory envelope."),
        ]
    )

    bcfb_summary = evidence_status(root, "results/project1_external_dataset_summary_latest.json")
    cpdl_summary = evidence_status(root, "results/project1_cpdl_external_dataset_summary_expanded.json")
    experiments.extend(
        [
            row("external_bcfb_bach_related_pilot", "external_source_protocol", "soprano_to_satb", "BCFB Bach-related external source", "pilot", "configs/chorale_bcfb_external_pilot.yaml", status=bcfb_summary, evidence_path="results/project1_external_dataset_summary_latest.json", claim_boundary="Bach-related source-chain pilot, not true external-repertory robustness."),
            row("external_cpdl_candidate_pilot", "external_source_protocol", "soprano_to_satb", "CPDL selected SATB candidates", "pilot", "configs/chorale_cpdl_external_expanded.yaml", status=cpdl_summary, evidence_path="results/project1_cpdl_external_dataset_summary_expanded.json", claim_boundary="Automatically selected candidate subset; not representative CPDL robustness or license-cleared benchmark."),
            row("external_curated_cpdl_benchmark", "external_source_protocol", "soprano_to_satb", "Curated public-domain CPDL benchmark", "formal_external_benchmark", status="protocol_pending_curation", expected_artifact="results/external_benchmark_manifest.csv", claim_boundary="No external generalization claim until curation, filtering, split, and evaluation are complete."),
        ]
    )
    experiments.append(
        row(
            "expert_blind_evaluation_protocol",
            "expert_evaluation_protocol",
            "soprano_to_satb",
            "Ground truth vs vanilla vs current rule-guided vs CIH-S2S",
            "human_evaluation",
            status="protocol_pending_completed_ratings",
            evidence_path="expert_eval/project1",
            expected_artifact="expert_eval/project1/sci_blind_protocol_packet",
            claim_boundary="No expert preference or rating result may be reported until completed returned forms are ingested.",
        )
    )
    return [item.as_row() for item in experiments]


def write_markdown_summary(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    lines = [
        "# Project1 Experiment Matrix",
        "",
        "This matrix is a planning and evidence-status file. It does not convert pending experiments into results.",
        "",
        "## Status Counts",
        "",
    ]
    lines.extend(f"- {status}: {count}" for status, count in sorted(counts.items()))
    lines.extend(["", "## Rows", "", "| ID | Section | Task | Component | Status | Evidence |", "|---|---|---|---|---|---|"])
    for row in rows:
        lines.append(
            f"| {row['experiment_id']} | {row['section']} | {row['task']} | {row['model_or_component']} | {row['status']} | {row['evidence_path']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_command_ledger(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Project1 Experiment Suite Commands",
        "",
        "# Run commands manually after checking GPU memory and author-approved experiment scope.",
        "",
    ]
    for row in rows:
        commands = [row.get("train_command", ""), row.get("evaluate_command", "")]
        commands = [command for command in commands if command]
        if not commands:
            continue
        lines.append(f"# {row['experiment_id']} ({row['status']})")
        lines.extend(commands)
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def execute_experiment(rows: list[dict[str, str]], experiment_id: str, *, root: Path) -> int:
    matches = [row for row in rows if row["experiment_id"] == experiment_id]
    if not matches:
        raise SystemExit(f"Unknown experiment_id: {experiment_id}")
    row = matches[0]
    commands = [row.get("train_command", ""), row.get("evaluate_command", "")]
    commands = [command for command in commands if command]
    if not commands:
        raise SystemExit(f"No executable command is registered for {experiment_id}")
    for command in commands:
        completed = subprocess.run(command, cwd=root, shell=True, text=True)
        if completed.returncode != 0:
            return completed.returncode
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Write or execute the Project1 SCI experiment-suite matrix.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out-csv", default="results/experiment_matrix.csv")
    parser.add_argument("--out-md", default="results/experiment_matrix.md")
    parser.add_argument("--commands-out", default="results/experiment_suite_commands.ps1")
    parser.add_argument("--execute", action="store_true", help="Execute registered commands for --experiment-id.")
    parser.add_argument("--experiment-id", default="")
    args = parser.parse_args()

    root = Path(args.root)
    rows = build_experiment_matrix(root)
    write_csv(root / args.out_csv, rows)
    write_markdown_summary(root / args.out_md, rows)
    write_command_ledger(root / args.commands_out, rows)
    if args.execute:
        if not args.experiment_id:
            raise SystemExit("--execute requires --experiment-id")
        raise SystemExit(execute_experiment(rows, args.experiment_id, root=root))
    print(json.dumps({"rows": len(rows), "out_csv": args.out_csv, "out_md": args.out_md}, indent=2))


if __name__ == "__main__":
    main()
