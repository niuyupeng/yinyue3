from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from music21 import converter


DEFAULT_BATCH_SUMMARY = "generated_scores/batch_user_harmonize_authentic_cadence_smoke_v3/batch_harmonization_summary.json"


@dataclass
class Gate:
    gate: str
    weight: int
    passed: bool
    status: str
    evidence: str
    details: dict[str, Any]

    @property
    def achieved(self) -> int:
        return self.weight if self.passed else 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate": self.gate,
            "weight": self.weight,
            "achieved": self.achieved,
            "passed": self.passed,
            "status": self.status,
            "evidence": self.evidence,
            "details": self.details,
        }


def build_music_functionality_audit(
    root: str | Path = ".",
    *,
    batch_summary: str | Path = DEFAULT_BATCH_SUMMARY,
) -> dict[str, Any]:
    root_path = Path(root)
    batch_path = root_path / batch_summary
    batch = read_json(batch_path)
    media = read_json(root_path / "results/project1_delivery_media_audit_latest.json")
    conformance = read_json(root_path / "results/project1_delivery_conformance_audit_latest.json")
    traceability = read_json(root_path / "results/project1_pro_playback_traceability_audit_latest.json")
    player_static = read_json(root_path / "results/project1_delivery_player_static_audit_latest.json")
    player_browser = read_json(root_path / "results/project1_delivery_player_qa_latest.json")

    gates = [
        gate_batch_generation(batch, str(batch_summary)),
        gate_satb_musicxml(root_path, batch, str(batch_summary)),
        gate_known_voice_preservation(batch, str(batch_summary)),
        gate_rule_reports_and_repair(root_path, batch, str(batch_summary)),
        gate_score_audio_assets(media),
        gate_score_audio_conformance(conformance),
        gate_traceability_variants(traceability),
        gate_offline_player(root_path, player_static, player_browser),
    ]
    score = sum(gate.achieved for gate in gates)
    total = sum(gate.weight for gate in gates)
    all_pass = score == total and all(gate.passed for gate in gates)
    return {
        "schema": "project1_music_functionality_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "music_functionality_score": score,
        "total_weight": total,
        "all_pass": all_pass,
        "status": "music functionality pass" if all_pass else "music functionality incomplete",
        "scope_note": (
            "This audit checks practical music functionality only: score input, SATB generation, "
            "known-voice preservation, MusicXML output, rule reports, score-derived playback assets, "
            "score-audio conformance, and the offline reviewer player. It intentionally excludes "
            "human expert preference ratings and legal/commercial signoff."
        ),
        "gates": [gate.as_dict() for gate in gates],
        "blocking_items": [gate.gate for gate in gates if not gate.passed],
    }


def gate_batch_generation(batch: dict[str, Any], evidence: str) -> Gate:
    rows = list_rows(batch)
    completed = as_int(batch.get("completed"), 0)
    failed = as_int(batch.get("failed"), 0)
    quality_pass = as_int(batch.get("quality_pass"), 0)
    needs_review = as_int(batch.get("needs_review"), 0)
    preflight_ok = all(str(row.get("input_preflight_status", "")) == "pass" for row in rows) if rows else False
    engines_ok = all(str(row.get("engine", "")).strip() for row in rows) if rows else False
    passed = (
        completed >= 3
        and failed == 0
        and quality_pass == completed
        and needs_review == 0
        and bool(batch.get("all_quality_pass")) is True
        and preflight_ok
        and engines_ok
    )
    status = "pass" if passed else "batch generation/preflight evidence incomplete"
    return Gate(
        "input_preflight_and_batch_generation",
        15,
        passed,
        status,
        evidence,
        {
            "completed": completed,
            "failed": failed,
            "quality_pass": quality_pass,
            "needs_review": needs_review,
            "all_quality_pass": batch.get("all_quality_pass"),
            "preflight_ok": preflight_ok,
            "engines_ok": engines_ok,
        },
    )


