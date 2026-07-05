from __future__ import annotations

import argparse
import csv
from pathlib import Path

from chorale.utils import ensure_dir


EXPECTED_EXPERIMENTS = [
    {
        "display": "LSTM baseline",
        "aliases": {"lstm_baseline", "chorale_lstm"},
        "task": "soprano_to_satb",
        "rule_guided": "False",
    },
    {
        "display": "Vanilla Transformer",
        "aliases": {"transformer_no_constraints", "chorale_transformer_no_constraints"},
        "task": "soprano_to_satb",
        "rule_guided": "False",
    },
    {
        "display": "Transformer without constraints",
        "aliases": {"transformer_no_constraints", "chorale_transformer_no_constraints"},
        "task": "soprano_to_satb",
        "rule_guided": "False",
    },
    {
        "display": "Proposed rule-guided Transformer",
        "aliases": {
            "proposed_neural_symbolic_rule_guided_enhanced",
            "proposed_neural_symbolic_rule_guided_rerankfix_tuned",
            "proposed_neural_symbolic_rule_guided_rerankfix",
            "proposed_neural_symbolic_rule_guided",
            "proposed_transformer_rule_guided",
            "transformer_rule_guided_decoding",
            "chorale_rule_guided_decoding",
        },
        "task": "soprano_to_satb",
        "rule_guided": "True",
    },
    {
        "display": "Masked infilling task",
        "aliases": {
            "proposed_neural_symbolic_masked_infilling_enhanced",
            "proposed_neural_symbolic_masked_infilling",
            "transformer_masked_infilling",
            "chorale_masked_infilling",
        },
        "task": "masked_infill",
        "rule_guided": "True",
    },
    {
        "display": "Soprano-to-SATB task",
        "aliases": {
            "proposed_neural_symbolic_soprano_to_satb_enhanced",
            "proposed_neural_symbolic_soprano_to_satb",
            "transformer_soprano_to_satb",
            "chorale_soprano_to_satb",
        },
        "task": "soprano_to_satb",
        "rule_guided": "True",
    },
]

EXPECTED_ABLATIONS = [
    {
        "display": "Vanilla / no-constraints Transformer",
        "aliases": {"transformer_no_constraints", "chorale_transformer_no_constraints"},
        "task": "soprano_to_satb",
        "rule_guided": "False",
    },
    {
        "display": "Proposed full model",
        "aliases": {
            "proposed_neural_symbolic_rule_guided_enhanced",
            "proposed_neural_symbolic_rule_guided_rerankfix_tuned",
            "proposed_neural_symbolic_rule_guided_rerankfix",
            "proposed_neural_symbolic_rule_guided",
            "proposed_transformer_rule_guided",
            "transformer_rule_guided_decoding",
            "chorale_rule_guided_decoding",
        },
        "task": "soprano_to_satb",
        "rule_guided": "True",
    },
    {
        "display": "No harmonic conditioning",
        "aliases": {"ablation_no_harmony_conditioning_enhanced", "ablation_no_harmony_conditioning", "chorale_ablation_no_harmony"},
        "task": "soprano_to_satb",
        "rule_guided": "True",
    },
    {
        "display": "No iterative refinement",
        "aliases": {"ablation_no_iterative_refinement_enhanced", "ablation_no_iterative_refinement", "chorale_ablation_no_iterative_refinement"},
        "task": "soprano_to_satb",
        "rule_guided": "True",
    },
    {
        "display": "No rule-guided decoding",
        "aliases": {"ablation_no_rule_guided_decoding_enhanced", "ablation_no_rule_guided_decoding", "chorale_ablation_no_rule_guided_decoding"},
        "task": "soprano_to_satb",
        "rule_guided": "False",
    },
    {
        "display": "No voice-relation attention",
        "aliases": {"ablation_no_voice_relation_attention_enhanced", "ablation_no_voice_relation_attention", "chorale_ablation_no_voice_relation"},
        "task": "soprano_to_satb",
        "rule_guided": "True",
    },
]

