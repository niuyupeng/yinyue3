from __future__ import annotations

import argparse
import csv
from datetime import datetime
from pathlib import Path
import platform
import sys

PRIMARY_MODEL_ORDER = [
    ("lstm_baseline", "LSTM"),
    ("transformer_no_constraints", "Vanilla"),
    ("proposed_neural_symbolic_rule_guided", "Proposed"),
]

MODEL_ORDER = [
    ("lstm_baseline", "LSTM"),
    ("transformer_no_constraints", "Vanilla"),
    ("proposed_neural_symbolic_rule_guided", "Proposed"),
    ("ablation_no_harmony_conditioning", "No harmony"),
    ("ablation_no_iterative_refinement", "No refinement"),
    ("ablation_no_rule_guided_decoding", "No rules"),
]

RUN_ORDER = [
    ("chorale_lstm_full_20260615_085410", "LSTM"),
    ("chorale_transformer_no_constraints", "Vanilla"),
    ("chorale_rule_guided_decoding", "Proposed"),
    ("chorale_ablation_no_harmony", "No harmony"),
    ("chorale_ablation_no_rule_guided_decoding", "No rules"),
]

PALETTE = {
    "LSTM": "#767676",
    "Vanilla": "#7884B4",
    "Proposed": "#0F4D92",
    "No harmony": "#B4C0E4",
    "No refinement": "#93A4D8",
    "No rules": "#B64342",
}

LINE_STYLES = {
    "LSTM": "-",
    "Vanilla": "--",
    "Proposed": "-",
    "No harmony": ":",
    "No refinement": "-.",
    "No rules": (0, (4, 2)),
}

DELTA_COLORS = {
    "improved": "#2E7D45",
    "worse": "#B64342",
    "neutral": "#767676",
}

CONFIG_BY_MODEL = {
    "lstm_baseline": "configs/chorale_lstm.yaml",
    "transformer_no_constraints": "configs/chorale_transformer_no_constraints.yaml",
    "proposed_neural_symbolic_rule_guided": "configs/chorale_rule_guided_decoding.yaml",
    "ablation_no_harmony_conditioning": "configs/chorale_main.yaml",
    "ablation_no_iterative_refinement": "configs/chorale_main.yaml",
    "ablation_no_rule_guided_decoding": "configs/chorale_transformer_no_constraints.yaml",
    "masked_infilling": "configs/chorale_masked_infilling.yaml",
    "soprano_to_satb": "configs/chorale_soprano_to_satb.yaml",
}

PROJECT_METADATA = {
    "seed": "2026",
    "train_count": "297",
    "val_count": "37",
    "test_count": "37",
    "n_definition": "37 held-out music21 Bach chorales in the deterministic test split",
    "center": "single evaluation run",
    "spread": "not applicable; no repeated seeds logged",
    "statistical_test": "not performed",
    "hardware": "NVIDIA GeForce RTX 4060 Ti 16GB; Intel i5-12400F; 16GB RAM; Windows 11 Professional 64-bit",
}