def gate_satb_musicxml(root: Path, batch: dict[str, Any], evidence: str) -> Gate:
    rows = list_rows(batch)
    checks = []
    for row in rows:
        path = root / str(row.get("harmonized_musicxml", ""))
        parsed = inspect_musicxml_score(path)
        checks.append(
            {
                "score_id": row.get("score_id"),
                "file_exists": path.is_file(),
                "score_parse_ok": bool(row.get("score_parse_ok")),
                "score_part_count": as_int(row.get("score_part_count"), 0),
                "score_note_count": as_int(row.get("score_note_count"), 0),
                "audit_parse_ok": parsed["parse_ok"],
                "audit_part_count": parsed["part_count"],
                "audit_note_count": parsed["note_count"],
                "audit_parse_error": parsed["parse_error"],
            }
        )
    passed = bool(checks) and all(
        item["file_exists"]
        and item["score_parse_ok"]
        and item["score_part_count"] == 4
        and item["score_note_count"] > 0
        and item["audit_parse_ok"]
        and item["audit_part_count"] == 4
        and item["audit_note_count"] > 0
        for item in checks
    )
    status = "pass" if passed else "one or more SATB MusicXML exports are missing or invalid"
    return Gate("satb_musicxml_export", 15, passed, status, evidence, {"scores": checks})


def gate_known_voice_preservation(batch: dict[str, Any], evidence: str) -> Gate:
    rows = list_rows(batch)
    checks = [
        {
            "score_id": row.get("score_id"),
            "known_voices": row.get("known_voices"),
            "known_voice_preservation_pass": bool(row.get("known_voice_preservation_pass")),
            "known_voice_mismatches": as_int(row.get("known_voice_mismatches"), 0),
        }
        for row in rows
    ]
    passed = bool(checks) and all(
        item["known_voice_preservation_pass"] and item["known_voice_mismatches"] == 0 for item in checks
    )
    status = "pass" if passed else "known input voice was not proven preserved"
    return Gate("known_voice_preservation", 10, passed, status, evidence, {"scores": checks})


def gate_rule_reports_and_repair(root: Path, batch: dict[str, Any], evidence: str) -> Gate:
    rows = list_rows(batch)
    checks = []
    for row in rows:
        rule_report = root / str(row.get("rule_report_json", ""))
        summary = root / str(row.get("summary_json", ""))
        checks.append(
            {
                "score_id": row.get("score_id"),
                "rule_report_exists": rule_report.is_file(),
                "summary_exists": summary.is_file(),
                "quality_status": row.get("quality_status"),
                "violations_per_100_timesteps": as_float(row.get("violations_per_100_timesteps"), 9999.0),
                "symbolic_repair_enabled": bool(row.get("symbolic_repair_enabled")),
                "symbolic_accepted_repairs": as_int(row.get("symbolic_accepted_repairs"), 0),
                "cadential_repair_enabled": bool(row.get("cadential_repair_enabled")),
                "cadence_type": row.get("cadence_type"),
            }
        )
    passed = bool(checks) and all(
        item["rule_report_exists"]
        and item["summary_exists"]
        and item["quality_status"] == "pass"
        and item["violations_per_100_timesteps"] <= 12.0
        and item["symbolic_repair_enabled"]
        and item["cadential_repair_enabled"]
        and item["cadence_type"] not in ("", None, "UNKNOWN")
        for item in checks
    )
    status = "pass" if passed else "rule-report, repair, or cadence evidence incomplete"
    return Gate("rule_reports_and_symbolic_repair", 10, passed, status, evidence, {"scores": checks})


def gate_score_audio_assets(media: dict[str, Any]) -> Gate:
    entry_count = as_int(media.get("entry_count"), 0)
    passed = (
        bool(media.get("all_pass")) is True
        and as_int(media.get("media_delivery_score"), 0) == 100
        and entry_count >= 240
        and as_int(media.get("mp3_parse_ok_count"), 0) == entry_count
        and as_int(media.get("midi_parse_ok_count"), 0) == entry_count
        and as_float(media.get("max_abs_duration_delta_sec"), 9999.0) <= 0.5
    )
    status = "pass" if passed else "MP3/MIDI parse or duration evidence incomplete"
    return Gate(
        "score_derived_audio_assets",
        15,
        passed,
        status,
        "results/project1_delivery_media_audit_latest.json",
        {
            "media_delivery_score": media.get("media_delivery_score"),
            "entry_count": entry_count,
            "mp3_parse_ok_count": media.get("mp3_parse_ok_count"),
            "midi_parse_ok_count": media.get("midi_parse_ok_count"),
            "max_abs_duration_delta_sec": media.get("max_abs_duration_delta_sec"),
        },
    )


