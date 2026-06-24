from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chorale.harmonize import harmonize_musicxml
from chorale.harmonization_quality import (
    DEFAULT_MAX_SEVENTH_RESOLUTION_VIOLATIONS,
    DEFAULT_MAX_TOTAL_PENALTY,
    DEFAULT_MAX_TOTAL_VIOLATIONS,
    DEFAULT_MAX_VIOLATIONS_PER_100,
)
from chorale.utils import ensure_dir, write_json


MUSICXML_SUFFIXES = {".musicxml", ".xml", ".mxl"}


def batch_harmonize(
    input_dir: str | Path,
    output_dir: str | Path,
    *,
    checkpoint: str | Path | None = None,
    config: str | Path | None = None,
    task: str = "soprano_to_satb",
    input_role: str = "soprano",
    known_voices: str | None = None,
    render_audio: bool = False,
    audio_backend: str = "additive",
    apply_rules: bool = True,
    optimize_symbols: bool = True,
    repair_passes: int = 12,
    repair_final_cadence: bool = True,
    max_violations_per_100: float = DEFAULT_MAX_VIOLATIONS_PER_100,
    max_total_violations: int = DEFAULT_MAX_TOTAL_VIOLATIONS,
    max_total_penalty: float = DEFAULT_MAX_TOTAL_PENALTY,
    max_seventh_resolution_violations: int = DEFAULT_MAX_SEVENTH_RESOLUTION_VIOLATIONS,
    require_audio_for_quality: bool = False,
    recursive: bool = False,
    stop_on_error: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    input_dir = Path(input_dir)
    output_dir = ensure_dir(output_dir)
    files = discover_musicxml_files(input_dir, recursive=recursive)
    if limit is not None:
        files = files[: max(0, int(limit))]

    rows: list[dict[str, Any]] = []
    for index, path in enumerate(files, start=1):
        score_id = safe_score_id(path, index)
        score_dir = ensure_dir(output_dir / score_id)
        try:
            summary = harmonize_musicxml(
                path,
                score_dir,
                checkpoint=checkpoint,
                config=config,
                task=task,
                input_role=input_role,
                known_voices=known_voices,
                prefix=score_id,
                apply_rules=apply_rules,
                render_audio=render_audio,
                audio_backend=audio_backend,
                optimize_symbols=optimize_symbols,
                repair_passes=repair_passes,
                repair_final_cadence=repair_final_cadence,
                max_violations_per_100=max_violations_per_100,
                max_total_violations=max_total_violations,
                max_total_penalty=max_total_penalty,
                max_seventh_resolution_violations=max_seventh_resolution_violations,
                require_audio_for_quality=require_audio_for_quality,
            )
            rows.append(row_from_summary(score_id, path, summary))
        except Exception as exc:
            row = {
                "score_id": score_id,
                "input_musicxml": str(path),
                "status": "failed",
                "quality_status": "failed",
                "quality_score": 0.0,
                "quality_issues": str(exc),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            rows.append(row)
            if stop_on_error:
                raise

    report = build_batch_report(input_dir, output_dir, rows, files)
    write_batch_outputs(report, output_dir)
    return report


def discover_musicxml_files(input_dir: Path, *, recursive: bool) -> list[Path]:
    if input_dir.is_file() and input_dir.suffix.lower() in MUSICXML_SUFFIXES:
        return [input_dir]
    pattern = "**/*" if recursive else "*"
    if not input_dir.is_dir():
        return []
    return sorted(path for path in input_dir.glob(pattern) if path.is_file() and path.suffix.lower() in MUSICXML_SUFFIXES)


def safe_score_id(path: Path, index: int) -> str:
    stem = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in path.stem).strip("_")
    return f"{index:03d}_{stem or 'score'}"


def row_from_summary(score_id: str, input_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    outputs = summary.get("outputs", {}) if isinstance(summary.get("outputs"), dict) else {}
    audio = summary.get("audio", {}) if isinstance(summary.get("audio"), dict) else {}
    rule_summary = summary.get("rule_summary", {}) if isinstance(summary.get("rule_summary"), dict) else {}
    repair = summary.get("symbolic_repair", {}) if isinstance(summary.get("symbolic_repair"), dict) else {}
    cadence_repair = summary.get("cadential_repair", {}) if isinstance(summary.get("cadential_repair"), dict) else {}
    quality = summary.get("quality_gate", {}) if isinstance(summary.get("quality_gate"), dict) else {}
    preservation = (
        summary.get("known_voice_preservation", {})
        if isinstance(summary.get("known_voice_preservation"), dict)
        else {}
    )
    score_validation = (
        summary.get("score_validation", {})
        if isinstance(summary.get("score_validation"), dict)
        else {}
    )
    preflight = summary.get("input_preflight", {}) if isinstance(summary.get("input_preflight"), dict) else {}
    return {
        "score_id": score_id,
        "input_musicxml": str(input_path),
        "status": "ok",
        "quality_status": quality.get("status", ""),
        "quality_score": quality.get("score", ""),
        "quality_issues": "; ".join(quality.get("issues", []) or []),
        "quality_warnings": "; ".join(quality.get("warnings", []) or []),
        "engine": summary.get("engine", ""),
        "task": summary.get("task", ""),
        "input_role": summary.get("input_role", ""),
        "known_voices": ",".join(summary.get("known_voices", []) or []),
        "key_label": summary.get("key_label", ""),
        "length_timesteps": summary.get("length_timesteps", ""),
        "harmonized_musicxml": outputs.get("harmonized_musicxml", ""),
        "condition_musicxml": outputs.get("condition_musicxml", ""),
        "rule_report_json": outputs.get("rule_report_json", ""),
        "summary_json": outputs.get("summary_json", ""),
        "total_penalty": rule_summary.get("total_penalty", ""),
        "total_violations": rule_summary.get("total_violations", ""),
        "violations_per_100_timesteps": rule_summary.get("violations_per_100_timesteps", ""),
        "cadence_type": rule_summary.get("cadence_type", ""),
        "seventh_resolution_violations": rule_summary.get("seventh_resolution_violations", ""),
        "known_voice_preservation_pass": preservation.get("pass", ""),
        "known_voice_mismatches": preservation.get("mismatches", ""),
        "input_preflight_status": preflight.get("status", ""),
        "input_preflight_issues": "; ".join(preflight.get("issues", []) or []),
        "input_preflight_warnings": "; ".join(preflight.get("warnings", []) or []),
        "input_part_count": preflight.get("part_count", ""),
        "input_note_count": preflight.get("note_count", ""),
        "input_will_truncate": preflight.get("will_truncate", ""),
        "score_parse_ok": score_validation.get("parse_ok", ""),
        "score_part_count": score_validation.get("part_count", ""),
        "score_note_count": score_validation.get("note_count", ""),
        "symbolic_repair_enabled": repair.get("enabled", False),
        "symbolic_accepted_repairs": repair.get("accepted_repairs", 0),
        "symbolic_candidate_checks": repair.get("candidate_checks", 0),
        "cadential_repair_enabled": cadence_repair.get("enabled", False),
        "cadential_repair_accepted": cadence_repair.get("accepted", False),
        "cadential_repair_applied": cadence_repair.get("applied", False),
        "cadential_repair_cadence_before": cadence_repair.get("cadence_before", ""),
        "cadential_repair_cadence_after": cadence_repair.get("cadence_after", ""),
        "audio_requested": audio.get("requested", False),
        "wav_status": audio.get("wav_status", ""),
        "mp3_status": audio.get("mp3_status", ""),
        "wav": audio.get("wav", ""),
        "mp3": audio.get("mp3", ""),
        "error_type": "",
        "error": "",
    }


def build_batch_report(input_dir: Path, output_dir: Path, rows: list[dict[str, Any]], files: list[Path]) -> dict[str, Any]:
    ok_rows = [row for row in rows if row.get("status") == "ok"]
    failed_rows = [row for row in rows if row.get("status") != "ok"]
    quality_pass_rows = [row for row in ok_rows if row.get("quality_status") == "pass"]
    needs_review_rows = [row for row in rows if row.get("quality_status") in {"needs_review", "failed"}]
    violation_values = [
        float(row.get("violations_per_100_timesteps", 0) or 0)
        for row in ok_rows
        if row.get("violations_per_100_timesteps") not in ("", None)
    ]
    return {
        "schema": "project1_batch_harmonization_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "input_dir": str(input_dir),
        "output_dir": str(output_dir),
        "discovered_files": len(files),
        "completed": len(ok_rows),
        "failed": len(failed_rows),
        "quality_pass": len(quality_pass_rows),
        "needs_review": len(needs_review_rows),
        "all_pass": len(files) > 0 and len(failed_rows) == 0 and len(ok_rows) == len(files),
        "all_quality_pass": len(files) > 0 and len(failed_rows) == 0 and len(needs_review_rows) == 0,
        "mean_violations_per_100_timesteps": (
            sum(violation_values) / len(violation_values) if violation_values else None
        ),
        "review_queue": review_queue(rows),
        "rows": rows,
    }


def write_batch_outputs(report: dict[str, Any], output_dir: Path) -> dict[str, str]:
    json_path = output_dir / "batch_harmonization_summary.json"
    csv_path = output_dir / "batch_harmonization_summary.csv"
    md_path = output_dir / "batch_harmonization_summary.md"
    review_csv = output_dir / "batch_review_queue.csv"
    review_md = output_dir / "batch_review_queue.md"
    write_json(report, json_path)
    write_rows_csv(report.get("rows", []), csv_path)
    write_rows_csv(report.get("review_queue", []), review_csv)
    md_path.write_text(make_markdown(report), encoding="utf-8")
    review_md.write_text(make_review_markdown(report), encoding="utf-8")
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "markdown": str(md_path),
        "review_csv": str(review_csv),
        "review_markdown": str(review_md),
    }


def write_rows_csv(rows: Any, path: Path) -> None:
    rows = [row for row in rows if isinstance(row, dict)]
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row.keys():
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Project1 Batch Harmonization Summary",
        "",
        f"Input: `{report.get('input_dir')}`",
        f"Output: `{report.get('output_dir')}`",
        f"Discovered files: `{report.get('discovered_files')}`",
        f"Completed: `{report.get('completed')}`",
        f"Failed: `{report.get('failed')}`",
        f"All pass: `{report.get('all_pass')}`",
        f"Quality pass: `{report.get('quality_pass')}`",
        f"Needs review: `{report.get('needs_review')}`",
        f"All quality pass: `{report.get('all_quality_pass')}`",
        f"Mean violations per 100 timesteps: `{report.get('mean_violations_per_100_timesteps')}`",
        "",
        "## Scores",
        "",
        "| score_id | status | quality | total violations | rule report | harmonized MusicXML |",
        "|---|---:|---:|---:|---|---|",
    ]
    for row in report.get("rows", []):
        if not isinstance(row, dict):
            continue
        lines.append(
            "| {score_id} | {status} | {quality_status} | {total_violations} | {rule_report_json} | {harmonized_musicxml} |".format(
                score_id=row.get("score_id", ""),
                status=row.get("status", ""),
                quality_status=row.get("quality_status", ""),
                total_violations=row.get("total_violations", ""),
                rule_report_json=row.get("rule_report_json", ""),
                harmonized_musicxml=row.get("harmonized_musicxml", ""),
            )
        )
    return "\n".join(lines) + "\n"