RULE_SUMMARY_EXPERIMENTS = [
    EXPECTED_EXPERIMENTS[0],
    EXPECTED_EXPERIMENTS[1],
    EXPECTED_EXPERIMENTS[3],
    EXPECTED_EXPERIMENTS[4],
    EXPECTED_EXPERIMENTS[5],
    EXPECTED_ABLATIONS[2],
    EXPECTED_ABLATIONS[3],
    EXPECTED_ABLATIONS[4],
    EXPECTED_ABLATIONS[5],
]

MAIN_COLUMNS = [
    ("display", "Experiment"),
    ("task", "Task"),
    ("checkpoint", "Checkpoint"),
    ("pitch_accuracy", "Pitch acc."),
    ("soprano_accuracy", "S acc."),
    ("alto_accuracy", "A acc."),
    ("tenor_accuracy", "T acc."),
    ("bass_accuracy", "B acc."),
    ("cross_entropy", "CE"),
    ("negative_log_likelihood", "NLL"),
    ("rule_violations_per_100_timesteps", "Viol./100 pos."),
    ("parallel_fifths_per_100_timesteps", "P5/100 pos."),
    ("parallel_octaves_per_100_timesteps", "P8/100 pos."),
    ("voice_crossing_rate", "Crossing"),
    ("spacing_violation_rate", "Spacing"),
    ("seventh_resolution_violation_rate", "7th viol."),
    ("cadence_unknown_rate", "Cad. unknown"),
    ("musicxml_export_success_rate", "XML success"),
]

ABLATION_COLUMNS = [
    ("display", "Experiment"),
    ("rule_guided_decoding", "Rule-guided"),
    ("pitch_accuracy", "Pitch acc."),
    ("cross_entropy", "CE"),
    ("rule_violations_per_100_timesteps", "Viol./100 pos."),
    ("parallel_fifths_per_100_timesteps", "P5/100 pos."),
    ("parallel_octaves_per_100_timesteps", "P8/100 pos."),
    ("seventh_resolution_violation_rate", "7th viol."),
    ("voice_crossing_rate", "Crossing"),
    ("range_violation_rate", "Range"),
    ("spacing_violation_rate", "Spacing"),
]

HARMONY_COLUMNS = [
    ("display", "Experiment"),
    ("task", "Task"),
    ("roman_numeral_extraction_coverage", "RN coverage"),
    ("chord_label_coverage", "Chord coverage"),
    ("generated_roman_numeral_coverage", "Generated RN coverage"),
    ("generated_chord_label_coverage", "Generated chord coverage"),
    ("cadence_unknown_rate", "Cadence unknown"),
]

EXPERT_DIMENSIONS = [
    "harmonic correctness",
    "voice-leading correctness",
    "seventh-resolution correctness",
    "cadence quality",
    "singability",
    "stylistic consistency",
    "usefulness for composition pedagogy",
    "overall preference",
]