def plot_project1_results(
    metrics_csv: str | Path = "results/project1_metrics.csv",
    output_dir: str | Path = "paper/figures",
    runs_dir: str | Path = "runs",
    rule_csv: str | Path = "results/project1_rule_violations.csv",
) -> dict[str, str]:
    import matplotlib.pyplot as plt

    apply_publication_style(plt)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: dict[str, str] = {}

    metric_rows = read_csv(Path(metrics_csv))
    non_smoke_metrics = [row for row in metric_rows if not is_smoke_row(row)]
    if non_smoke_metrics:
        paths["summary"] = str(plot_metric_summary(non_smoke_metrics, output_dir / "project1_metrics_summary.png", plt, Path(rule_csv)))
    else:
        paths["summary"] = str(write_note_figure(output_dir / "project1_metrics_summary.png", "Full RTX metric rows not available", "No non-smoke rows were found in results/project1_metrics.csv.", plt))

    paths["training_curves"] = str(plot_training_curves(Path(runs_dir), output_dir / "project1_training_curves.png", plt))
    paths["rule_violations_bar"] = str(plot_rule_violations(Path(rule_csv), output_dir / "project1_rule_violations_bar.png", plt))
    paths["method"] = str(make_method_figure(output_dir / "project1_method_figure.png"))
    write_source_data(output_dir / "source_data", non_smoke_metrics, Path(rule_csv), Path(runs_dir))
    write_qa_note(output_dir / "project1_figure_qa.md")
    return paths


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def plot_metric_summary(rows: list[dict[str, str]], output_path: Path, plt, rule_csv: Path) -> Path:
    import numpy as np

    row_by_model = {row.get("model", ""): row for row in rows}
    primary = [(model, label, row_by_model[model]) for model, label in PRIMARY_MODEL_ORDER if model in row_by_model]
    fig = plt.figure(figsize=(7.1, 4.45), constrained_layout=True)
    gs = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.0], height_ratios=[1.0, 1.0])
    ax_a = fig.add_subplot(gs[0, 0])
    ax_b = fig.add_subplot(gs[0, 1])
    ax_c = fig.add_subplot(gs[1, 0])
    ax_d = fig.add_subplot(gs[1, 1])

    for model, label, row in primary:
        x_val = float_or_zero(row.get("cross_entropy"))
        y_val = float_or_zero(row.get("pitch_accuracy"))
        size = 68 if label == "Proposed" else 44
        ax_a.scatter(x_val, y_val, s=size, color=PALETTE[label], edgecolor="#272727", linewidth=0.5, zorder=3)
        dx, dy = {
            "LSTM": (0.010, 0.0015),
            "Vanilla": (0.010, -0.004),
            "Proposed": (-0.070, 0.0015),
        }.get(label, (0.008, 0.001))
        ax_a.text(x_val + dx, y_val + dy, label, fontsize=6.3, va="center")
    ax_a.set_xlim(0.52, 0.93)
    ax_a.set_ylim(0.755, 0.835)
    ax_a.set_xlabel("Cross entropy (lower is better)")
    ax_a.set_ylabel("Pitch accuracy")
    ax_a.grid(alpha=0.18, linewidth=0.5)
    ax_a.set_title("Prediction trade-off", loc="left", fontsize=7, pad=3)

    ablation_models = [
        ("proposed_neural_symbolic_rule_guided", "Full"),
        ("ablation_no_harmony_conditioning", "No harmony"),
        ("ablation_no_iterative_refinement", "No refinement"),
        ("ablation_no_rule_guided_decoding", "No rules"),
    ]
    full = row_by_model.get("proposed_neural_symbolic_rule_guided", {})
    full_ce = float_or_zero(full.get("cross_entropy"))
    full_acc = float_or_zero(full.get("pitch_accuracy"))
    ab_rows = [
        (label, row_by_model[model])
        for model, label in ablation_models[1:]
        if model in row_by_model
    ]
    ab_labels = [label for label, _ in ab_rows]
    ce_delta = [float_or_zero(row.get("cross_entropy")) - full_ce for _, row in ab_rows]
    acc_delta_pp = [(float_or_zero(row.get("pitch_accuracy")) - full_acc) * 100.0 for _, row in ab_rows]
    y = np.arange(len(ab_labels))
    colors_b = [DELTA_COLORS["worse"] if value > 0.002 else DELTA_COLORS["neutral"] for value in ce_delta]
    ax_b.axvline(0, color="#272727", linewidth=0.7)
    ax_b.barh(y, ce_delta, color=colors_b, edgecolor="#272727", linewidth=0.4)
    ax_b.set_yticks(y)
    ax_b.set_yticklabels(ab_labels)
    ax_b.invert_yaxis()
    ax_b.set_xlim(-0.02, max(ce_delta) * 1.25 if ce_delta else 0.1)
    ax_b.set_xlabel("Cross-entropy change vs full model")
    ax_b.grid(axis="x", alpha=0.18, linewidth=0.5)
    ax_b.set_title("Ablation penalty", loc="left", fontsize=7, pad=3)
    for yi, d_ce, d_acc in zip(y, ce_delta, acc_delta_pp):
        ax_b.text(d_ce + 0.006, yi, f"{d_ce:+.3f} CE; {d_acc:+.2f} pp acc.", va="center", fontsize=5.8)

    vanilla = row_by_model.get("transformer_no_constraints", {})
    proposed = row_by_model.get("proposed_neural_symbolic_rule_guided", {})
    targeted = [
        ("Parallel fifths", "parallel_fifths_per_100_timesteps"),
        ("Crossing", "voice_crossing_rate"),
        ("Spacing", "spacing_violation_rate"),
        ("Seventh resolution", "seventh_resolution_violation_rate"),
    ]
    names, changes = [], []
    for name, key in targeted:
        base = float_or_zero(vanilla.get(key))
        new = float_or_zero(proposed.get(key))
        change = 0.0 if base == 0 else 100.0 * (new - base) / base
        names.append(name)
        changes.append(change)
    yy = np.arange(len(names))
    ax_c.axvline(0, color="#272727", linewidth=0.7)
    ax_c.barh(yy, changes, color=[DELTA_COLORS["improved"] if v < 0 else DELTA_COLORS["worse"] for v in changes], edgecolor="#272727", linewidth=0.35)
    ax_c.set_yticks(yy)
    ax_c.set_yticklabels(names)
    ax_c.invert_yaxis()
    ax_c.set_xlabel("Change vs vanilla, fewer is better (%)")
    ax_c.set_xlim(-100, 80)
    ax_c.grid(axis="x", alpha=0.18, linewidth=0.5)
    ax_c.set_title("Targeted rule changes", loc="left", fontsize=7, pad=3)
    for yi, value in zip(yy, changes):
        align = "right" if value < 0 else "left"
        offset = -3 if value < 0 else 3
        ax_c.text(value + offset, yi, f"{value:+.0f}%", va="center", ha=align, fontsize=6)

    tradeoffs = [
        ("Total violations", "rule_violations_per_100_timesteps"),
        ("Parallel octaves", "parallel_octaves_per_100_timesteps"),
        ("Leading tone", None),
    ]
    rule_rows = [row for row in read_csv(rule_csv) if not is_smoke_row(row)]
    rule_map = {(row.get("model", ""), row.get("rule", "")): row for row in rule_rows}
    trade_names, trade_changes = [], []
    for name, key in tradeoffs:
        if key is None:
            base = float_or_zero(rule_map.get(("transformer_no_constraints", "leading_tone_resolution"), {}).get("per_100_timesteps"))
            new = float_or_zero(rule_map.get(("proposed_neural_symbolic_rule_guided", "leading_tone_resolution"), {}).get("per_100_timesteps"))
        else:
            base = float_or_zero(vanilla.get(key))
            new = float_or_zero(proposed.get(key))
        change = 0.0 if base == 0 else 100.0 * (new - base) / base
        trade_names.append(name)
        trade_changes.append(change)
    yy = np.arange(len(trade_names))
    ax_d.axvline(0, color="#272727", linewidth=0.7)
    ax_d.barh(yy, trade_changes, color=[DELTA_COLORS["improved"] if v < 0 else DELTA_COLORS["worse"] for v in trade_changes], edgecolor="#272727", linewidth=0.35)
    ax_d.set_yticks(yy)
    ax_d.set_yticklabels(trade_names)
    ax_d.invert_yaxis()
    ax_d.set_xlim(-40, 80)
    ax_d.set_xlabel("Change vs vanilla, fewer is better (%)")
    ax_d.grid(axis="x", alpha=0.18, linewidth=0.5)
    ax_d.set_title("Unresolved trade-offs", loc="left", fontsize=7, pad=3)
    for yi, value in zip(yy, trade_changes):
        ax_d.text(value + 3, yi, f"{value:+.0f}%", va="center", ha="left", fontsize=6)

    for panel, ax in zip("abcd", [ax_a, ax_b, ax_c, ax_d]):
        add_panel_label(ax, panel)
    save_all_formats(fig, output_path, plt)
    plt.close(fig)
    return output_path


