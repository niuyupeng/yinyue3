from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_MAX_VIOLATIONS_PER_100 = 12.0
DEFAULT_MAX_TOTAL_VIOLATIONS = 24
DEFAULT_MAX_TOTAL_PENALTY = 20.0
DEFAULT_MAX_SEVENTH_RESOLUTION_VIOLATIONS = 12


def evaluate_harmonization_quality(
    summary: dict[str, Any],
    *,
    max_violations_per_100: float = DEFAULT_MAX_VIOLATIONS_PER_100,
    max_total_violations: int = DEFAULT_MAX_TOTAL_VIOLATIONS,
    max_total_penalty: float = DEFAULT_MAX_TOTAL_PENALTY,
    max_seventh_resolution_violations: int = DEFAULT_MAX_SEVENTH_RESOLUTION_VIOLATIONS,
    require_audio: bool = False,
) -> dict[str, Any]:
    """Evaluate practical delivery readiness for one harmonized score.

    This gate is an engineering/music-rule screen, not a claim of artistic
    perfection. A `needs_review` result means the score was generated but should
    be inspected or edited before being sent as a polished deliverable.
    """
    outputs = summary.get("outputs", {}) if isinstance(summary.get("outputs"), dict) else {}
    audio = summary.get("audio", {}) if isinstance(summary.get("audio"), dict) else {}
    rule_summary = summary.get("rule_summary", {}) if isinstance(summary.get("rule_summary"), dict) else {}
    known_voice_preservation = (
        summary.get("known_voice_preservation", {})
        if isinstance(summary.get("known_voice_preservation"), dict)
        else {}
    )
    score_validation = (
        summary.get("score_validation", {})
        if isinstance(summary.get("score_validation"), dict)
        else {}
    )
    input_preflight = (
        summary.get("input_preflight", {})
        if isinstance(summary.get("input_preflight"), dict)
        else {}
    )
    issues: list[str] = []
    warnings: list[str] = []

    harmonized_musicxml = str(outputs.get("harmonized_musicxml", "") or "")
    if not harmonized_musicxml:
        issues.append("missing harmonized MusicXML path")
    elif not Path(harmonized_musicxml).is_file():
        issues.append(f"harmonized MusicXML file not found: {harmonized_musicxml}")

    rule_report_json = str(outputs.get("rule_report_json", "") or "")
    if not rule_report_json:
        issues.append("missing rule report path")
    elif not Path(rule_report_json).is_file():
        issues.append(f"rule report file not found: {rule_report_json}")

    total_penalty = safe_float(rule_summary.get("total_penalty"))
    total_violations = safe_int(rule_summary.get("total_violations"))
    violations_per_100 = safe_float(rule_summary.get("violations_per_100_timesteps"))
    seventh_violations = safe_int(rule_summary.get("seventh_resolution_violations"))

    if violations_per_100 is None:
        issues.append("missing violations_per_100_timesteps")
    elif violations_per_100 > float(max_violations_per_100):
        issues.append(
            f"violations_per_100_timesteps {violations_per_100:.3f} exceeds threshold {float(max_violations_per_100):.3f}"
        )
    if total_violations is None:
        issues.append("missing total_violations")
    elif total_violations > int(max_total_violations):
        issues.append(f"total_violations {total_violations} exceeds threshold {int(max_total_violations)}")
    if total_penalty is None:
        issues.append("missing total_penalty")
    elif total_penalty > float(max_total_penalty):
        issues.append(f"total_penalty {total_penalty:.3f} exceeds threshold {float(max_total_penalty):.3f}")
    if seventh_violations is not None and seventh_violations > int(max_seventh_resolution_violations):
        issues.append(
            "seventh_resolution_violations "
            f"{seventh_violations} exceeds threshold {int(max_seventh_resolution_violations)}"
        )

    if known_voice_preservation and not bool(known_voice_preservation.get("pass", False)):
        issues.append(
            "known input voice preservation failed: "
            f"{int(known_voice_preservation.get('mismatches', 0) or 0)} token mismatches"
        )

    if score_validation:
        if not bool(score_validation.get("parse_ok", False)):
            issues.append(f"MusicXML parse failed: {score_validation.get('error', 'unknown error')}")
        part_count = score_validation.get("part_count")
        if part_count not in ("", None) and int(part_count) != 4:
            issues.append(f"expected 4 SATB parts, found {int(part_count)}")
        if score_validation.get("has_notes") is False:
            issues.append("exported score contains no notes")

    if str(rule_summary.get("cadence_type", "")).upper() == "UNKNOWN":
        warnings.append("cadence_type is UNKNOWN; automatic cadence evidence was insufficient")

    preflight_status = str(input_preflight.get("status", "") or "").lower()
    if preflight_status == "failed":
        issues.append(
            "input score preflight failed: "
            + "; ".join(input_preflight.get("critical", []) or input_preflight.get("issues", []) or ["unknown reason"])
        )
    elif preflight_status == "needs_review":
        issues.append(
            "input score preflight needs review: "
            + "; ".join(input_preflight.get("issues", []) or ["review input warnings"])
        )
    elif input_preflight and preflight_status != "pass":
        warnings.append("input score preflight status is unavailable")

    if require_audio:
        wav_status = str(audio.get("wav_status", "") or "")
        if wav_status != "ok":
            issues.append(f"required WAV audio is not ok: {wav_status or 'missing'}")
        mp3_status = str(audio.get("mp3_status", "") or "")
        if mp3_status not in {"ok", "skipped"}:
            issues.append(f"MP3 audio status is not ok/skipped: {mp3_status or 'missing'}")

    def is_hard_failure(item: str) -> bool:
        return (
            item.startswith("missing harmonized MusicXML path")
            or item.startswith("missing rule report path")
            or "file not found" in item
            or "known input voice preservation failed" in item
            or "MusicXML parse failed" in item
            or "expected 4 SATB parts" in item
            or "exported score contains no notes" in item
            or "input score preflight failed" in item
        )

    if any(is_hard_failure(item) for item in issues):
        status = "failed"
    elif issues:
        status = "needs_review"
    else:
        status = "pass"

    return {
        "status": status,
        "score": rule_gate_score(
            total_penalty=total_penalty,
            total_violations=total_violations,
            violations_per_100=violations_per_100,
            failed=status == "failed",
        ),
        "issues": issues,
        "warnings": warnings,
        "thresholds": {
            "max_violations_per_100": float(max_violations_per_100),
            "max_total_violations": int(max_total_violations),
            "max_total_penalty": float(max_total_penalty),
            "max_seventh_resolution_violations": int(max_seventh_resolution_violations),
            "require_audio": bool(require_audio),
        },
    }


def rule_gate_score(
    *,
    total_penalty: float | None,
    total_violations: int | None,
    violations_per_100: float | None,
    failed: bool,
) -> float:
    if failed:
        return 0.0
    score = 100.0
    if violations_per_100 is not None:
        score -= min(55.0, max(0.0, violations_per_100) * 2.0)
    if total_violations is not None:
        score -= min(25.0, max(0, total_violations) * 0.35)
    if total_penalty is not None:
        score -= min(20.0, max(0.0, total_penalty) * 0.25)
    return round(max(0.0, min(100.0, score)), 3)


def safe_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def safe_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