def build_project1_tables_from_csv(
    metrics_csv: str | Path = "results/project1_metrics.csv",
    output_dir: str | Path = "paper/tables",
    rule_csv: str | Path = "results/project1_rule_violations.csv",
    harmony_csv: str | Path = "results/project1_harmony_labels_summary.csv",
    expert_summary_csv: str | Path = "results/project1_expert_eval_summary.csv",
) -> dict[str, str]:
    output_dir = ensure_dir(output_dir)
    metric_rows = read_rows(Path(metrics_csv))
    rule_rows = read_rows(Path(rule_csv))
    harmony_rows = read_rows(Path(harmony_csv))
    expert_rows = read_rows(Path(expert_summary_csv))

    final_metric_rows = [row for row in metric_rows if not is_smoke_row(row)]
    expected_rows = expected_table_rows(final_metric_rows)
    full_missing = not any(row.get("status") == "available" for row in expected_rows)

    paths: dict[str, str] = {}
    paths["main"] = write_table(
        output_dir / "project1_main_results.tex",
        expected_rows,
        MAIN_COLUMNS,
        "Main full-experiment metrics. Cells are filled only from logged non-smoke result rows.",
        full_missing=full_missing,
    )
    ablation_rows = expected_table_rows(final_metric_rows, EXPECTED_ABLATIONS)
    paths["ablation"] = write_table(
        output_dir / "project1_ablation_results.tex",
        ablation_rows,
        ABLATION_COLUMNS,
        "Focused architecture and decoding ablations from logged non-smoke evaluations.",
        full_missing=full_missing,
    )
    paths["rule_violations"] = write_rule_table(
        output_dir / "project1_rule_violations.tex",
        [row for row in rule_rows if not is_smoke_row(row)],
        full_missing=full_missing,
    )
    paths["harmony_coverage"] = write_harmony_table(
        output_dir / "project1_harmony_label_coverage.tex",
        expected_rows,
        harmony_rows,
        full_missing=full_missing,
    )
    if expert_rows:
        paths["expert_eval"] = write_expert_results_table(output_dir / "project1_expert_eval_results.tex", expert_rows)
    else:
        paths["expert_eval_template"] = write_expert_template_table(output_dir / "project1_expert_eval_template.tex")
    return paths


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def expected_table_rows(metric_rows: list[dict[str, str]], expected_experiments: list[dict[str, object]] | None = None) -> list[dict[str, str]]:
    expected_experiments = expected_experiments or EXPECTED_EXPERIMENTS
    rows: list[dict[str, str]] = []
    for expected in expected_experiments:
        match = find_metric_row(metric_rows, expected)
        row = {
            "display": expected["display"],
            "task": expected["task"],
            "rule_guided_decoding": expected["rule_guided"],
            "status": "available" if match else "not available",
            "_aliases": tuple(expected["aliases"]),
        }
        if match:
            row.update(match)
            row["display"] = expected["display"]
        rows.append(row)
    return rows


def find_metric_row(rows: list[dict[str, str]], expected: dict[str, object]) -> dict[str, str] | None:
    aliases = {str(alias).lower() for alias in expected["aliases"]}
    task = str(expected["task"])
    rule_guided = str(expected["rule_guided"]).lower()
    candidates: list[dict[str, str]] = []
    for row in rows:
        model = row.get("model", "").lower()
        if model not in aliases and not any(model.startswith(alias) for alias in aliases):
            continue
        if row.get("task", "") != task:
            continue
        if row.get("rule_guided_decoding", "").lower() != rule_guided.lower():
            continue
        candidates.append(row)
    if not candidates:
        return None
    return sorted(candidates, key=row_preference_score, reverse=True)[0]


def row_preference_score(row: dict[str, str]) -> int:
    joined = " ".join([row.get("model", ""), row.get("checkpoint", "")]).lower()
    score = 0
    # Prefer full enhanced reruns over older exploratory reranking sweeps.
    if "enhanced" in joined:
        score += 100
    if "202607" in joined:
        score += 25
    if "rerankfix" in joined:
        score += 10
    if "tuned" in joined:
        score += 15
    if "fastcheck" in joined or "smoke" in joined:
        score -= 100
    return score


def is_smoke_row(row: dict[str, str]) -> bool:
    return "smoke" in row.get("model", "").lower()


def write_table(path: Path, rows: list[dict[str, str]], columns: list[tuple[str, str]], caption: str, full_missing: bool) -> str:
    missing_note = " Full RTX result rows were not available in the inspected result files." if full_missing else ""
    path.write_text(latex_table(rows, columns, caption + missing_note), encoding="utf-8")
    return str(path)