def plot_training_curves(runs_dir: Path, output_path: Path, plt) -> Path:
    histories: list[tuple[str, str, list[dict[str, str]]]] = []
    if runs_dir.exists():
        for run_name, label in RUN_ORDER:
            metrics_path = runs_dir / run_name / "metrics.csv"
            rows = read_csv(metrics_path)
            if rows:
                histories.append((run_name, label, rows))

    if not histories:
        return write_note_figure(output_path, "Training curves not available", "No runs/*/metrics.csv files were found.", plt)

    fig, axes = plt.subplots(1, 2, figsize=(7.1, 2.65), constrained_layout=True)
    for _, label, rows in histories:
        epochs = [int(float(row.get("epoch", idx + 1))) for idx, row in enumerate(rows)]
        val_loss = [float_or_none(row.get("val_loss")) for row in rows]
        val_acc = [float_or_none(row.get("val_accuracy")) for row in rows]
        color = PALETTE.get(label, "#767676")
        style = LINE_STYLES.get(label, "-")
        if any(value is not None for value in val_loss):
            axes[0].plot(epochs, val_loss, linewidth=1.35, linestyle=style, label=label, color=color)
        if any(value is not None for value in val_acc):
            axes[1].plot(epochs, val_acc, linewidth=1.35, linestyle=style, label=label, color=color)
    label_offsets = {
        "LSTM": (0.6, 0.000),
        "Vanilla": (0.6, -0.003),
        "Proposed": (0.6, 0.006),
        "No harmony": (0.6, -0.008),
        "No rules": (0.6, -0.012),
    }
    for _, label, rows in histories:
        epochs = [int(float(row.get("epoch", idx + 1))) for idx, row in enumerate(rows)]
        color = PALETTE.get(label, "#767676")
        annotate_last_point(axes[0], epochs, [float_or_none(row.get("val_loss")) for row in rows], label, color, label_offsets.get(label, (0.5, 0.0)))
        annotate_last_point(axes[1], epochs, [float_or_none(row.get("val_accuracy")) for row in rows], label, color, label_offsets.get(label, (0.5, 0.0)))

    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Validation cross entropy")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Validation accuracy")
    axes[1].set_ylim(0.70, 0.86)
    axes[0].set_xlim(0, 54)
    axes[1].set_xlim(0, 54)
    for idx, ax in enumerate(axes):
        ax.grid(alpha=0.18, linewidth=0.5)
        add_panel_label(ax, chr(ord("a") + idx))
    axes[0].set_title("Validation loss", loc="left", fontsize=7, pad=3)
    axes[1].set_title("Validation accuracy", loc="left", fontsize=7, pad=3)
    save_all_formats(fig, output_path, plt)
    plt.close(fig)
    return output_path


