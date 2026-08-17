from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


METRICS = [
    "pitch_accuracy",
    "cross_entropy",
    "negative_log_likelihood",
    "rule_violations_per_100_timesteps",
    "parallel_fifths_per_100_timesteps",
    "parallel_octaves_per_100_timesteps",
    "voice_crossing_rate",
    "spacing_violation_rate",
    "range_violation_rate",
    "seventh_resolution_violation_rate",
    "cadence_unknown_rate",
    "musicxml_export_success_rate",
    "generation_validity_rate",
]

PLANNED_COMPARISONS = [
    ("vanilla_vs_current_rule_guided", "vanilla_transformer", "current_rule_guided_transformer"),
    ("vanilla_vs_cih_s2s", "vanilla_transformer", "cih_s2s_transformer"),
    ("current_rule_guided_vs_cih_s2s", "current_rule_guided_transformer", "cih_s2s_transformer"),
    ("no_constraints_vs_constrained", "vanilla_transformer", "current_rule_guided_transformer"),
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "comparison_id",
        "model_a",
        "model_b",
        "metric",
        "n_a",
        "n_b",
        "n_pairs",
        "mean_a",
        "sd_a",
        "mean_b",
        "sd_b",
        "mean_difference_b_minus_a",
        "ci_low",
        "ci_high",
        "test",
        "statistic",
        "p_value",
        "status",
        "note",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: fmt(row.get(key, "")) for key in fieldnames})


def fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        return f"{value:.12g}"
    return str(value)


def float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return value


def values_for(rows: list[dict[str, str]], family: str, metric: str) -> list[tuple[str, float]]:
    output: list[tuple[str, float]] = []
    for row in rows:
        if row.get("model_family") != family:
            continue
        if str(row.get("formal_evidence", "")).lower() == "false":
            continue
        value = float_or_none(row.get(metric))
        if value is None:
            continue
        seed = str(row.get("seed", "")).strip()
        if not seed:
            continue
        output.append((seed, value))
    return sorted(output)


def descriptive(values: list[float]) -> tuple[float | None, float | None]:
    if not values:
        return None, None
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if len(values) > 1 else 0.0
    return float(mean), float(sd)


def bootstrap_ci(values: list[float], *, n_boot: int = 2000, seed: int = 2026) -> tuple[float | None, float | None]:
    if len(values) < 2:
        return None, None
    rng = random.Random(seed)
    means = []
    for _ in range(n_boot):
        sample = [values[rng.randrange(len(values))] for _ in values]
        means.append(statistics.mean(sample))
    means.sort()
    low_idx = max(0, int(0.025 * len(means)) - 1)
    high_idx = min(len(means) - 1, int(0.975 * len(means)))
    return float(means[low_idx]), float(means[high_idx])


def paired_test(diffs: list[float]) -> tuple[str, float | None, float | None]:
    if len(diffs) < 3:
        return "paired_test_not_run", None, None
    try:
        from scipy import stats  # type: ignore
    except Exception:
        if len(diffs) < 8:
            statistic, p_value = exact_wilcoxon_signed_rank(diffs)
            if statistic is not None:
                return "wilcoxon_signed_rank_exact_fallback", statistic, p_value
        return "paired_test_pending_scipy_unavailable", None, None
    try:
        if len(diffs) < 8:
            result = stats.wilcoxon(diffs, zero_method="wilcox", alternative="two-sided")
            return "wilcoxon_signed_rank", float(result.statistic), float(result.pvalue)
        result = stats.ttest_1samp(diffs, popmean=0.0)
        return "paired_t_test", float(result.statistic), float(result.pvalue)
    except Exception:
        return "paired_test_failed", None, None


def exact_wilcoxon_signed_rank(diffs: list[float]) -> tuple[float | None, float | None]:
    nonzero = [float(diff) for diff in diffs if abs(float(diff)) > 1e-12]
    if not nonzero:
        return 0.0, 1.0
    abs_values = [abs(diff) for diff in nonzero]
    sorted_indices = sorted(range(len(abs_values)), key=lambda idx: abs_values[idx])
    ranks = [0.0] * len(abs_values)
    i = 0
    while i < len(sorted_indices):
        j = i + 1
        while j < len(sorted_indices) and abs(abs_values[sorted_indices[j]] - abs_values[sorted_indices[i]]) <= 1e-12:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for idx in sorted_indices[i:j]:
            ranks[idx] = avg_rank
        i = j
    positive = sum(rank for rank, diff in zip(ranks, nonzero) if diff > 0)
    total_rank = sum(ranks)
    observed = min(positive, total_rank - positive)
    possible_stats: list[float] = []
    for mask in range(1 << len(nonzero)):
        signed_sum = sum(rank for idx, rank in enumerate(ranks) if mask & (1 << idx))
        possible_stats.append(min(signed_sum, total_rank - signed_sum))
    p_value = sum(1 for value in possible_stats if value <= observed + 1e-12) / len(possible_stats)
    return float(observed), float(min(1.0, p_value))