def write_rule_table(path: Path, rows: list[dict[str, str]], full_missing: bool) -> str:
    columns = [
        ("model", "Model"),
        ("task", "Task"),
        ("rule_guided_decoding", "Rule-guided"),
        ("parallel_fifth", "P5/100"),
        ("parallel_octave", "P8/100"),
        ("voice_crossing", "Cross/100"),
        ("spacing", "Spacing/100"),
        ("seventh_resolution", "7th/100"),
        ("leading_tone_resolution", "LT/100"),
    ]
    caption = "Compact rule-violation summary for selected primary and ablation evaluations. Full per-rule counts remain in results/project1_rule_violations.csv."
    if full_missing:
        caption += " Full RTX rule rows were not available in the inspected result files."
    if not rows:
        rows = [
            {
                "model": "full RTX experiments",
                "task": "not available",
                "rule_guided_decoding": "not available",
                "parallel_fifth": "not available",
                "parallel_octave": "not available",
                "voice_crossing": "not available",
                "spacing": "not available",
                "seventh_resolution": "not available",
                "leading_tone_resolution": "not available",
            }
        ]
    else:
        rows = expected_rule_summary_rows(compact_rule_rows(rows))
    path.write_text(latex_table(rows, columns, caption), encoding="utf-8")
    return str(path)


def expected_rule_summary_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    selected: list[dict[str, str]] = []
    for expected in RULE_SUMMARY_EXPERIMENTS:
        match = find_metric_row(rows, expected)
        row = {
            "model": expected["display"],
            "task": expected["task"],
            "rule_guided_decoding": expected["rule_guided"],
        }
        if match:
            row.update(match)
            row["model"] = expected["display"]
        for rule in [
            "parallel_fifth",
            "parallel_octave",
            "voice_crossing",
            "spacing",
            "seventh_resolution",
            "leading_tone_resolution",
        ]:
            row.setdefault(rule, "not available")
        selected.append(row)
    return selected


def compact_rule_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    grouped: dict[tuple[str, str, str], dict[str, str]] = {}
    for row in rows:
        key = (row.get("model", ""), row.get("task", ""), row.get("rule_guided_decoding", ""))
        out = grouped.setdefault(
            key,
            {
                "model": row.get("model", ""),
                "task": row.get("task", ""),
                "rule_guided_decoding": row.get("rule_guided_decoding", ""),
            },
        )
        rule = row.get("rule", "")
        if rule:
            out[rule] = row.get("per_100_timesteps", "")
    for out in grouped.values():
        for rule in [
            "parallel_fifth",
            "parallel_octave",
            "voice_crossing",
            "spacing",
            "seventh_resolution",
            "leading_tone_resolution",
        ]:
            out.setdefault(rule, "0")
    return [grouped[key] for key in sorted(grouped)]


def write_harmony_table(path: Path, expected_rows: list[dict[str, str]], harmony_rows: list[dict[str, str]], full_missing: bool) -> str:
    rows = []
    non_smoke_harmony = [row for row in harmony_rows if not is_smoke_row(row)]
    for row in expected_rows:
        match = find_harmony_row(non_smoke_harmony, row)
        out = {"display": row["display"], "task": row["task"]}
        for key, _ in HARMONY_COLUMNS:
            if key not in {"display", "task"} and row.get(key, "") != "":
                out[key] = row[key]
        if match:
            out.update(normalize_harmony_row(match))
        out.update({key: "not available" for key, _ in HARMONY_COLUMNS if key not in out})
        rows.append(out)
    caption = "Automatic harmonic-label coverage for non-smoke evaluations."
    if full_missing:
        caption += " Full RTX harmony summary rows were not available in the inspected result files."
    path.write_text(latex_table(rows, HARMONY_COLUMNS, caption), encoding="utf-8")
    return str(path)


def find_harmony_row(rows: list[dict[str, str]], expected_row: dict[str, str]) -> dict[str, str] | None:
    task = expected_row.get("task", "")
    rule_guided = expected_row.get("rule_guided_decoding", "").lower()
    aliases = {str(alias).lower() for alias in expected_row.get("_aliases", [])}
    candidates: list[dict[str, str]] = []
    for row in rows:
        if aliases and row.get("model", "").lower() not in aliases:
            continue
        if row.get("task", "") == task and row.get("rule_guided_decoding", "").lower() == rule_guided:
            candidates.append(row)
    if not candidates:
        return None
    return sorted(candidates, key=row_preference_score, reverse=True)[0]