def plot_rule_violations(rule_csv: Path, output_path: Path, plt) -> Path:
    import numpy as np
    import matplotlib.colors as mcolors

    rows = [row for row in read_csv(rule_csv) if not is_smoke_row(row)]
    if not rows:
        return write_note_figure(output_path, "Rule-violation bars not available", "No non-smoke rows were found in results/project1_rule_violations.csv.", plt)

    row_map = {(row.get("model", ""), row.get("rule", "")): row for row in rows}
    model_keys = [
        ("transformer_no_constraints", "Vanilla"),
        ("proposed_neural_symbolic_rule_guided", "Proposed"),
        ("ablation_no_harmony_conditioning", "No harmony"),
        ("ablation_no_rule_guided_decoding", "No rules"),
    ]
    rule_keys = [
        ("parallel_fifth", "Parallel\nfifths"),
        ("parallel_octave", "Parallel\noctaves"),
        ("leading_tone_resolution", "Leading tone"),
        ("voice_crossing", "Crossing"),
        ("spacing", "Spacing"),
        ("seventh_resolution", "Seventh\nresolution"),
    ]
    matrix = np.array(
        [
            [float_or_zero(row_map.get((model, rule), {}).get("per_100_timesteps")) for model, _ in model_keys]
            for rule, _ in rule_keys
        ],
        dtype=float,
    )
    row_max = np.maximum(matrix.max(axis=1, keepdims=True), 1e-12)
    normalized = matrix / row_max
    fig = plt.figure(figsize=(7.1, 3.35), constrained_layout=True)
    gs = fig.add_gridspec(1, 2, width_ratios=[1.35, 1.0])
    ax = fig.add_subplot(gs[0, 0])
    ax_delta = fig.add_subplot(gs[0, 1])
    cmap = mcolors.LinearSegmentedColormap.from_list("rule_heat", ["#F7F7F7", "#B4C0E4", "#0F4D92"])
    ax.imshow(normalized, cmap=cmap, vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(np.arange(len(model_keys)))
    ax.set_xticklabels([label for _, label in model_keys], rotation=25, ha="right")
    ax.set_yticks(np.arange(len(rule_keys)))
    ax.set_yticklabels([label for _, label in rule_keys])
    ax.set_title("Rule counts per 100 score positions", loc="left", fontsize=7, pad=3)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            text_color = "white" if normalized[i, j] > 0.62 else "#272727"
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", fontsize=5.6, color=text_color)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.tick_params(length=0)

    vanilla_idx = 0
    proposed_idx = 1
    changes = []
    names = []
    for idx, (_, label) in enumerate(rule_keys):
        base = matrix[idx, vanilla_idx]
        new = matrix[idx, proposed_idx]
        changes.append(0.0 if base == 0 else 100.0 * (new - base) / base)
        names.append(label)
    y = np.arange(len(names))
    ax_delta.axvline(0, color="#272727", linewidth=0.7)
    ax_delta.barh(y, changes, color=[DELTA_COLORS["improved"] if v < 0 else DELTA_COLORS["worse"] for v in changes], edgecolor="#272727", linewidth=0.35)
    ax_delta.set_yticks(y)
    ax_delta.set_yticklabels(names)
    ax_delta.invert_yaxis()
    ax_delta.set_xlim(-100, 80)
    ax_delta.set_xlabel("Proposed vs vanilla, fewer is better (%)")
    ax_delta.set_title("Directional change", loc="left", fontsize=7, pad=3)
    ax_delta.grid(axis="x", alpha=0.18, linewidth=0.5)
    for yi, value in zip(y, changes):
        align = "right" if value < 0 else "left"
        offset = -3 if value < 0 else 3
        ax_delta.text(value + offset, yi, f"{value:+.0f}%", va="center", ha=align, fontsize=5.8)
    add_panel_label(ax, "a")
    add_panel_label(ax_delta, "b")
    save_all_formats(fig, output_path, plt)
    plt.close(fig)
    return output_path


def write_note_figure(output_path: Path, title: str, message: str, plt) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(7.2, 2.8), constrained_layout=True)
    ax.set_axis_off()
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=13, weight="bold")
    ax.text(0.5, 0.38, message, ha="center", va="center", fontsize=10)
    fig.savefig(output_path, dpi=220, bbox_inches="tight")
    plt.close(fig)
    return output_path


