from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


EXTERNAL_BLOCKERS = {"returned_expert_evaluation", "commercial_legal_signoff"}


def build_acceptance_report(root: str | Path = ".") -> dict[str, object]:
    root_path = Path(root)
    readiness = read_json(root_path / "results" / "project1_commercial_readiness_audit.json")
    release = read_json(root_path / "results" / "project1_delivery_release_manifest_latest.json")
    delivery = read_json(root_path / "results" / "project1_commercial_delivery_audit_latest.json")
    traceability = read_json(root_path / "results" / "project1_pro_playback_traceability_audit_latest.json")
    folder_integrity = read_json(root_path / "results" / "project1_delivery_integrity_report_latest.json")
    zip_integrity = read_json(root_path / "results" / "project1_delivery_zip_integrity_report_latest.json")
    license_audit = read_json(root_path / "results" / "project1_playback_license_audit_latest.json")
    player_qa = read_json(root_path / "results" / "project1_delivery_player_qa_latest.json")
    player_static = read_json(root_path / "results" / "project1_delivery_player_static_audit_latest.json")
    media_audit = read_json(root_path / "results" / "project1_delivery_media_audit_latest.json")
    conformance_audit = read_json(root_path / "results" / "project1_delivery_conformance_audit_latest.json")
    recipient_usability = read_json(root_path / "results" / "project1_recipient_usability_audit_latest.json")
    expert = read_json(root_path / "results" / "project1_expert_eval_summary.json")
    review_issues = read_json(root_path / "results" / "project1_review_issue_intake_latest.json")
    legal_packet = read_json(root_path / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json")
    legal_packet_matches_release = packet_matches_release(release, legal_packet)
    customer_review = customer_review_status(root_path, release, player_qa)

    gates = readiness.get("gates", [])
    if not isinstance(gates, list):
        gates = []
    engineering_gates = [
        gate for gate in gates if isinstance(gate, dict) and gate.get("gate") not in EXTERNAL_BLOCKERS
    ]
    external_gates = [
        gate for gate in gates if isinstance(gate, dict) and gate.get("gate") in EXTERNAL_BLOCKERS
    ]
    engineering_pass = bool(engineering_gates) and all(bool(gate.get("passed")) for gate in engineering_gates)
    external_pass = bool(external_gates) and all(bool(gate.get("passed")) for gate in external_gates)

    deliverable = {
        "zip_file": release.get("zip_file"),
        "zip_name": release.get("zip_name"),
        "zip_size_bytes": release.get("zip_size_bytes"),
        "zip_sha256": release.get("zip_sha256"),
        "zip_regular_file_count": release.get("zip_regular_file_count"),
        "score_count": delivery.get("score_count"),
        "manifest_rows": delivery.get("manifest_rows"),
        "file_count": delivery.get("file_count"),
        "mp3_count": delivery.get("mp3_count"),
        "midi_count": delivery.get("midi_count"),
        "wav_count": delivery.get("wav_count"),
    }
    evidence = {
        "commercial_delivery_score": delivery.get("commercial_delivery_score"),
        "commercial_delivery_all_pass": delivery.get("all_pass"),
        "commercial_delivery_file_count": delivery.get("file_count"),
        "folder_integrity_all_pass": folder_integrity.get("all_pass"),
        "folder_integrity_checked_file_count": folder_integrity.get("checked_file_count"),
        "zip_integrity_all_pass": zip_integrity.get("all_pass"),
        "zip_integrity_checked_file_count": zip_integrity.get("checked_file_count"),
        "score_audio_traceability_score": traceability.get("score_audio_traceability_score"),
        "score_audio_traceability_all_pass": traceability.get("all_pass"),
        "license_audit_score": license_audit.get("license_audit_score"),
        "license_audit_all_pass": license_audit.get("all_pass"),
        "offline_player_qa_status": player_qa.get("status"),
        "customer_review_ready": customer_review["ready"],
        "customer_review_status": customer_review["status"],
        "customer_review_blockers": customer_review["blockers"],
        "offline_player_nav_items": player_qa.get("nav_items"),
        "offline_player_static_status": player_static.get("status"),
        "offline_player_static_package": player_static.get("package_dir"),
        "offline_player_static_bad_text_file_count": player_static.get("bad_text_file_count"),
        "delivery_media_audit_score": media_audit.get("media_delivery_score"),
        "delivery_media_audit_all_pass": media_audit.get("all_pass"),
        "delivery_media_mp3_parse_ok_count": media_audit.get("mp3_parse_ok_count"),
        "delivery_media_midi_parse_ok_count": media_audit.get("midi_parse_ok_count"),
        "delivery_conformance_score": conformance_audit.get("conformance_score"),
        "delivery_conformance_all_pass": conformance_audit.get("all_pass"),
        "delivery_conformance_mp3_audible_count": conformance_audit.get("mp3_audible_count"),
        "delivery_conformance_pitch_check_pass_count": conformance_audit.get("midi_render_pitch_check_pass_count"),
        "delivery_conformance_stem_target_pass_count": conformance_audit.get("stem_target_check_pass_count"),
        "delivery_conformance_event_alignment_pass_count": conformance_audit.get("event_alignment_pass_count"),
        "delivery_conformance_min_event_recall": conformance_audit.get("min_event_recall"),
        "delivery_conformance_min_event_precision": conformance_audit.get("min_event_precision"),
        "delivery_conformance_min_duration_similarity": conformance_audit.get("min_duration_similarity"),
        "recipient_usability_score": recipient_usability.get("recipient_usability_score"),
        "recipient_usability_all_pass": recipient_usability.get("all_pass"),
        "recipient_usability_status": recipient_usability.get("status"),
        "recipient_usability_issue_count": len(recipient_usability.get("issues", []))
        if isinstance(recipient_usability.get("issues"), list)
        else None,
        "expert_rating_file_count": expert.get("rating_file_count"),
        "expert_absolute_completed_rows": expert.get("absolute_completed_rows"),
        "expert_paired_completed_rows": expert.get("paired_completed_rows"),
        "expert_status": expert.get("status"),
        "review_issue_intake_status": review_issues.get("status"),
        "review_issue_file_count": review_issues.get("issue_file_count"),
        "review_issue_accepted_count": review_issues.get("accepted_issue_count"),
        "review_issue_invalid_count": review_issues.get("invalid_issue_count"),
        "review_issue_unmatched_count": review_issues.get("unmatched_issue_count"),
        "review_issue_needs_attention_count": review_issues.get("needs_attention_count"),
        "legal_review_packet_status": legal_packet.get("status"),
        "legal_review_packet_dir": legal_packet.get("packet_dir"),
        "legal_review_packet_delivery_zip": legal_packet.get("delivery_zip"),
        "legal_review_packet_delivery_zip_sha256": legal_packet.get("delivery_zip_sha256"),
        "legal_review_packet_matches_release": legal_packet_matches_release,
    }
    blocking = [
        {
            "gate": gate.get("gate"),
            "status": gate.get("status"),
            "evidence": gate.get("evidence"),
        }
        for gate in external_gates
        if not gate.get("passed")
    ]
    report = {
        "schema": "project1_commercial_acceptance_report_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engineering_acceptance": "pass" if engineering_pass else "failed",
        "commercial_release": "ready" if engineering_pass and external_pass else "pending_external_evidence",
        "commercial_readiness_score": readiness.get("commercial_readiness_score"),
        "all_commercial_gates_pass": readiness.get("all_pass"),
        "deliverable": deliverable,
        "evidence": evidence,
        "passed_engineering_gates": [gate.get("gate") for gate in engineering_gates if gate.get("passed")],
        "failed_engineering_gates": [
            {"gate": gate.get("gate"), "status": gate.get("status"), "evidence": gate.get("evidence")}
            for gate in engineering_gates
            if not gate.get("passed")
        ],
        "external_blockers": blocking,
        "required_next_steps": required_next_steps(blocking),
        "legal_review_packet": {
            "status": legal_packet.get("status"),
            "packet_dir": legal_packet.get("packet_dir"),
            "summary": "results/project1_commercial_legal_review_packet/LEGAL_PACKET_SUMMARY.json"
            if legal_packet
            else None,
        },
        "non_substitutable_evidence_note": (
            "Expert ratings and legal/commercial signoff must be real external evidence; "
            "this report does not fabricate or replace them."
        ),
        "manifest_counting_note": (
            "The delivery ZIP file count may exceed the integrity checked file count because "
            "self-referential manifest and integrity-report files are intentionally excluded from "
            "their own hash manifest."
        ),
    }
    return report


def required_next_steps(blocking: list[dict[str, object]]) -> list[str]:
    steps: list[str] = []
    gates = {str(item.get("gate")) for item in blocking}
    if "returned_expert_evaluation" in gates:
        steps.append(
            "Collect at least three completed expert rating workbooks in expert_eval/project1/returned_ratings and run scripts/summarize_project1_expert_ratings.ps1."
        )
    if "commercial_legal_signoff" in gates:
        steps.append(
            "Complete a real legal/commercial redistribution review and write results/project1_commercial_legal_signoff.json only when approved."
        )
    return steps


def write_report(report: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(report), encoding="utf-8")
    return {"json": str(out_json), "markdown": str(out_md)}


def make_markdown(report: dict[str, object]) -> str:
    deliverable = report.get("deliverable", {})
    evidence = report.get("evidence", {})
    lines = [
        "# Project1 Commercial Acceptance Report",
        "",
        f"Engineering acceptance: **{report.get('engineering_acceptance')}**",
        f"Commercial release: **{report.get('commercial_release')}**",
        f"Commercial readiness score: **{report.get('commercial_readiness_score')}/100**",
        "",
        "## Deliverable",
        "",
    ]
    if isinstance(deliverable, dict):
        for key in [
            "zip_name",
            "zip_size_bytes",
            "zip_sha256",
            "zip_regular_file_count",
            "score_count",
            "file_count",
            "mp3_count",
            "midi_count",
            "manifest_rows",
        ]:
            lines.append(f"- {key}: `{deliverable.get(key)}`")
    lines.extend(["", "## Engineering Evidence", ""])
    if isinstance(evidence, dict):
        for key in [
            "commercial_delivery_score",
            "commercial_delivery_all_pass",
            "commercial_delivery_file_count",
            "folder_integrity_all_pass",
            "folder_integrity_checked_file_count",
            "zip_integrity_all_pass",
            "zip_integrity_checked_file_count",
            "score_audio_traceability_score",
            "score_audio_traceability_all_pass",
            "license_audit_score",
            "license_audit_all_pass",
            "offline_player_qa_status",
            "customer_review_ready",
            "customer_review_status",
            "customer_review_blockers",
            "offline_player_static_status",
            "offline_player_static_package",
            "offline_player_static_bad_text_file_count",
            "delivery_media_audit_score",
            "delivery_media_audit_all_pass",
            "delivery_media_mp3_parse_ok_count",
            "delivery_media_midi_parse_ok_count",
            "delivery_conformance_score",
            "delivery_conformance_all_pass",
            "delivery_conformance_mp3_audible_count",
            "delivery_conformance_pitch_check_pass_count",
            "delivery_conformance_stem_target_pass_count",
            "delivery_conformance_event_alignment_pass_count",
            "delivery_conformance_min_event_recall",
            "delivery_conformance_min_event_precision",
            "delivery_conformance_min_duration_similarity",
            "recipient_usability_score",
            "recipient_usability_all_pass",
            "recipient_usability_status",
            "recipient_usability_issue_count",
            "review_issue_intake_status",
            "review_issue_file_count",
            "review_issue_accepted_count",
            "review_issue_invalid_count",
            "review_issue_unmatched_count",
            "review_issue_needs_attention_count",
            "legal_review_packet_status",
            "legal_review_packet_delivery_zip",
            "legal_review_packet_delivery_zip_sha256",
            "legal_review_packet_matches_release",
        ]:
            lines.append(f"- {key}: `{evidence.get(key)}`")
    blockers = report.get("external_blockers", [])
    lines.extend(["", "## External Blockers", ""])
    if isinstance(blockers, list) and blockers:
        for blocker in blockers:
            if isinstance(blocker, dict):
                lines.append(f"- {blocker.get('gate')}: {blocker.get('status')}")
    else:
        lines.append("No external blockers recorded.")
    steps = report.get("required_next_steps", [])
    lines.extend(["", "## Required Next Steps", ""])
    if isinstance(steps, list) and steps:
        lines.extend(f"- {step}" for step in steps)
    else:
        lines.append("No required next steps recorded.")
    lines.extend(
        [
            "",
            str(report.get("manifest_counting_note", "")),
            "",
            str(report.get("non_substitutable_evidence_note", "")),
            "",
        ]
    )
    return "\n".join(lines)


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def packet_matches_release(release: dict[str, object], legal_packet: dict[str, object]) -> bool:
    release_zip = str(release.get("zip_file", "")).replace("\\", "/").strip()
    packet_zip = str(legal_packet.get("delivery_zip", "")).replace("\\", "/").strip()
    release_sha = str(release.get("zip_sha256", "")).strip()
    packet_sha = str(legal_packet.get("delivery_zip_sha256", "")).strip()
    return bool(release_zip and release_sha) and release_zip == packet_zip and release_sha == packet_sha


def customer_review_status(root: Path, release: dict[str, object], player_qa: dict[str, object]) -> dict[str, object]:
    release_zip = Path(str(release.get("zip_file", "")))
    expected_package = release_zip.with_suffix("") if release_zip.suffix.lower() == ".zip" else Path("")
    package_dir = Path(str(player_qa.get("package_dir", "")))
    package_matches = bool(expected_package) and normalize_path(package_dir) == normalize_path(expected_package)
    screenshot = Path(str(player_qa.get("screenshot", "")))
    screenshot_path = screenshot if screenshot.is_absolute() else root / screenshot
    screenshot_ok = bool(str(screenshot)) and screenshot_path.is_file()
    browser_status = str(player_qa.get("browser_status", "pass"))
    ready = (
        player_qa.get("status") == "pass"
        and browser_status not in {"failed", "not_run", "unavailable"}
        and int(player_qa.get("nav_items", 0) or 0) >= 40
        and int(player_qa.get("audio_controls_initial", 0) or 0) >= 6
        and int(player_qa.get("audio_controls_after_search", 0) or 0) >= 6
        and package_matches
        and screenshot_ok
    )
    blockers = [] if ready else ["real_browser_player_qa"]
    return {
        "ready": ready,
        "status": "ready_for_live_reviewer_delivery" if ready else "blocked_until_real_browser_qa",
        "blockers": blockers,
    }


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/").rstrip("/").lower()


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Project1 commercial acceptance report.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-json", default="results/project1_commercial_acceptance_report_latest.json")
    args = parser.parse_args()
    report = build_acceptance_report(args.root)
    outputs = write_report(report, args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