def gate_score_audio_conformance(conformance: dict[str, Any]) -> Gate:
    entry_count = as_int(conformance.get("entry_count"), 0)
    passed = (
        bool(conformance.get("all_pass")) is True
        and as_int(conformance.get("conformance_score"), 0) == 100
        and entry_count >= 240
        and as_int(conformance.get("mp3_audible_count"), 0) == entry_count
        and as_int(conformance.get("midi_render_pitch_check_pass_count"), 0) == entry_count
        and as_int(conformance.get("stem_target_check_pass_count"), 0) == entry_count
        and as_int(conformance.get("event_alignment_pass_count"), 0) == entry_count
        and as_float(conformance.get("min_pitch_similarity"), 0.0) >= 0.9
        and as_float(conformance.get("min_event_recall"), 0.0) >= 0.98
        and as_float(conformance.get("min_event_precision"), 0.0) >= 0.98
        and as_float(conformance.get("min_duration_similarity"), 0.0) >= 0.95
        and as_float(conformance.get("min_mp3_rms"), 0.0) > 0.0
    )
    status = "pass" if passed else "score-audio pitch, event alignment, stem, or audibility conformance incomplete"
    return Gate(
        "score_audio_conformance",
        15,
        passed,
        status,
        "results/project1_delivery_conformance_audit_latest.json",
        {
            "conformance_score": conformance.get("conformance_score"),
            "entry_count": entry_count,
            "mp3_audible_count": conformance.get("mp3_audible_count"),
            "midi_render_pitch_check_pass_count": conformance.get("midi_render_pitch_check_pass_count"),
            "stem_target_check_pass_count": conformance.get("stem_target_check_pass_count"),
            "event_alignment_pass_count": conformance.get("event_alignment_pass_count"),
            "min_pitch_similarity": conformance.get("min_pitch_similarity"),
            "min_event_recall": conformance.get("min_event_recall"),
            "min_event_precision": conformance.get("min_event_precision"),
            "min_duration_similarity": conformance.get("min_duration_similarity"),
            "min_mp3_rms": conformance.get("min_mp3_rms"),
        },
    )


def gate_traceability_variants(traceability: dict[str, Any]) -> Gate:
    summary = ensure_dict(traceability.get("summary"))
    by_variant = ensure_dict(summary.get("by_variant"))
    required_variants = ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]
    score_count = as_int(summary.get("score_count"), 0)
    variant_ok = score_count > 0 and all(as_int(by_variant.get(name), 0) >= score_count for name in required_variants)
    passed = (
        bool(traceability.get("all_pass")) is True
        and as_int(traceability.get("score_audio_traceability_score"), 0) == 100
        and as_int(summary.get("entry_count"), 0) >= 240
        and as_int(summary.get("fail_count"), 9999) == 0
        and as_int(summary.get("issue_count"), 9999) == 0
        and variant_ok
    )
    status = "pass" if passed else "score/audio traceability or playback-variant coverage incomplete"
    return Gate(
        "score_audio_traceability_and_variants",
        10,
        passed,
        status,
        "results/project1_pro_playback_traceability_audit_latest.json",
        {
            "score_audio_traceability_score": traceability.get("score_audio_traceability_score"),
            "entry_count": summary.get("entry_count"),
            "score_count": score_count,
            "fail_count": summary.get("fail_count"),
            "issue_count": summary.get("issue_count"),
            "by_variant": by_variant,
        },
    )


