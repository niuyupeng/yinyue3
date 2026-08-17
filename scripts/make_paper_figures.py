from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
FIG_DIR = ROOT / "paper" / "figures"
SOURCE_DIR = FIG_DIR / "source_data"
CAPTION_DIR = FIG_DIR / "captions"

PRIMARY_MODELS = [
    {
        "key": "lstm_baseline",
        "label": "LSTM",
        "aliases": {"lstm_baseline", "chorale_lstm"},
        "task": "soprano_to_satb",
        "seed_count": "1",
        "claim_boundary": "single-seed same-corpus Bach baseline",
    },
    {
        "key": "vanilla_transformer",
        "label": "Vanilla Transformer",
        "aliases": {"transformer_no_constraints", "chorale_transformer_no_constraints"},
        "task": "soprano_to_satb",
        "seed_count": "3 formal seeds when multiseed summary is present; otherwise 1 plotted row",
        "claim_boundary": "same-corpus Bach baseline; statistics only when paired multiseed rows are available",
    },
    {
        "key": "current_rule_guided",
        "label": "Current rule-guided",
        "aliases": {"proposed_neural_symbolic_rule_guided_enhanced", "chorale_rule_guided_decoding"},
        "task": "soprano_to_satb",
        "seed_count": "3 for robustness summary; 1 plotted row in main comparison",
        "claim_boundary": "same-corpus Bach evidence only",
    },
    {
        "key": "cih_s2s",
        "label": "CIH-S2S",
        "aliases": {"cih_s2s_transformer", "cih_s2s_transformer_smoke"},
        "task": "soprano_to_satb",
        "seed_count": "3 formal seeds when robustness summary is present",
        "claim_boundary": "same-corpus Bach evidence only; no state-of-the-art or expert-preference claim",
    },
]

ABLATION_VARIANTS = [
    {
        "key": "full",
        "label": "Full",
        "aliases": {"proposed_neural_symbolic_rule_guided_enhanced", "chorale_rule_guided_decoding"},
        "task": "soprano_to_satb",
        "claim_boundary": "single plotted row; multiseed summary exists separately",
    },
    {
        "key": "no_harmony",
        "label": "No harmony",
        "aliases": {"ablation_no_harmony_conditioning_enhanced", "ablation_no_harmony_conditioning"},
        "task": "soprano_to_satb",
        "claim_boundary": "single-seed ablation",
    },
    {
        "key": "no_voice_relation",
        "label": "No voice relation",
        "aliases": {"ablation_no_voice_relation_attention_enhanced", "ablation_no_voice_relation_attention"},
        "task": "soprano_to_satb",
        "claim_boundary": "single-seed ablation",
    },
    {
        "key": "no_refinement",
        "label": "No refinement",
        "aliases": {"ablation_no_iterative_refinement_enhanced", "ablation_no_iterative_refinement"},
        "task": "soprano_to_satb",
        "claim_boundary": "single-seed ablation",
    },
    {
        "key": "no_rules",
        "label": "No rules",
        "aliases": {"ablation_no_rule_guided_decoding_enhanced", "ablation_no_rule_guided_decoding"},
        "task": "soprano_to_satb",
        "claim_boundary": "single-seed ablation of the current rule-guided decoder",
    },
    {
        "key": "no_constrained_decoding",
        "label": "No constrained decoding",
        "aliases": {"cih_s2s_no_constrained_decoding"},
        "task": "soprano_to_satb",
        "claim_boundary": "CIH-specific constrained-decoding ablation pending",
    },
]

RULES = [
    ("parallel_fifth", "Parallel fifths"),
    ("parallel_octave", "Parallel octaves"),
    ("voice_crossing", "Crossing"),
    ("spacing", "Spacing"),
    ("seventh_resolution", "Seventh resolution"),
    ("leading_tone_resolution", "Leading tone"),
]

