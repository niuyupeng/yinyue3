from __future__ import annotations

from pathlib import Path

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.theory.harmony_rules import check_cadence_correctness, check_seventh_resolution
from chorale.theory.voice_leading_rules import evaluate_voice_leading
from chorale.utils import ensure_dir, write_json


def build_explanation_report(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    title: str = "SATB rule report",
    key_tonic_pc: int = 0,
    harmonic_labels: dict | None = None,
) -> dict:
    voice_report = evaluate_voice_leading(tokens, tokenizer, length=length, key_tonic_pc=key_tonic_pc)
    seventh = check_seventh_resolution(tokens, tokenizer, harmonic_labels=harmonic_labels, length=length)
    cadence = check_cadence_correctness(tokens, tokenizer, harmonic_labels=harmonic_labels, length=length)
    counts = dict(voice_report["counts"])
    for extra in (seventh, cadence):
        for rule, count in extra.get("counts", {}).items():
            counts[rule] = counts.get(rule, 0) + int(count)
    violations = voice_report["violations"] + seventh.get("violations", []) + cadence.get("violations", [])
    explanations = voice_report["explanations"] + seventh.get("explanations", []) + cadence.get("explanations", [])
    total_penalty = float(voice_report["total_penalty"]) + float(seventh.get("total_penalty", 0.0)) + float(
        cadence.get("total_penalty", 0.0)
    )
    total_violations = int(len(violations))
    steps = int(length if length is not None else np.asarray(tokens).shape[0])
    return {
        "title": title,
        "total_penalty": total_penalty,
        "total_violations": total_violations,
        "counts": counts,
        "violations_per_100_timesteps": 100.0 * total_violations / max(1, steps),
        "seventh_resolution_violations": int(seventh.get("total_violations", 0)),
        "seventh_resolution_violation_rate": float(seventh.get("total_violations", 0)) / max(1, steps),
        "cadence_type": cadence.get("cadence_type", "UNKNOWN"),
        "cadence_checks": int(cadence.get("cadence_checks", 0)),
        "cadence_unknown_count": int(cadence.get("cadence_unknown_count", 0)),
        "cadence_unknown_rate": float(cadence.get("cadence_unknown_rate", 0.0)),
        "explanations": explanations,
        "violations": violations,
        "limitations": voice_report["limitations"] + seventh["limitations"] + cadence["limitations"],
    }


def write_explanation_report(report: dict, txt_path: str | Path, json_path: str | Path) -> None:
    txt_path = Path(txt_path)
    ensure_dir(txt_path.parent)
    lines = [
        report.get("title", "SATB rule report"),
        f"Total penalty: {report.get('total_penalty', 0)}",
        f"Total violations: {report.get('total_violations', 0)}",
        "",
        "Violations:",
    ]
    explanations = report.get("explanations", [])
    lines.extend(explanations if explanations else ["None detected."])
    lines.append("")
    lines.append("Limitations:")
    lines.extend(report.get("limitations", []))
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    write_json(report, json_path)