def normalize_harmony_row(row: dict[str, str]) -> dict[str, str]:
    normalized = dict(row)
    total_steps = to_float(row.get("harmony_label_steps", ""))
    if total_steps and total_steps > 0:
        if not normalized.get("generated_roman_numeral_coverage"):
            normalized["generated_roman_numeral_coverage"] = ratio(row.get("generated_roman_known_total", ""), total_steps)
        if not normalized.get("generated_chord_label_coverage"):
            normalized["generated_chord_label_coverage"] = ratio(row.get("generated_chord_known_total", ""), total_steps)
    cadence_checks = to_float(row.get("cadence_checks", ""))
    if cadence_checks and cadence_checks > 0 and not normalized.get("cadence_unknown_rate"):
        normalized["cadence_unknown_rate"] = ratio(row.get("cadence_unknown_count", ""), cadence_checks)
    return normalized


def ratio(numerator: str, denominator: float) -> str:
    value = to_float(numerator)
    if value is None:
        return ""
    return str(value / denominator)


def to_float(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def write_expert_results_table(path: Path, rows: list[dict[str, str]]) -> str:
    columns = [("dimension", "Dimension"), ("mean", "Mean"), ("std", "SD"), ("n", "N")]
    path.write_text(latex_table(rows, columns, "Blind expert-evaluation results from completed rating forms."), encoding="utf-8")
    return str(path)


def write_expert_template_table(path: Path) -> str:
    rows = [{"dimension": dimension, "status": "expert evaluation pending"} for dimension in EXPERT_DIMENSIONS]
    columns = [("dimension", "Rating dimension"), ("status", "Status")]
    path.write_text(latex_table(rows, columns, "Expert-evaluation template. Scores are not reported until completed ratings are available."), encoding="utf-8")
    return str(path)


def latex_table(rows: list[dict[str, str]], columns: list[tuple[str, str]], caption: str) -> str:
    alignment = "l" * len(columns)
    use_resize = len(columns) > 6
    lines = [
        "\\begin{table}[t]",
        "\\centering",
        f"\\caption{{{escape_latex(caption)}}}",
    ]
    if use_resize:
        lines.append("\\resizebox{\\textwidth}{!}{%")
    lines.extend(
        [
            f"\\begin{{tabular}}{{{alignment}}}",
            "\\toprule",
            " & ".join(header for _, header in columns) + " \\\\",
            "\\midrule",
        ]
    )
    if rows:
        for row in rows:
            lines.append(" & ".join(format_cell(row.get(key, "")) for key, _ in columns) + " \\\\")
    else:
        lines.append(" & ".join(["not available"] * len(columns)) + " \\\\")
    lines.extend(["\\bottomrule", "\\end{tabular}"])
    if use_resize:
        lines.append("}%")
    lines.extend(["\\end{table}", ""])
    return "\n".join(lines)


def format_cell(value: object) -> str:
    if value is None or str(value) == "":
        return "not available"
    value_str = str(value)
    lowered = value_str.lower()
    if lowered == "true":
        return "yes"
    if lowered == "false":
        return "no"
    if lowered == "nan":
        return "not available"
    try:
        numeric = float(value_str)
    except ValueError:
        return escape_latex(value_str)
    if abs(numeric) >= 1000:
        return f"{numeric:.1f}"
    return f"{numeric:.4f}"


def escape_latex(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\textbackslash{}")
        .replace("_", "\\_")
        .replace("&", "\\&")
        .replace("%", "\\%")
        .replace("#", "\\#")
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Create LaTeX tables for Project 1 from logged metrics.")
    parser.add_argument("--metrics-csv", default="results/project1_metrics.csv")
    parser.add_argument("--output-dir", default="paper/tables")
    parser.add_argument("--rule-csv", default="results/project1_rule_violations.csv")
    parser.add_argument("--harmony-csv", default="results/project1_harmony_labels_summary.csv")
    parser.add_argument("--expert-summary-csv", default="results/project1_expert_eval_summary.csv")
    args = parser.parse_args()
    paths = build_project1_tables_from_csv(args.metrics_csv, args.output_dir, args.rule_csv, args.harmony_csv, args.expert_summary_csv)
    print(paths)


if __name__ == "__main__":
    main()