PALETTE = {
    "LSTM": "#6F6F6F",
    "Vanilla Transformer": "#8190B8",
    "Current rule-guided": "#1C5A92",
    "CIH-S2S": "#B8B8B8",
    "Full": "#1C5A92",
    "No harmony": "#C2A261",
    "No voice relation": "#B05A5A",
    "No refinement": "#7A9A6A",
    "No rules": "#8B6FA8",
    "No constrained decoding": "#B8B8B8",
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate SCI-style paper figures from stored result artifacts.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    root = Path(args.root).resolve()
    make_paper_figures(root)


def make_paper_figures(root: Path = ROOT) -> dict[str, str]:
    import matplotlib as mpl
    import matplotlib.pyplot as plt

    configure_matplotlib(mpl)
    fig_dir = root / "paper" / "figures"
    source_dir = fig_dir / "source_data"
    caption_dir = fig_dir / "captions"
    source_dir.mkdir(parents=True, exist_ok=True)
    caption_dir.mkdir(parents=True, exist_ok=True)

    generated: dict[str, str] = {}
    generated.update(make_figure1(root, fig_dir, source_dir, caption_dir, plt))
    generated.update(make_figure2(root, fig_dir, source_dir, caption_dir, plt))
    generated.update(make_figure3(root, fig_dir, source_dir, caption_dir, plt))
    generated.update(make_figure4(root, fig_dir, source_dir, caption_dir, plt))
    generated.update(make_figure5(root, fig_dir, source_dir, caption_dir, plt))
    generated.update(make_figure6(root, fig_dir, source_dir, caption_dir, plt))
    generated.update(make_figure7(root, fig_dir, source_dir, caption_dir, plt))
    write_figure_manifest(root, generated)
    return generated


def configure_matplotlib(mpl) -> None:
    mpl.rcParams.update(
        {
            "font.family": "sans-serif",
            "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
            "font.size": 7,
            "axes.labelsize": 7,
            "axes.titlesize": 8,
            "axes.spines.right": False,
            "axes.spines.top": False,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.5,
            "legend.frameon": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def make_figure1(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    dataset = read_json(root / "results" / "experiment_dataset_summary.json")
    upgrade = read_json(root / "results" / "project1_hierarchical_upgrade_status.json")
    matrix = read_csv(root / "results" / "experiment_matrix.csv")
    expert = read_json(root / "expert_eval" / "project1" / "sci_blind_protocol_packet" / "packet_manifest.json")
    cih_row = find_matrix_row(matrix, "baseline_cih_s2s_bach_s2s")

    steps = [
        ("Partial score", f"SATB tensor {dataset.get('tokens_shape', '')}", "results/experiment_dataset_summary.json"),
        ("Tokenizer", f"grid={dataset.get('grid_quarter_length')}; vocab={dataset.get('vocab_size')}", "results/experiment_dataset_summary.json"),
        ("Harmonic plan encoder", "key, beat, measure, phrase and harmonic-label inputs", "results/project1_hierarchical_upgrade_status.json"),
        ("Hierarchical SATB decoder", cih_row.get("status", "status unknown"), "results/experiment_matrix.csv"),
        ("Constrained decoding", constraint_decoder_status(upgrade), "results/project1_hierarchical_upgrade_status.json"),
        ("MusicXML + rule report", f"expert packet status: {expert.get('status', 'pending')}", "expert_eval/project1/sci_blind_protocol_packet/packet_manifest.json"),
    ]
    rows = [
        {
            "figure": "Figure 1",
            "panel": "system",
            "step_index": str(i + 1),
            "step": step,
            "evidence_summary": summary,
            "source_file": source,
            "seed_count": "not applicable",
            "claim_boundary": "system schematic; no performance claim",
        }
        for i, (step, summary, source) in enumerate(steps)
    ]
    write_csv(source_dir / "figure1_system_structure_source.csv", rows)

    fig, ax = plt.subplots(figsize=(7.2, 1.85), constrained_layout=True)
    ax.set_axis_off()
    xs = [0.07, 0.23, 0.40, 0.58, 0.75, 0.91]
    y = 0.55
    for idx, ((step, summary, _), x) in enumerate(zip(steps, xs)):
        ax.text(
            x,
            y,
            wrap_label(step, 18),
            ha="center",
            va="center",
            fontsize=7.5,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.38", facecolor="#F4F6F8", edgecolor="#6D7A86", linewidth=0.8),
            transform=ax.transAxes,
        )
        ax.text(x, 0.18, wrap_label(summary, 32), ha="center", va="center", fontsize=5.8, color="#49515A", transform=ax.transAxes)
        if idx < len(xs) - 1:
            ax.annotate(
                "",
                xy=(xs[idx + 1] - 0.075, y),
                xytext=(x + 0.075, y),
                xycoords=ax.transAxes,
                arrowprops=dict(arrowstyle="->", lw=1.1, color="#3D4852"),
            )
    ax.set_title("Constraint-integrated score-to-score SATB harmonization workflow", loc="left", pad=4)
    out = fig_dir / "figure1_system_structure"
    save_all(fig, out)
    plt.close(fig)
    write_caption(
        caption_dir / "figure1_system_structure_caption.md",
        "Figure 1. System structure for the score-level SATB harmonization pipeline. Source data: results/experiment_dataset_summary.json, results/project1_hierarchical_upgrade_status.json, results/experiment_matrix.csv, and expert_eval/project1/sci_blind_protocol_packet/packet_manifest.json. The figure is a schematic of implemented or recorded pipeline components and does not report model superiority, confidence intervals, significance tests, or expert ratings.",
    )
    return {"figure1": str(out.with_suffix(".pdf"))}


def make_figure2(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    source_rows = build_main_result_rows(root)
    long_rows = []
    metrics = [
        ("pitch_accuracy", "Pitch accuracy", "higher"),
        ("cross_entropy", "Cross entropy", "lower"),
        ("rule_violations_per_100_timesteps", "Rule flags/100", "lower"),
        ("musicxml_export_success_rate", "XML success", "higher"),
    ]
    for row in source_rows:
        for metric, label, direction in metrics:
            long_rows.append(
                {
                    "figure": "Figure 2",
                    "panel": metric,
                    "model_key": row["model_key"],
                    "model_label": row["model_label"],
                    "task": row["task"],
                    "metric": metric,
                    "metric_label": label,
                    "metric_direction": direction,
                    "value": row.get(metric, ""),
                    "status": row["status"],
                    "seed_count": row["seed_count"],
                    "source_file": row["source_file"],
                    "claim_boundary": row["claim_boundary"],
                }
            )
    write_csv(source_dir / "figure2_main_results_source.csv", long_rows)

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.4), constrained_layout=True)
    for ax, (metric, label, _) in zip(axes.ravel(), metrics):
        labels = [r["model_label"] for r in source_rows]
        values = [to_float(r.get(metric, "")) for r in source_rows]
        colors = [PALETTE.get(label, "#888888") for label in labels]
        xs = list(range(len(labels)))
        for x, value, color, row in zip(xs, values, colors, source_rows):
            if value is None:
                ax.text(x, 0.02, "pending", ha="center", va="bottom", rotation=90, fontsize=6, color="#666666")
                ax.bar(x, 0, color="none", edgecolor="#B8B8B8", linewidth=0.8)
            else:
                ax.bar(x, value, color=color, edgecolor="#333333", linewidth=0.4)
        ax.set_title(label, loc="left")
        ax.set_xticks(xs, [short_label(v) for v in labels], rotation=25, ha="right")
        ax.grid(axis="y", alpha=0.22, linewidth=0.6)
        if metric in {"pitch_accuracy", "musicxml_export_success_rate"}:
            ax.set_ylim(0, 1.05)
    fig.suptitle("Held-out Bach same-split results with evidence boundaries", x=0.01, ha="left", fontsize=9, fontweight="bold")
    out = fig_dir / "figure2_main_results"
    save_all(fig, out)
    plt.close(fig)
    write_caption(
        caption_dir / "figure2_main_results_caption.md",
        "Figure 2. Main result comparison on the soprano-to-SATB task for the deterministic music21 Bach split. Source data: results/project1_metrics.csv plus formal robustness summaries when present (results/project1_robustness_summary.json, results/vanilla_transformer_robustness_summary.json, and results/cih_s2s_robustness_summary.json). Vanilla Transformer, current rule-guided Transformer, and CIH-S2S values are three-seed means when the corresponding formal multiseed summary is available; LSTM remains a single-seed baseline. This figure reports automatic metrics only and does not imply state-of-the-art performance or expert preference.",
    )
    return {"figure2": str(out.with_suffix(".pdf"))}


def make_figure3(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    rows = build_rule_diagnostic_rows(root)
    write_csv(source_dir / "figure3_rule_diagnostics_source.csv", rows)
    models = ["Vanilla Transformer", "Current rule-guided"]
    rule_labels = [label for _, label in RULES]
    width = 0.36

    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), gridspec_kw={"width_ratios": [3.1, 0.9]}, constrained_layout=True)
    ax = axes[0]
    for mi, model in enumerate(models):
        vals = [to_float(find_value(rows, model, rule)) or 0.0 for rule, _ in RULES]
        xs = [i + (mi - 0.5) * width for i in range(len(rule_labels))]
        ax.bar(xs, vals, width=width, label=model, color=PALETTE.get(model, "#777777"), edgecolor="#333333", linewidth=0.35)
    ax.set_xticks(range(len(rule_labels)), rule_labels, rotation=28, ha="right")
    ax.set_ylabel("Flags per 100 score positions")
    ax.set_title("A. Local rule diagnostics", loc="left")
    ax.grid(axis="y", alpha=0.22, linewidth=0.6)
    ax.legend(loc="upper right")

    ax2 = axes[1]
    cadence_vals = [to_float(find_value(rows, model, "cadence_unknown_rate")) for model in models]
    ax2.bar(range(len(models)), [v if v is not None else 0 for v in cadence_vals], color=[PALETTE.get(m, "#777777") for m in models], edgecolor="#333333", linewidth=0.35)
    ax2.set_xticks(range(len(models)), ["Vanilla", "Current"], rotation=25, ha="right")
    ax2.set_ylim(0, 1.0)
    ax2.set_title("B. Cadence unknown", loc="left")
    ax2.set_ylabel("Rate")
    ax2.grid(axis="y", alpha=0.22, linewidth=0.6)
    fig.suptitle("Automatic rule diagnostics, not expert-rated musical quality", x=0.01, ha="left", fontsize=9, fontweight="bold")
    out = fig_dir / "figure3_rule_diagnostics"
    save_all(fig, out)
    plt.close(fig)
    write_caption(
        caption_dir / "figure3_rule_diagnostics_caption.md",
        "Figure 3. Automatic rule diagnostics for vanilla Transformer and current rule-guided Transformer outputs on the soprano-to-SATB Bach test split. Source data: results/project1_rule_violations.csv and results/project1_metrics.csv. Rule counts are normalized per 100 score positions; cadence unknown is a rate from automatic cadence diagnostics. The figure reports automatic diagnostics only and includes no expert rating, confidence interval, or significance test.",
    )
    return {"figure3": str(out.with_suffix(".pdf"))}


def make_figure4(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    rows = build_ablation_rows(root)
    metrics = [
        ("pitch_accuracy", "Pitch accuracy"),
        ("rule_violations_per_100_timesteps", "Rule flags/100"),
        ("parallel_octaves_per_100_timesteps", "P8/100"),
    ]
    long_rows = []
    for row in rows:
        for metric, label in metrics:
            long_rows.append(
                {
                    "figure": "Figure 4",
                    "panel": metric,
                    "variant_key": row["variant_key"],
                    "variant_label": row["variant_label"],
                    "task": row["task"],
                    "metric": metric,
                    "metric_label": label,
                    "value": row.get(metric, ""),
                    "status": row["status"],
                    "source_file": row["source_file"],
                    "seed_count": row["seed_count"],
                    "claim_boundary": row["claim_boundary"],
                }
            )
    write_csv(source_dir / "figure4_ablation_source.csv", long_rows)

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.25), constrained_layout=True)
    for ax, (metric, label) in zip(axes, metrics):
        labels = [r["variant_label"] for r in rows]
        xs = list(range(len(labels)))
        vals = [to_float(r.get(metric, "")) for r in rows]
        for x, val, row in zip(xs, vals, rows):
            color = PALETTE.get(row["variant_label"], "#888888")
            if val is None:
                ax.text(x, 0.02, "pending", ha="center", va="bottom", rotation=90, fontsize=6, color="#666666")
                ax.bar(x, 0, color="none", edgecolor="#B8B8B8", linewidth=0.8)
            else:
                ax.bar(x, val, color=color, edgecolor="#333333", linewidth=0.35)
        ax.set_title(label, loc="left")
        ax.set_xticks(xs, [short_label(v) for v in labels], rotation=30, ha="right")
        ax.grid(axis="y", alpha=0.22, linewidth=0.6)
        if metric == "pitch_accuracy":
            ax.set_ylim(0, 1.05)
    fig.suptitle("Component ablations: token metrics and rule diagnostics diverge", x=0.01, ha="left", fontsize=9, fontweight="bold")
    out = fig_dir / "figure4_ablation"
    save_all(fig, out)
    plt.close(fig)
    write_caption(
        caption_dir / "figure4_ablation_caption.md",
        "Figure 4. Component ablations for the soprano-to-SATB Bach task. Source data: results/project1_metrics.csv and results/experiment_matrix.csv. Completed rows are single-seed ablations unless otherwise stated. The CIH-specific no-constrained-decoding ablation is pending and is shown without a bar. No confidence interval or significance test is included.",
    )
    return {"figure4": str(out.with_suffix(".pdf"))}


def make_figure5(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    summary_path = root / "results" / "constraint_decoder_analysis_summary.csv"
    raw_path = root / "results" / "constraint_decoder_analysis.csv"
    summary_rows = read_csv(summary_path)
    if summary_rows:
        order = {"neural_argmax": 0, "local_rule_repair": 1, "beam_b2_k4": 2, "beam_b4_k8": 3, "beam_b8_k12": 4}
        summary_rows = sorted(summary_rows, key=lambda row: order.get(row.get("variant_id", ""), 99))
        source_rows = []
        for row in summary_rows:
            source_row = dict(row)
            source_row["figure"] = "Figure 5"
            source_row["source_file"] = str(summary_path.relative_to(root))
            source_row["raw_source_file"] = str(raw_path.relative_to(root)) if raw_path.exists() else ""
            source_row["task"] = "soprano_to_satb"
            source_row["seed_count"] = "1 checkpoint full test"
            source_row["claim_boundary"] = "full-test decoder analysis for one trained CIH checkpoint; automatic rule diagnostics only; no expert rating"
            source_rows.append(source_row)
        write_csv(source_dir / "figure5_constraint_decoder_analysis_source.csv", source_rows)

        labels = [row["variant_label"] for row in source_rows]
        rules = [to_float(row.get("rule_violations_per_100_timesteps", "")) or 0.0 for row in source_rows]
        runtimes = [to_float(row.get("mean_runtime_seconds_per_score", "")) or 0.0 for row in source_rows]
        reductions = [to_float(row.get("rule_reduction_vs_argmax_percent", "")) or 0.0 for row in source_rows]
        xs = list(range(len(labels)))
        colors = ["#6F6F6F", "#1C5A92", "#7A9A6A", "#C2A261", "#8B6FA8"][: len(labels)]

        fig, axes = plt.subplots(1, 3, figsize=(7.2, 3.1), constrained_layout=True)
        axes[0].bar(xs, rules, color=colors, edgecolor="#333333", linewidth=0.35)
        axes[0].set_title("A. Rule flags", loc="left")
        axes[0].set_ylabel("Flags per 100 positions")
        axes[1].bar(xs, runtimes, color=colors, edgecolor="#333333", linewidth=0.35)
        axes[1].set_title("B. Runtime", loc="left")
        axes[1].set_ylabel("Seconds per score")
        axes[2].bar(xs, reductions, color=colors, edgecolor="#333333", linewidth=0.35)
        axes[2].set_title("C. Rule-flag change", loc="left")
        axes[2].set_ylabel("% vs argmax")
        for ax in axes:
            ax.set_xticks(xs, [short_label(label) for label in labels], rotation=30, ha="right")
            ax.grid(axis="y", alpha=0.22, linewidth=0.6)
        fig.suptitle("Constraint-decoder analysis on a trained CIH-S2S checkpoint", x=0.01, ha="left", fontsize=9, fontweight="bold")
        out = fig_dir / "figure5_constraint_decoder_analysis"
        save_all(fig, out)
        plt.close(fig)
        write_caption(
            caption_dir / "figure5_constraint_decoder_analysis_caption.md",
            "Figure 5. Constraint-decoder analysis on the full Bach test split for one formally trained CIH-S2S checkpoint. Source data: results/constraint_decoder_analysis_summary.csv and results/constraint_decoder_analysis.csv. Bars show automatic rule flags per 100 score positions, mean decoder runtime per score, and percentage rule-flag change relative to neural argmax; negative values indicate more total automatic flags than argmax. This figure reports automatic diagnostics only; no expert rating, confidence interval, or significance test is included.",
        )
        return {"figure5": str(out.with_suffix(".pdf"))}

    return make_figure5_todo(root, source_dir, caption_dir)


def make_figure5_todo(root: Path, source_dir: Path, caption_dir: Path) -> dict[str, str]:
    matrix = read_csv(root / "results" / "experiment_matrix.csv")
    relevant = [
        row
        for row in matrix
        if row.get("section") == "constraint_decoding_analysis"
        or "constrained" in row.get("model_or_component", "").lower()
        or "beam" in row.get("model_or_component", "").lower()
    ]
    rows = []
    for row in relevant:
        rows.append(
            {
                "figure": "Figure 5",
                "analysis": row.get("model_or_component", ""),
                "task": row.get("task", ""),
                "status": row.get("status", ""),
                "evidence_path": row.get("evidence_path", ""),
                "expected_artifact": row.get("expected_artifact", ""),
                "required_metrics": "local repair, constrained beam, beam size, top-k, runtime, rule reduction",
                "source_file": "results/experiment_matrix.csv",
                "claim_boundary": row.get("claim_boundary", "do not plot until formal CIH constrained-decoder data exist"),
            }
        )
    if not rows:
        rows.append(
            {
                "figure": "Figure 5",
                "analysis": "local repair vs constrained beam search",
                "task": "soprano_to_satb",
                "status": "pending_no_formal_data",
                "evidence_path": "",
                "expected_artifact": "",
                "required_metrics": "beam size, top-k, runtime, rule reduction",
                "source_file": "results/experiment_matrix.csv",
                "claim_boundary": "do not plot until formal CIH constrained-decoder data exist",
            }
        )
    write_csv(source_dir / "figure5_constraint_decoder_todo_source.csv", rows)
    todo = (
        "# Figure 5 TODO: Constraint Decoder Analysis\n\n"
        "No formal local-repair versus constrained-beam comparison with beam size, top-k, runtime, and rule-reduction metrics is available in the current artifacts.\n\n"
        "Required source before plotting: a CSV/JSON result file with matched local-repair and constrained-beam rows from the same model family/checkpoint, including beam_size, top_k, decoding_runtime, rule_flags_per_100, and evaluated_generation count.\n\n"
        "Current boundary: do not draw a quantitative Figure 5 until those data exist.\n"
    )
    (caption_dir / "figure5_constraint_decoder_analysis_TODO.md").write_text(todo, encoding="utf-8")
    return {"figure5": str(caption_dir / "figure5_constraint_decoder_analysis_TODO.md")}


def make_figure6(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    source_rows, excluded = build_training_curve_rows(root)
    write_csv(source_dir / "figure6_training_curves_source.csv", source_rows)
    write_csv(source_dir / "figure6_training_curve_exclusions.csv", excluded)
    if not source_rows:
        write_caption(caption_dir / "figure6_training_curves_caption.md", "Figure 6 was not drawn because no complete non-development training logs with validation CE and validation accuracy were found.")
        return {"figure6": "not_drawn_no_complete_training_logs"}

    models = list(dict.fromkeys(row["model_label"] for row in source_rows))
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), constrained_layout=True)
    for model in models:
        rows = [row for row in source_rows if row["model_label"] == model]
        rows.sort(key=lambda r: int(float(r["epoch"])))
        epochs = [int(float(row["epoch"])) for row in rows]
        val_loss = [float(row["val_loss"]) for row in rows]
        val_acc = [float(row["val_accuracy"]) for row in rows]
        color = PALETTE.get(model, "#666666")
        axes[0].plot(epochs, val_loss, label=model, color=color, lw=1.4)
        axes[1].plot(epochs, val_acc, label=model, color=color, lw=1.4)
    axes[0].set_title("A. Validation CE", loc="left")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Validation CE")
    axes[1].set_title("B. Validation accuracy", loc="left")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Validation accuracy")
    for ax in axes:
        ax.grid(alpha=0.22, linewidth=0.6)
    axes[1].legend(loc="lower right")
    fig.suptitle("Training curves from complete non-development logs", x=0.01, ha="left", fontsize=9, fontweight="bold")
    out = fig_dir / "figure6_training_curves"
    save_all(fig, out)
    plt.close(fig)
    write_caption(
        caption_dir / "figure6_training_curves_caption.md",
        "Figure 6. Validation cross entropy and validation accuracy from complete non-development training logs. Source data: runs/*/metrics.csv, filtered into paper/figures/source_data/figure6_training_curves_source.csv; excluded logs and reasons are listed in figure6_training_curve_exclusions.csv. Curves are descriptive training histories only and include no confidence interval or significance test.",
    )
    return {"figure6": str(out.with_suffix(".pdf"))}


def make_figure7(root: Path, fig_dir: Path, source_dir: Path, caption_dir: Path, plt) -> dict[str, str]:
    summary = read_json(root / "results" / "project1_expert_eval_summary.json")
    packet = read_json(root / "expert_eval" / "project1" / "sci_blind_protocol_packet" / "packet_manifest.json")
    rating_form = read_csv(root / "expert_eval" / "project1" / "sci_blind_protocol_packet" / "rating_form.csv")
    if float(summary.get("absolute_completed_rows", 0) or 0) > 0 and float(summary.get("rating_file_count", 0) or 0) > 0:
        rows = build_expert_result_rows(summary)
        write_csv(source_dir / "figure7_expert_evaluation_source.csv", rows)
        # Reserved for future real expert ratings.
    else:
        rows = build_expert_protocol_rows(packet, rating_form)
        write_csv(source_dir / "figure7_expert_protocol_source.csv", rows)
        fig, axes = plt.subplots(1, 2, figsize=(7.2, 3.2), gridspec_kw={"width_ratios": [1.2, 2.0]}, constrained_layout=True)
        condition_rows = [r for r in rows if r["row_type"] == "condition"]
        labels = [r["label"] for r in condition_rows]
        values = [float(r["count"]) for r in condition_rows]
        axes[0].bar(range(len(labels)), values, color="#9AA9B7", edgecolor="#333333", linewidth=0.35)
        axes[0].set_xticks(range(len(labels)), [short_label(v) for v in labels], rotation=25, ha="right")
        axes[0].set_ylabel("Prepared score count")
        axes[0].set_title("A. Blind packet", loc="left")
        axes[0].grid(axis="y", alpha=0.22, linewidth=0.6)
        axes[1].set_axis_off()
        dim_rows = [r for r in rows if r["row_type"] == "rating_dimension"]
        y = 0.95
        axes[1].text(0.0, y, "B. Rating dimensions (pending returned forms)", fontsize=8, fontweight="bold", va="top")
        y -= 0.12
        for idx, row in enumerate(dim_rows, start=1):
            axes[1].text(0.02, y, f"{idx}. {row['label']}", fontsize=6.7, va="top")
            y -= 0.095
        axes[1].text(0.02, 0.02, "No expert mean, CI, or inter-rater reliability is reported.", fontsize=6.5, color="#6A3D3D")
        fig.suptitle("Blind expert-evaluation protocol prepared; ratings pending", x=0.01, ha="left", fontsize=9, fontweight="bold")
        out = fig_dir / "figure7_expert_protocol"
        save_all(fig, out)
        plt.close(fig)
        write_caption(
            caption_dir / "figure7_expert_protocol_caption.md",
            "Figure 7. Blind expert-evaluation protocol. Source data: expert_eval/project1/sci_blind_protocol_packet/packet_manifest.json and rating_form.csv. The packet contains prepared anonymized conditions and rating dimensions, but no returned expert ratings. Therefore no expert mean, confidence interval, inter-rater reliability, or preference claim is reported.",
        )
        return {"figure7": str(out.with_suffix(".pdf"))}
    write_caption(caption_dir / "figure7_expert_protocol_caption.md", "Figure 7 expert-rating plot pending implementation for returned real ratings.")
    return {"figure7": "pending_real_rating_plot"}


def build_main_result_rows(root: Path = ROOT) -> list[dict[str, str]]:
    metrics = [row for row in read_csv(root / "results" / "project1_metrics.csv") if not is_development_row(row)]
    matrix = read_csv(root / "results" / "experiment_matrix.csv")
    rows: list[dict[str, str]] = []
    for model in PRIMARY_MODELS:
        robustness = find_formal_robustness_row(root, model["key"])
        if robustness:
            robust_row, source_file = robustness
            rows.append(metric_to_result_row(robust_row, model, "formal_multiseed_mean", source_file))
            continue
        if model["key"] == "cih_s2s":
            formal = find_formal_cih_row(root)
            if formal:
                rows.append(metric_to_result_row(formal, model, "formal_result", "results/cih_s2s_robustness_summary.json"))
            else:
                matrix_row = find_matrix_row(matrix, "baseline_cih_s2s_bach_s2s")
                rows.append(
                    {
                        "model_key": model["key"],
                        "model_label": model["label"],
                        "task": model["task"],
                        "pitch_accuracy": "",
                        "cross_entropy": "",
                        "rule_violations_per_100_timesteps": "",
                        "musicxml_export_success_rate": "",
                        "parallel_fifths_per_100_timesteps": "",
                        "parallel_octaves_per_100_timesteps": "",
                        "status": matrix_row.get("status", "pending_formal_result"),
                        "seed_count": model["seed_count"],
                        "source_file": matrix_row.get("evidence_path", "results/cih_s2s_smoke_metrics.json"),
                        "claim_boundary": matrix_row.get("claim_boundary", model["claim_boundary"]),
                    }
                )
            continue
        match = find_metric_row(metrics, model["aliases"], model["task"])
        if match:
            rows.append(metric_to_result_row(match, model, "available", "results/project1_metrics.csv"))
        else:
            rows.append(
                {
                    "model_key": model["key"],
                    "model_label": model["label"],
                    "task": model["task"],
                    "status": "missing",
                    "seed_count": "0",
                    "source_file": "results/project1_metrics.csv",
                    "claim_boundary": "required row not found",
                }
            )
    return rows


def build_ablation_rows(root: Path = ROOT) -> list[dict[str, str]]:
    metrics = [row for row in read_csv(root / "results" / "project1_metrics.csv") if not is_development_row(row)]
    matrix = read_csv(root / "results" / "experiment_matrix.csv")
    rows: list[dict[str, str]] = []
    for variant in ABLATION_VARIANTS:
        match = find_metric_row(metrics, variant["aliases"], variant["task"])
        if match:
            row = metric_to_result_row(match, {"key": variant["key"], "label": variant["label"], "task": variant["task"], "seed_count": "1", "claim_boundary": variant["claim_boundary"]}, "available", "results/project1_metrics.csv")
            row["variant_key"] = variant["key"]
            row["variant_label"] = variant["label"]
            rows.append(row)
        else:
            exp_id = "ablation_no_constrained_decoding_cih" if variant["key"] == "no_constrained_decoding" else ""
            matrix_row = find_matrix_row(matrix, exp_id) if exp_id else {}
            rows.append(
                {
                    "variant_key": variant["key"],
                    "variant_label": variant["label"],
                    "task": variant["task"],
                    "pitch_accuracy": "",
                    "cross_entropy": "",
                    "rule_violations_per_100_timesteps": "",
                    "parallel_octaves_per_100_timesteps": "",
                    "status": matrix_row.get("status", "pending_or_missing"),
                    "source_file": matrix_row.get("evidence_path", "results/experiment_matrix.csv"),
                    "seed_count": str(matrix_row.get("seeds_available", "0")),
                    "claim_boundary": matrix_row.get("claim_boundary", variant["claim_boundary"]),
                }
            )
    return rows


def build_rule_diagnostic_rows(root: Path = ROOT) -> list[dict[str, str]]:
    metric_rows = build_main_result_rows(root)
    metrics_by_label = {row["model_label"]: row for row in metric_rows}
    rule_rows = read_csv(root / "results" / "project1_rule_violations.csv")
    out: list[dict[str, str]] = []
    for label in ["Vanilla Transformer", "Current rule-guided"]:
        model_row = metrics_by_label[label]
        raw_model = model_row.get("raw_model", "")
        for rule, rule_label in RULES:
            rr = find_rule_row(rule_rows, raw_model, rule)
            out.append(
                {
                    "figure": "Figure 3",
                    "model_label": label,
                    "model": raw_model,
                    "task": model_row.get("task", "soprano_to_satb"),
                    "diagnostic": rule,
                    "diagnostic_label": rule_label,
                    "value": rr.get("per_100_timesteps", "") if rr else "",
                    "unit": "flags per 100 score positions",
                    "source_file": "results/project1_rule_violations.csv",
                    "seed_count": model_row["seed_count"],
                    "claim_boundary": "automatic rule diagnostic; no expert-rating claim",
                }
            )
        out.append(
            {
                "figure": "Figure 3",
                "model_label": label,
                "model": raw_model,
                "task": model_row.get("task", "soprano_to_satb"),
                "diagnostic": "cadence_unknown_rate",
                "diagnostic_label": "Cadence unknown",
                "value": model_row.get("cadence_unknown_rate", ""),
                "unit": "rate",
                "source_file": "results/project1_metrics.csv",
                "seed_count": model_row["seed_count"],
                "claim_boundary": "automatic cadence diagnostic; no expert-rating claim",
            }
        )
    return out


def build_training_curve_rows(root: Path = ROOT) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    selected = {
        "chorale_lstm": "LSTM",
        "chorale_transformer_no_constraints": "Vanilla Transformer",
        "chorale_rule_guided_decoding": "Current rule-guided",
    }
    source_rows: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    for metrics_path in sorted((root / "runs").rglob("metrics.csv")):
        run = metrics_path.parent.name
        rel_run = str(metrics_path.parent.relative_to(root / "runs")).replace("\\", "/")
        nested_label = training_curve_label_from_path(rel_run)
        model_label = selected.get(run, nested_label)
        rows = read_csv(metrics_path)
        complete = is_complete_training_log(rows)
        if model_label and complete and not is_development_name(rel_run):
            for row in rows:
                source_rows.append(
                    {
                        "figure": "Figure 6",
                        "run": rel_run,
                        "model_label": model_label,
                        "epoch": row.get("epoch", ""),
                        "train_loss": row.get("train_loss", ""),
                        "val_loss": row.get("val_loss", ""),
                        "val_accuracy": row.get("val_accuracy", ""),
                        "source_file": str(metrics_path.relative_to(root)),
                        "selection_role": "complete non-development primary training log",
                        "seed_count": "1 training trajectory",
                        "claim_boundary": "training history only; not a significance test",
                    }
                )
        else:
            reason = "not selected primary run"
            if is_development_name(run):
                reason = "development or software-check run"
            elif not complete:
                reason = "missing epoch, val_loss, or val_accuracy, or too few epochs"
            excluded.append({"run": rel_run, "metrics_path": str(metrics_path.relative_to(root)), "excluded_reason": reason})
    return source_rows, excluded


def training_curve_label_from_path(rel_run: str) -> str:
    if rel_run.startswith("vanilla_transformer_formal_multiseed/seed_2026"):
        return "Vanilla Transformer"
    if rel_run.startswith("cih_s2s_formal_multiseed/seed_2026"):
        return "CIH-S2S"
    if rel_run.startswith("project1_formal_multiseed/seed_2026"):
        return "Current rule-guided"
    return ""


def build_expert_protocol_rows(packet: dict, rating_form: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    conditions = packet.get("conditions", {})
    for condition, count in conditions.items():
        rows.append(
            {
                "figure": "Figure 7",
                "row_type": "condition",
                "label": condition,
                "count": str(count),
                "status": packet.get("status", "pending_completed_ratings"),
                "source_file": "expert_eval/project1/sci_blind_protocol_packet/packet_manifest.json",
                "claim_boundary": "protocol only; no expert rating result",
            }
        )
    dimension_columns = []
    if rating_form:
        dimension_columns = [
            col
            for col in rating_form[0].keys()
            if col not in {"rater_id", "score_id", "comments"} and col.endswith("_1_to_5")
        ]
    for col in dimension_columns:
        rows.append(
            {
                "figure": "Figure 7",
                "row_type": "rating_dimension",
                "label": col.replace("_1_to_5", "").replace("_", " "),
                "count": "",
                "status": "pending_completed_ratings",
                "source_file": "expert_eval/project1/sci_blind_protocol_packet/rating_form.csv",
                "claim_boundary": "protocol dimension only; no expert mean or CI",
            }
        )
    return rows


def build_expert_result_rows(summary: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for metric, values in (summary.get("absolute") or {}).items():
        rows.append(
            {
                "figure": "Figure 7",
                "row_type": "expert_result",
                "label": metric,
                "count": str(values.get("n", "")),
                "mean": str(values.get("mean", "")),
                "status": summary.get("status", "completed"),
                "source_file": "results/project1_expert_eval_summary.json",
                "claim_boundary": "expert rating result; CI requires returned-score distribution",
            }
        )
    return rows


def metric_to_result_row(metric: dict[str, str], model: dict, status: str, source_file: str) -> dict[str, str]:
    return {
        "model_key": model["key"],
        "model_label": model["label"],
        "raw_model": metric.get("model", ""),
        "task": metric.get("task", model.get("task", "")),
        "pitch_accuracy": metric.get("pitch_accuracy", metric.get("pitch_token_accuracy", "")),
        "cross_entropy": metric.get("cross_entropy", ""),
        "negative_log_likelihood": metric.get("negative_log_likelihood", ""),
        "rule_violations_per_100_timesteps": metric.get("rule_violations_per_100_timesteps", ""),
        "parallel_fifths_per_100_timesteps": metric.get("parallel_fifths_per_100_timesteps", ""),
        "parallel_octaves_per_100_timesteps": metric.get("parallel_octaves_per_100_timesteps", ""),
        "cadence_unknown_rate": metric.get("cadence_unknown_rate", ""),
        "musicxml_export_success_rate": metric.get("musicxml_export_success_rate", ""),
        "status": status,
        "seed_count": metric.get("seed_count", model.get("seed_count", "1")),
        "source_file": source_file,
        "claim_boundary": model.get("claim_boundary", ""),
    }


def find_metric_row(rows: list[dict[str, str]], aliases: set[str], task: str) -> dict[str, str] | None:
    lowered = {a.lower() for a in aliases}
    candidates = [
        row
        for row in rows
        if row.get("model", "").lower() in lowered
        or any(row.get("model", "").lower().startswith(alias) for alias in lowered)
    ]
    candidates = [row for row in candidates if not task or row.get("task", task) == task]
    if not candidates:
        return None
    return sorted(candidates, key=preference_score, reverse=True)[0]


def find_rule_row(rows: list[dict[str, str]], model: str, rule: str) -> dict[str, str] | None:
    for row in rows:
        if row.get("model") == model and row.get("rule") == rule:
            return row
    return None


def find_matrix_row(rows: list[dict[str, str]], experiment_id: str) -> dict[str, str]:
    for row in rows:
        if row.get("experiment_id") == experiment_id:
            return row
    return {}


def find_formal_robustness_row(root: Path, model_key: str) -> tuple[dict[str, str], str] | None:
    paths = {
        "vanilla_transformer": root / "results" / "vanilla_transformer_robustness_summary.json",
        "current_rule_guided": root / "results" / "project1_robustness_summary.json",
        "cih_s2s": root / "results" / "cih_s2s_robustness_summary.json",
    }
    path = paths.get(model_key)
    if path is None:
        return None
    data = read_json(path)
    if not data.get("formal_robustness_evidence") or not data.get("aggregates"):
        return None
    rows = data.get("rows", [])
    first_row = rows[0] if rows else {}
    aggregates = data["aggregates"]
    row = {
        "model": first_row.get("model", model_key),
        "task": first_row.get("task", "soprano_to_satb"),
        "seed_count": str(data.get("seed_count", "")),
        "pitch_accuracy": mean_from_aggregate(aggregates, "pitch_accuracy"),
        "cross_entropy": mean_from_aggregate(aggregates, "cross_entropy"),
        "negative_log_likelihood": mean_from_aggregate(aggregates, "cross_entropy"),
        "rule_violations_per_100_timesteps": mean_from_aggregate(aggregates, "rule_violations_per_100_timesteps"),
        "parallel_fifths_per_100_timesteps": mean_from_aggregate(aggregates, "parallel_fifths_per_100_timesteps"),
        "parallel_octaves_per_100_timesteps": mean_from_aggregate(aggregates, "parallel_octaves_per_100_timesteps"),
        "cadence_unknown_rate": mean_from_aggregate(aggregates, "cadence_unknown_rate"),
        "musicxml_export_success_rate": mean_from_aggregate(aggregates, "musicxml_export_success_rate"),
    }
    return row, str(path.relative_to(root))


def find_formal_cih_row(root: Path) -> dict[str, str] | None:
    robustness = read_json(root / "results" / "cih_s2s_robustness_summary.json")
    if robustness.get("formal_robustness_evidence") and robustness.get("aggregates"):
        aggregates = robustness["aggregates"]
        row = {
            "model": "cih_s2s_transformer_4060ti_16gb_multiseed_mean",
            "task": "soprano_to_satb",
            "seed_count": str(robustness.get("seed_count", "")),
            "pitch_accuracy": mean_from_aggregate(aggregates, "pitch_accuracy"),
            "cross_entropy": mean_from_aggregate(aggregates, "cross_entropy"),
            "negative_log_likelihood": mean_from_aggregate(aggregates, "cross_entropy"),
            "rule_violations_per_100_timesteps": mean_from_aggregate(aggregates, "rule_violations_per_100_timesteps"),
            "parallel_fifths_per_100_timesteps": mean_from_aggregate(aggregates, "parallel_fifths_per_100_timesteps"),
            "parallel_octaves_per_100_timesteps": mean_from_aggregate(aggregates, "parallel_octaves_per_100_timesteps"),
            "cadence_unknown_rate": mean_from_aggregate(aggregates, "cadence_unknown_rate"),
            "musicxml_export_success_rate": mean_from_aggregate(aggregates, "musicxml_export_success_rate"),
        }
        return row
    for path in [root / "results" / "cih_s2s_metrics.json", root / "results" / "cih_s2s_4060ti_metrics.json"]:
        data = read_json(path)
        if data and not is_development_name(str(data.get("model", ""))) and "smoke" not in str(path).lower():
            row = {k: json.dumps(v) if isinstance(v, (dict, list)) else str(v) for k, v in data.items()}
            row["model"] = row.get("model", "cih_s2s_transformer")
            return row
    return None


def mean_from_aggregate(aggregates: dict, key: str) -> str:
    value = aggregates.get(key, {})
    if isinstance(value, dict) and value.get("mean") is not None:
        return str(value["mean"])
    return ""


def preference_score(row: dict[str, str]) -> int:
    text = " ".join(str(row.get(k, "")) for k in ["model", "checkpoint", "source"]).lower()
    score = 0
    if "enhanced" in text:
        score += 100
    if "rerankfix" in text:
        score -= 30
    if "smoke" in text or "fastcheck" in text:
        score -= 200
    return score


def is_development_row(row: dict[str, str]) -> bool:
    return any(is_development_name(str(row.get(k, ""))) for k in ["model", "checkpoint", "source", "evidence_level"])


def is_development_name(value: str) -> bool:
    lowered = value.lower()
    return any(token in lowered for token in ["smoke", "fastcheck", "fastdev", "software_check"])


def is_complete_training_log(rows: list[dict[str, str]]) -> bool:
    if len(rows) < 5:
        return False
    required = {"epoch", "val_loss", "val_accuracy"}
    return all(required.issubset(row.keys()) and row.get("val_loss") and row.get("val_accuracy") for row in rows)


def constraint_decoder_status(upgrade: dict) -> str:
    rows = upgrade.get("rows", [])
    backends = sorted({str(row.get("constraint_decoder", "")) for row in rows if row.get("constraint_decoder")})
    return ", ".join(backends) if backends else "constraint decoder status unavailable"


def find_value(rows: list[dict[str, str]], model_label: str, diagnostic: str) -> str:
    for row in rows:
        if row.get("model_label") == model_label and row.get("diagnostic") == diagnostic:
            return row.get("value", "")
    return ""


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_caption(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_figure_manifest(root: Path, generated: dict[str, str]) -> None:
    rows = [
        {
            "figure": key,
            "artifact": relpath(root, value),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "script": "scripts/make_paper_figures.py",
        }
        for key, value in generated.items()
    ]
    write_csv(root / "paper" / "figures" / "source_data" / "figure_generation_manifest.csv", rows)


def save_all(fig, base: Path) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".png"), dpi=300, bbox_inches="tight")
    fig.savefig(base.with_name(base.name + "_600dpi").with_suffix(".png"), dpi=600, bbox_inches="tight")


def to_float(value: object) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def short_label(label: str) -> str:
    replacements = {
        "Vanilla Transformer": "Vanilla",
        "Current rule-guided": "Current",
        "No voice relation": "No voice\nrelation",
        "No constrained decoding": "No constrained\ndecoding",
    }
    return replacements.get(label, label)


def wrap_label(text: str, width: int) -> str:
    words = str(text).split()
    lines: list[str] = []
    current: list[str] = []
    for word in words:
        if sum(len(w) for w in current) + len(current) + len(word) > width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def relpath(root: Path, value: str) -> str:
    if not value:
        return ""
    try:
        path = Path(value)
        if path.is_absolute():
            return str(path.relative_to(root))
    except ValueError:
        return value
    return value


if __name__ == "__main__":
    main()