def make_method_figure(output_path: str | Path) -> Path:
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    apply_publication_style(plt)
    labels = [
        "Soprano, bass\nor Roman plan",
        "Score\ntokenizer",
        "Neural-symbolic\nTransformer",
        "Rule-guided\ndecoding",
        "SATB MusicXML\nand report",
    ]
    fig, ax = plt.subplots(figsize=(7.1, 1.8))
    ax.set_axis_off()
    xs = [0.11, 0.30, 0.50, 0.70, 0.89]
    fills = ["#F7F7F7", "#E8EEF8", "#DCE7F3", "#EAF4EA", "#F7F7F7"]
    for x, label, fill in zip(xs, labels, fills):
        box = FancyBboxPatch(
            (x - 0.074, 0.34),
            0.148,
            0.34,
            boxstyle="round,pad=0.018,rounding_size=0.018",
            linewidth=0.8,
            facecolor=fill,
            edgecolor="#272727",
        )
        ax.add_patch(box)
        ax.text(x, 0.51, label, ha="center", va="center", fontsize=7)
    for x0, x1 in zip(xs[:-1], xs[1:]):
        ax.add_patch(FancyArrowPatch((x0 + 0.083, 0.51), (x1 - 0.083, 0.51), arrowstyle="->", mutation_scale=9, linewidth=0.8, color="#272727"))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    save_all_formats(fig, output_path, plt)
    plt.close(fig)
    return output_path


def add_panel_label(ax, label: str) -> None:
    ax.text(-0.12, 1.08, label, transform=ax.transAxes, fontsize=8, fontweight="bold", va="top", ha="left")


def annotate_last_point(ax, x_values: list[int], y_values: list[float | None], label: str, color: str, offset: tuple[float, float] = (0.5, 0.0)) -> None:
    pairs = [(x, y) for x, y in zip(x_values, y_values) if y is not None]
    if not pairs:
        return
    x, y = pairs[-1]
    ax.text(x + offset[0], y + offset[1], label, color=color, fontsize=5.8, va="center", ha="left")


def ordered_metric_rows(rows: list[dict[str, str]]) -> list[tuple[str, str, dict[str, str]]]:
    by_model = {row.get("model", ""): row for row in rows}
    selected: list[tuple[str, str, dict[str, str]]] = []
    for model, label in MODEL_ORDER:
        row = by_model.get(model)
        if row:
            selected.append((model, label, row))
    return selected