def review_queue(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [row for row in rows if row.get("quality_status") in {"needs_review", "failed"}]
    return sorted(
        candidates,
        key=lambda row: (
            0 if row.get("quality_status") == "failed" else 1,
            safe_float(row.get("quality_score"), default=100.0),
            -safe_float(row.get("violations_per_100_timesteps"), default=0.0),
        ),
    )


def make_review_markdown(report: dict[str, Any]) -> str:
    queue = [row for row in report.get("review_queue", []) if isinstance(row, dict)]
    lines = [
        "# Project1 Batch Review Queue",
        "",
        "Scores listed here need manual review before polished delivery.",
        "",
        "| priority | score_id | quality | score | issues | rule report |",
        "|---:|---|---|---:|---|---|",
    ]
    if not queue:
        lines.append("|  | none | pass |  |  |  |")
    for idx, row in enumerate(queue, start=1):
        lines.append(
            "| {idx} | {score_id} | {quality_status} | {quality_score} | {issues} | {rule_report} |".format(
                idx=idx,
                score_id=row.get("score_id", ""),
                quality_status=row.get("quality_status", ""),
                quality_score=row.get("quality_score", ""),
                issues=str(row.get("quality_issues", "")).replace("|", "/"),
                rule_report=row.get("rule_report_json", ""),
            )
        )
    return "\n".join(lines) + "\n"


def safe_float(value: Any, *, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch harmonize user MusicXML files into SATB outputs.")
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", default="generated_scores/batch_user_harmonizations")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--task", default="soprano_to_satb", choices=["soprano_to_satb", "bass_to_satb", "masked_infill", "auto"])
    parser.add_argument("--input-role", default="soprano", choices=["soprano", "alto", "tenor", "bass"])
    parser.add_argument("--known-voices", default=None)
    parser.add_argument("--render-audio", action="store_true")
    parser.add_argument("--audio-backend", default="additive")
    parser.add_argument("--no-rule-guided", action="store_true")
    parser.add_argument("--no-symbolic-repair", action="store_true")
    parser.add_argument("--no-final-cadence-repair", action="store_true")
    parser.add_argument("--repair-passes", type=int, default=12)
    parser.add_argument("--max-violations-per-100", type=float, default=DEFAULT_MAX_VIOLATIONS_PER_100)
    parser.add_argument("--max-total-violations", type=int, default=DEFAULT_MAX_TOTAL_VIOLATIONS)
    parser.add_argument("--max-total-penalty", type=float, default=DEFAULT_MAX_TOTAL_PENALTY)
    parser.add_argument(
        "--max-seventh-resolution-violations",
        type=int,
        default=DEFAULT_MAX_SEVENTH_RESOLUTION_VIOLATIONS,
    )
    parser.add_argument("--require-audio-for-quality", action="store_true")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--stop-on-error", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    report = batch_harmonize(
        args.input_dir,
        args.output_dir,
        checkpoint=args.checkpoint,
        config=args.config,
        task=args.task,
        input_role=args.input_role,
        known_voices=args.known_voices,
        render_audio=args.render_audio,
        audio_backend=args.audio_backend,
        apply_rules=not args.no_rule_guided,
        optimize_symbols=not args.no_symbolic_repair,
        repair_passes=args.repair_passes,
        repair_final_cadence=not args.no_final_cadence_repair,
        max_violations_per_100=args.max_violations_per_100,
        max_total_violations=args.max_total_violations,
        max_total_penalty=args.max_total_penalty,
        max_seventh_resolution_violations=args.max_seventh_resolution_violations,
        require_audio_for_quality=args.require_audio_for_quality,
        recursive=args.recursive,
        stop_on_error=args.stop_on_error,
        limit=args.limit,
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