def gate_offline_player(root: Path, player_static: dict[str, Any], player_browser: dict[str, Any]) -> Gate:
    static_variants = ensure_dict(player_static.get("variant_counts"))
    score_count = as_int(player_static.get("score_count"), 0)
    static_ok = (
        bool(player_static.get("all_pass")) is True
        and score_count >= 40
        and as_int(player_static.get("manifest_rows"), 0) >= 240
        and as_int(player_static.get("missing_reference_count"), 9999) == 0
        and as_int(player_static.get("bad_text_file_count"), 9999) == 0
        and all(
            as_int(static_variants.get(name), 0) >= score_count
            for name in ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]
        )
    )
    screenshot = Path(str(player_browser.get("screenshot", "")))
    if not screenshot.is_absolute():
        screenshot = root / screenshot
    browser_ok = (
        str(player_browser.get("status")) == "pass"
        and as_int(player_browser.get("nav_items"), 0) >= 40
        and as_int(player_browser.get("audio_controls_initial"), 0) >= 6
        and as_int(player_browser.get("audio_controls_after_search"), 0) >= 6
        and screenshot.is_file()
        and not player_browser.get("issues")
    )
    passed = static_ok and browser_ok
    status = "pass" if passed else "offline player static or real browser playback QA incomplete"
    return Gate(
        "offline_score_audio_player",
        10,
        passed,
        status,
        "results/project1_delivery_player_static_audit_latest.json; results/project1_delivery_player_qa_latest.json",
        {
            "static_all_pass": player_static.get("all_pass"),
            "score_count": score_count,
            "manifest_rows": player_static.get("manifest_rows"),
            "missing_reference_count": player_static.get("missing_reference_count"),
            "bad_text_file_count": player_static.get("bad_text_file_count"),
            "browser_status": player_browser.get("status"),
            "browser": player_browser.get("browser"),
            "nav_items": player_browser.get("nav_items"),
            "audio_controls_initial": player_browser.get("audio_controls_initial"),
            "audio_controls_after_search": player_browser.get("audio_controls_after_search"),
            "screenshot": player_browser.get("screenshot"),
        },
    )


def list_rows(batch: dict[str, Any]) -> list[dict[str, Any]]:
    rows = batch.get("rows", [])
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def ensure_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def inspect_musicxml_score(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"parse_ok": False, "part_count": 0, "note_count": 0, "parse_error": "missing file"}
    try:
        score = converter.parse(str(path))
        part_count = len(list(score.parts))
        note_count = sum(1 for _ in score.recurse().notes)
        return {"parse_ok": True, "part_count": part_count, "note_count": note_count, "parse_error": ""}
    except Exception as exc:  # pragma: no cover - exact music21 parser errors vary by backend.
        return {"parse_ok": False, "part_count": 0, "note_count": 0, "parse_error": str(exc)}


def as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_float(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def make_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Project1 音乐实用功能 100 分审计",
        "",
        f"- 功能得分：`{report.get('music_functionality_score')}/{report.get('total_weight')}`",
        f"- 状态：`{report.get('status')}`",
        "",
        str(report.get("scope_note", "")),
        "",
        "## 功能门槛",
        "",
        "| 功能门槛 | 分值 | 状态 | 证据 |",
        "|---|---:|---|---|",
    ]
    for gate in report.get("gates", []):
        if not isinstance(gate, dict):
            continue
        status = "PASS" if gate.get("passed") else "BLOCKED"
        lines.append(
            f"| `{gate.get('gate')}` | {gate.get('achieved')}/{gate.get('weight')} | {status}: {gate.get('status')} | `{gate.get('evidence')}` |"
        )
    blockers = report.get("blocking_items", [])
    lines.extend(["", "## 阻塞项", ""])
    if blockers:
        lines.extend(f"- `{item}`" for item in blockers if isinstance(item, str))
    else:
        lines.append("- 无。音乐实用功能审计通过。")
    lines.extend(
        [
            "",
            "## 解释边界",
            "",
            "该审计只说明系统的音乐实用功能证据齐全：能够接收谱面输入、生成 SATB、导出 MusicXML、给出规则报告、生成谱面派生试听音频，并通过谱面-音频一致性与离线播放器检查。它不等同于专家偏好评价、法律/商业授权签核，也不声明真人演唱音频或世界顶级音乐生成。",
        ]
    )
    return "\n".join(lines) + "\n"


def write_audit(
    root: str | Path = ".",
    *,
    batch_summary: str | Path = DEFAULT_BATCH_SUMMARY,
    out_json: str | Path = "results/project1_music_functionality_audit_latest.json",
) -> dict[str, str]:
    report = build_music_functionality_audit(root, batch_summary=batch_summary)
    out = Path(root) / out_json
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8-sig")
    md = out.with_suffix(".md")
    md.write_text(make_markdown(report), encoding="utf-8-sig")
    return {"json": str(out), "markdown": str(md)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Project1 practical music functionality.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--batch-summary", default=DEFAULT_BATCH_SUMMARY)
    parser.add_argument("--out-json", default="results/project1_music_functionality_audit_latest.json")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero unless the music functionality score is 100/100.")
    args = parser.parse_args()
    report = build_music_functionality_audit(args.root, batch_summary=args.batch_summary)
    outputs = write_audit(args.root, batch_summary=args.batch_summary, out_json=args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))
    if args.strict and not report["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
