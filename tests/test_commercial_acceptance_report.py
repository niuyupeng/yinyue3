from __future__ import annotations

import json
from pathlib import Path

from chorale.commercial_acceptance_report import build_acceptance_report, write_report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_acceptance_report_separates_engineering_pass_from_external_blockers(tmp_path: Path) -> None:
    _write_fixture(tmp_path, external_pass=False)

    report = build_acceptance_report(tmp_path)

    assert report["engineering_acceptance"] == "pass"
    assert report["commercial_release"] == "pending_external_evidence"
    assert report["commercial_readiness_score"] == 75
    assert report["evidence"]["review_issue_intake_status"] == "no_issue_files"
    assert report["evidence"]["customer_review_ready"] is False
    assert report["evidence"]["delivery_conformance_event_alignment_pass_count"] == 240
    assert report["evidence"]["delivery_conformance_min_event_recall"] == 1.0
    assert {item["gate"] for item in report["external_blockers"]} == {
        "returned_expert_evaluation",
        "commercial_legal_signoff",
    }


def test_acceptance_report_can_write_markdown(tmp_path: Path) -> None:
    _write_fixture(tmp_path, external_pass=True)
    report = build_acceptance_report(tmp_path)
    outputs = write_report(report, tmp_path / "acceptance.json")

    assert Path(outputs["json"]).is_file()
    assert Path(outputs["markdown"]).read_text(encoding="utf-8").startswith("# Project1")


def test_acceptance_report_marks_customer_review_ready_from_real_browser_qa(tmp_path: Path) -> None:
    _write_fixture(tmp_path, external_pass=False, real_browser_qa=True)

    report = build_acceptance_report(tmp_path)

    assert report["evidence"]["customer_review_ready"] is True
    assert report["evidence"]["customer_review_status"] == "ready_for_live_reviewer_delivery"
    assert report["evidence"]["customer_review_blockers"] == []


def _write_fixture(root: Path, *, external_pass: bool, real_browser_qa: bool = False) -> None:
    gates = [
        {"gate": "logged_full_experiments", "passed": True, "status": "pass", "evidence": "metrics"},
        {"gate": "commercial_delivery_package", "passed": True, "status": "pass", "evidence": "delivery"},
        {"gate": "delivery_integrity_verification", "passed": True, "status": "pass", "evidence": "integrity"},
        {"gate": "delivery_release_manifest", "passed": True, "status": "pass", "evidence": "release"},
        {"gate": "score_audio_traceability", "passed": True, "status": "pass", "evidence": "trace"},
        {"gate": "playback_license_notices", "passed": True, "status": "pass", "evidence": "license"},
        {"gate": "offline_player_browser_qa", "passed": True, "status": "pass", "evidence": "qa"},
        {"gate": "recipient_usability_audit", "passed": True, "status": "pass", "evidence": "recipient_usability"},
        {"gate": "paper_compile", "passed": True, "status": "pass", "evidence": "paper"},
        {"gate": "expert_rating_workflow", "passed": True, "status": "pass", "evidence": "workflow"},
        {"gate": "review_issue_intake_workflow", "passed": True, "status": "pass", "evidence": "issues"},
        {"gate": "issue_evidence_packet_workflow", "passed": True, "status": "pass", "evidence": "issue_packet"},
        {
            "gate": "returned_expert_evaluation",
            "passed": external_pass,
            "status": "pass" if external_pass else "expert evaluation pending",
            "evidence": "expert",
        },
        {
            "gate": "commercial_legal_signoff",
            "passed": external_pass,
            "status": "pass" if external_pass else "legal signoff pending",
            "evidence": "legal",
        },
    ]
    _write_json(
        root / "results" / "project1_commercial_readiness_audit.json",
        {"commercial_readiness_score": 100 if external_pass else 75, "all_pass": external_pass, "gates": gates},
    )
    _write_json(
        root / "results" / "project1_delivery_release_manifest_latest.json",
        {"zip_file": "delivery.zip", "zip_name": "delivery.zip", "zip_size_bytes": 1, "zip_sha256": "abc"},
    )
    _write_json(root / "results" / "project1_commercial_delivery_audit_latest.json", {"commercial_delivery_score": 100, "all_pass": True, "score_count": 40, "manifest_rows": 240, "mp3_count": 240, "midi_count": 240, "wav_count": 0})
    _write_json(root / "results" / "project1_pro_playback_traceability_audit_latest.json", {"score_audio_traceability_score": 100, "all_pass": True})
    _write_json(root / "results" / "project1_delivery_integrity_report_latest.json", {"all_pass": True, "checked_file_count": 835})
    _write_json(root / "results" / "project1_delivery_zip_integrity_report_latest.json", {"all_pass": True, "checked_file_count": 835})
    _write_json(root / "results" / "project1_playback_license_audit_latest.json", {"license_audit_score": 100, "all_pass": True})
    _write_json(
        root / "results" / "project1_delivery_player_qa_latest.json",
        {
            "status": "pass" if real_browser_qa else "fallback_static_pass",
            "browser_status": "pass" if real_browser_qa else "not_run",
            "package_dir": "delivery",
            "nav_items": 40,
            "audio_controls_initial": 7,
            "audio_controls_after_search": 7,
            "screenshot": "results/project1_delivery_player_qa_latest.png" if real_browser_qa else "",
        },
    )
    if real_browser_qa:
        (root / "results" / "project1_delivery_player_qa_latest.png").write_bytes(b"png")
    _write_json(root / "results" / "project1_delivery_player_static_audit_latest.json", {"status": "pass", "package_dir": "delivery", "bad_text_file_count": 0})
    _write_json(root / "results" / "project1_delivery_media_audit_latest.json", {"media_delivery_score": 100, "all_pass": True, "mp3_parse_ok_count": 240, "midi_parse_ok_count": 240})
    _write_json(
        root / "results" / "project1_delivery_conformance_audit_latest.json",
        {
            "conformance_score": 100,
            "all_pass": True,
            "mp3_audible_count": 240,
            "midi_render_pitch_check_pass_count": 240,
            "stem_target_check_pass_count": 240,
            "event_alignment_pass_count": 240,
            "min_event_recall": 1.0,
            "min_event_precision": 1.0,
            "min_duration_similarity": 1.0,
        },
    )
    _write_json(
        root / "results" / "project1_recipient_usability_audit_latest.json",
        {"recipient_usability_score": 100, "all_pass": True, "status": "pass", "issues": []},
    )
    _write_json(
        root / "results" / "project1_expert_eval_summary.json",
        {
            "status": "completed" if external_pass else "expert evaluation pending",
            "rating_file_count": 3 if external_pass else 0,
            "absolute_completed_rows": 30 if external_pass else 0,
            "paired_completed_rows": 30 if external_pass else 0,
        },
    )
    _write_json(
        root / "results" / "project1_review_issue_intake_latest.json",
        {
            "schema": "project1_review_issue_intake_v1",
            "status": "no_issue_files",
            "issue_file_count": 0,
            "accepted_issue_count": 0,
            "invalid_issue_count": 0,
            "unmatched_issue_count": 0,
            "needs_attention_count": 0,
        },
    )
    _write_json(
        root / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json",
        {
            "schema": "project1_commercial_legal_review_packet_v1",
            "status": "manual review required",
            "packet_dir": "results/project1_commercial_legal_review_packet",
            "delivery_zip": "delivery.zip",
            "delivery_zip_sha256": "abc",
        },
    )