def apply_publication_style(plt) -> None:
    plt.rcParams["font.family"] = "sans-serif"
    plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["pdf.fonttype"] = 42
    plt.rcParams["font.size"] = 7
    plt.rcParams["axes.spines.right"] = False
    plt.rcParams["axes.spines.top"] = False
    plt.rcParams["axes.linewidth"] = 0.7
    plt.rcParams["legend.frameon"] = False


def save_all_formats(fig, output_path: Path, plt, dpi: int = 450) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    base = output_path.with_suffix("")
    fig.savefig(base.with_suffix(".png"), dpi=dpi, bbox_inches="tight")
    fig.savefig(base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(base.with_suffix(".svg"), bbox_inches="tight")
    # Compatibility note: Matplotlib/Pillow can fail when overwriting large TIFF
    # files on Windows. The submission-critical vector exports above remain the
    # primary artifacts; TIFF is written as an additional raster copy and any
    # failure is recorded explicitly for reproducibility.
    tiff_path = base.with_suffix(".tiff")
    warning_path = base.with_name(f"{base.name}_tiff_export_warning.txt")
    try:
        if tiff_path.exists():
            tiff_path.unlink()
        fig.savefig(tiff_path, dpi=600, bbox_inches="tight")
        old_tif = base.with_suffix(".tif")
        if old_tif.exists():
            old_tif.unlink()
        if warning_path.exists():
            warning_path.unlink()
    except OSError as exc:
        warning_path.write_text(
            f"TIFF export failed for {base.name}: {exc}\n"
            "PNG, PDF, and SVG exports were written before this optional raster export.\n",
            encoding="utf-8",
        )


def write_source_data(output_dir: Path, metrics_rows: list[dict[str, str]], rule_csv: Path, runs_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    if any(is_smoke_row(row) for row in metrics_rows):
        raise ValueError("Smoke rows must not be passed to final figure source-data export.")
    generated_at = datetime.now().isoformat(timespec="seconds")
    software = software_versions()
    metric_fields = [
        "figure",
        "panel",
        "plotted",
        "model_label",
        "model",
        "task",
        "checkpoint",
        "config_path",
        "seed",
        "train_count",
        "val_count",
        "test_count",
        "n_definition",
        "metric_definition",
        "denominator",
        "center",
        "spread",
        "statistical_test",
        "is_smoke",
        "excluded_reason",
        "source_file",
        "script",
        "command",
        "generated_at",
        "hardware",
        "os",
        "python_version",
        "torch_version",
        "pitch_accuracy",
        "cross_entropy",
        "rule_violations_per_100_timesteps",
        "parallel_fifths_per_100_timesteps",
        "parallel_octaves_per_100_timesteps",
        "voice_crossing_rate",
        "spacing_violation_rate",
        "seventh_resolution_violation_rate",
        "cadence_unknown_rate",
        "musicxml_export_success_rate",
        "evaluated_generations",
    ]
    with (output_dir / "project1_metrics_source_data.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=metric_fields)
        writer.writeheader()
        for row in metrics_rows:
            out = base_source_row(
                figure="project1_metrics_summary",
                panel="a-d",
                source_file="results/project1_metrics.csv",
                generated_at=generated_at,
                software=software,
            )
            out.update(
                {
                    "plotted": "yes",
                    "model_label": model_label_for(row.get("model", "")),
                    "model": row.get("model", ""),
                    "task": row.get("task", ""),
                    "checkpoint": row.get("checkpoint", ""),
                    "config_path": CONFIG_BY_MODEL.get(row.get("model", ""), ""),
                    "metric_definition": "token-level pitch accuracy, cross entropy, and automatic rule diagnostics",
                    "denominator": "held-out score positions after padding/mask handling",
                    "is_smoke": "no",
                    "excluded_reason": "",
                }
            )
            for field in metric_fields:
                if field not in out:
                    out[field] = row.get(field, "")
            writer.writerow(out)

    rule_rows = [row for row in read_csv(rule_csv) if not is_smoke_row(row)]
    rule_fields = [
        "figure",
        "panel",
        "plotted",
        "model_label",
        "model",
        "task",
        "rule_guided_decoding",
        "rule",
        "rule_label",
        "count",
        "per_100_timesteps",
        "per_100_score_positions",
        "seed",
        "test_count",
        "n_definition",
        "denominator",
        "source_file",
        "script",
        "command",
        "generated_at",
        "hardware",
        "os",
        "python_version",
        "torch_version",
    ]
    with (output_dir / "project1_rule_source_data.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=rule_fields)
        writer.writeheader()
        for row in rule_rows:
            out = base_source_row(
                figure="project1_rule_violations_bar",
                panel="a-b",
                source_file=str(rule_csv),
                generated_at=generated_at,
                software=software,
            )
            out.update(
                {
                    "plotted": "yes",
                    "model_label": model_label_for(row.get("model", "")),
                    "model": row.get("model", ""),
                    "task": row.get("task", ""),
                    "rule_guided_decoding": row.get("rule_guided_decoding", ""),
                    "rule": row.get("rule", ""),
                    "rule_label": readable_rule_name(row.get("rule", "")),
                    "count": row.get("count", ""),
                    "per_100_timesteps": row.get("per_100_timesteps", ""),
                    "per_100_score_positions": row.get("per_100_timesteps", ""),
                    "denominator": "100 quantized SATB score positions",
                }
            )
            writer.writerow({field: out.get(field, "") for field in rule_fields})

    training_fields = [
        "figure",
        "panel",
        "plotted",
        "run",
        "model_label",
        "epoch",
        "train_loss",
        "val_loss",
        "val_accuracy",
        "selection_role",
        "excluded_reason",
        "seed",
        "source_file",
        "script",
        "command",
        "generated_at",
        "hardware",
        "os",
        "python_version",
        "torch_version",
    ]
    with (output_dir / "project1_training_curve_source_data.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=training_fields)
        writer.writeheader()
        for run_name, _ in RUN_ORDER:
            for row in read_csv(runs_dir / run_name / "metrics.csv"):
                out = base_source_row(
                    figure="project1_training_curves",
                    panel="a-b",
                    source_file=str(runs_dir / run_name / "metrics.csv"),
                    generated_at=generated_at,
                    software=software,
                )
                out.update(
                    {
                        "plotted": "yes",
                        "run": run_name,
                        "model_label": run_label_for(run_name),
                        "epoch": row.get("epoch", ""),
                        "train_loss": row.get("train_loss", ""),
                        "val_loss": row.get("val_loss", ""),
                        "val_accuracy": row.get("val_accuracy", ""),
                        "selection_role": "selected comparable training history",
                        "excluded_reason": "",
                    }
                )
                writer.writerow({field: out.get(field, "") for field in training_fields})

    selected_runs = {run_name for run_name, _ in RUN_ORDER}
    exclusion_rows = []
    if runs_dir.exists():
        for metrics_path in sorted(runs_dir.glob("*/metrics.csv")):
            run_name = metrics_path.parent.name
            if run_name in selected_runs:
                continue
            reason = "smoke or development run" if "smoke" in run_name.lower() or "fast" in run_name.lower() else "not included in selected comparable training-curve panel"
            exclusion_rows.append(
                {
                    "run": run_name,
                    "metrics_path": str(metrics_path),
                    "excluded_reason": reason,
                }
            )
    with (output_dir / "project1_training_curve_exclusions.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["run", "metrics_path", "excluded_reason"])
        writer.writeheader()
        writer.writerows(exclusion_rows)

    manifest_rows = [
        {
            "figure": "project1_metrics_summary",
            "source_data_file": "project1_metrics_source_data.csv",
            "source_file": "results/project1_metrics.csv",
            "plotted_rows": str(len(metrics_rows)),
            "excluded_rows": "smoke rows and rows without logged full-evaluation metrics",
            "statistics_note": "single seed; no confidence intervals or significance tests",
        },
        {
            "figure": "project1_rule_violations_bar",
            "source_data_file": "project1_rule_source_data.csv",
            "source_file": str(rule_csv),
            "plotted_rows": str(len(rule_rows)),
            "excluded_rows": "smoke rows",
            "statistics_note": "automatic rule counts per 100 quantized SATB score positions",
        },
        {
            "figure": "project1_training_curves",
            "source_data_file": "project1_training_curve_source_data.csv",
            "source_file": "runs/*/metrics.csv",
            "plotted_rows": str(sum(1 for _ in (output_dir / "project1_training_curve_source_data.csv").open("r", encoding="utf-8")) - 1),
            "excluded_rows": str(len(exclusion_rows)),
            "statistics_note": "selected comparable logs only; unequal run lengths reflect logged training histories",
        },
    ]
    with (output_dir / "project1_source_data_manifest.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "figure",
                "source_data_file",
                "source_file",
                "plotted_rows",
                "excluded_rows",
                "statistics_note",
                "generated_at",
                "script",
                "command",
            ],
        )
        writer.writeheader()
        for row in manifest_rows:
            row.update({"generated_at": generated_at, "script": "src/chorale/plot_results.py", "command": "python -m chorale.plot_results"})
            writer.writerow(row)


def write_qa_note(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Project 1 Figure QA Note",
                "",
                "Backend: Python/matplotlib only.",
                "Figure archetypes: quantitative grid for result summaries; schematic-led workflow for the method figure.",
                "Core conclusion: the proposed model improves pitch prediction and selected rule diagnostics, but it does not solve all common-practice constraints.",
                "Source data: see paper/figures/source_data/*.csv.",
                "Exports: PNG preview, PDF, SVG with editable text, and TIFF at 600 dpi when supported by the local Matplotlib/Pillow stack.",
                "Integrity note: all plotted values are read from results/project1_metrics.csv, results/project1_rule_violations.csv, or selected runs/*/metrics.csv. Smoke rows are excluded from final figures.",
                "Statistics note: the figures report one logged seed and do not show confidence intervals or significance tests.",
                "Training-curve note: only selected comparable training histories are plotted; other run logs are listed in source_data/project1_training_curve_exclusions.csv.",
                "Rule denominator note: legacy CSV columns say per_100_timesteps; figure labels use per 100 score positions for score-level clarity.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def float_or_zero(value: str | None) -> float:
    parsed = float_or_none(value)
    return 0.0 if parsed is None else parsed


def float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def is_smoke_row(row: dict[str, str]) -> bool:
    haystack = " ".join(
        str(row.get(field, "")).lower()
        for field in ("model", "task", "checkpoint", "run", "config", "notes")
    )
    return "smoke" in haystack or row.get("fast_dev_run", "").lower() == "true"


def model_label_for(model: str) -> str:
    for key, label in MODEL_ORDER:
        if key == model:
            return label
    if model == "masked_infilling":
        return "Masked infilling"
    if model == "soprano_to_satb":
        return "Soprano-to-SATB"
    return model


def run_label_for(run_name: str) -> str:
    for run, label in RUN_ORDER:
        if run == run_name:
            return label
    return run_name


def readable_rule_name(rule: str) -> str:
    return {
        "parallel_fifth": "Parallel fifths",
        "parallel_octave": "Parallel octaves",
        "leading_tone_resolution": "Leading-tone resolution",
        "voice_crossing": "Voice crossing",
        "spacing": "Adjacent-voice spacing",
        "seventh_resolution": "Seventh resolution",
    }.get(rule, rule.replace("_", " "))


def software_versions() -> dict[str, str]:
    try:
        import torch

        torch_version = torch.__version__
    except Exception as exc:  # pragma: no cover - depends on optional runtime import.
        torch_version = f"not importable: {type(exc).__name__}"
    return {
        "os": platform.platform(),
        "python_version": sys.version.split()[0],
        "torch_version": torch_version,
    }


def base_source_row(
    figure: str,
    panel: str,
    source_file: str,
    generated_at: str,
    software: dict[str, str],
) -> dict[str, str]:
    row = {
        "figure": figure,
        "panel": panel,
        "source_file": source_file,
        "script": "src/chorale/plot_results.py",
        "command": "python -m chorale.plot_results",
        "generated_at": generated_at,
    }
    row.update(PROJECT_METADATA)
    row.update(software)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot Project 1 metrics and method figure.")
    parser.add_argument("--metrics-csv", default="results/project1_metrics.csv")
    parser.add_argument("--output-dir", default="paper/figures")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--rule-csv", default="results/project1_rule_violations.csv")
    args = parser.parse_args()
    print(plot_project1_results(args.metrics_csv, args.output_dir, args.runs_dir, args.rule_csv))


if __name__ == "__main__":
    main()