def comparison_rows(multiseed_rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    families = sorted({row.get("model_family", "") for row in multiseed_rows if row.get("model_family")})

    for family in families:
        for metric in METRICS:
            seed_values = values_for(multiseed_rows, family, metric)
            values = [value for _, value in seed_values]
            if not values:
                continue
            mean, sd = descriptive(values)
            ci_low, ci_high = bootstrap_ci(values)
            output.append(
                {
                    "comparison_id": f"descriptive_{family}",
                    "model_a": family,
                    "model_b": "",
                    "metric": metric,
                    "n_a": len(values),
                    "n_b": "",
                    "n_pairs": "",
                    "mean_a": mean,
                    "sd_a": sd,
                    "mean_b": "",
                    "sd_b": "",
                    "mean_difference_b_minus_a": "",
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "test": "bootstrap_mean_ci" if len(values) > 1 else "descriptive_only",
                    "status": "descriptive_ci" if len(values) > 1 else "descriptive_single_seed",
                    "note": "Mean/SD over available formal seeds; no model comparison in this row.",
                }
            )

    for comparison_id, model_a, model_b in PLANNED_COMPARISONS:
        for metric in METRICS:
            a = dict(values_for(multiseed_rows, model_a, metric))
            b = dict(values_for(multiseed_rows, model_b, metric))
            shared = sorted(set(a) & set(b))
            a_values = list(a.values())
            b_values = list(b.values())
            mean_a, sd_a = descriptive(a_values)
            mean_b, sd_b = descriptive(b_values)
            if shared:
                diffs = [b[seed] - a[seed] for seed in shared]
                test, statistic, p_value = paired_test(diffs)
                ci_low, ci_high = bootstrap_ci(diffs)
                status = "paired_test_completed" if p_value is not None else "paired_test_pending"
                note = "Paired by identical random seed."
            else:
                diffs = []
                test, statistic, p_value = "not_run", None, None
                ci_low, ci_high = None, None
                status = "pending_no_paired_seed_data"
                note = "No shared formal seeds were found; do not report significance for this comparison."
            output.append(
                {
                    "comparison_id": comparison_id,
                    "model_a": model_a,
                    "model_b": model_b,
                    "metric": metric,
                    "n_a": len(a_values),
                    "n_b": len(b_values),
                    "n_pairs": len(shared),
                    "mean_a": mean_a,
                    "sd_a": sd_a,
                    "mean_b": mean_b,
                    "sd_b": sd_b,
                    "mean_difference_b_minus_a": statistics.mean(diffs) if diffs else "",
                    "ci_low": ci_low,
                    "ci_high": ci_high,
                    "test": test,
                    "statistic": statistic,
                    "p_value": p_value,
                    "status": status,
                    "note": note,
                }
            )
    return output


def make_markdown(rows: list[dict[str, Any]]) -> str:
    status_counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
    lines = [
        "# Project1 Statistical Summary",
        "",
        "Rows marked pending must not be cited as statistical evidence.",
        "",
        "## Status Counts",
        "",
    ]
    lines.extend(f"- {status}: {count}" for status, count in sorted(status_counts.items()))
    lines.extend(
        [
            "",
            "## Reporting Rule",
            "",
            "Use mean +/- SD only for models with repeated formal seeds. Use paired tests only when the same seed or same score-level unit is available for both models. Figure captions must state when no significance test is included.",
            "",
        ]
    )
    return "\n".join(lines)


def run(root: str | Path = ROOT, out_csv: str = "results/statistical_summary.csv") -> dict[str, str]:
    root = Path(root)
    multiseed_path = root / "results" / "experiment_multiseed_raw.csv"
    rows = read_csv(multiseed_path)
    summary_rows = comparison_rows(rows)
    out = root / out_csv
    write_csv(out, summary_rows)
    md = out.with_suffix(".md")
    md.write_text(make_markdown(summary_rows), encoding="utf-8")
    return {"out_csv": str(out.relative_to(root)), "out_md": str(md.relative_to(root)), "rows": str(len(summary_rows))}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run planned paired/statistical summaries for Project1.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--out-csv", default="results/statistical_summary.csv")
    args = parser.parse_args()
    print(json.dumps(run(args.root, args.out_csv), indent=2))


if __name__ == "__main__":
    main()
