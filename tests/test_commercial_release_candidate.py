from __future__ import annotations

import hashlib
import json
from pathlib import Path

from chorale.commercial_release_candidate import build_release_candidate_report


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_candidate_fixture(
    root: Path,
    *,
    static_package_stale: bool = False,
    chrome_package_stale: bool = False,
    legal_packet_stale: bool = False,
    real_browser_qa: bool = False,
) -> None:
    zip_path = root / "expert_eval" / "project1" / "deliverables" / "delivery.zip"
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    zip_path.write_bytes(b"delivery")
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    package_dir = zip_path.with_suffix("")
    package_dir.mkdir()
    static_package = root / "expert_eval" / "project1" / "deliverables" / "old_delivery"
    if not static_package_stale:
        static_package = package_dir
    chrome_package = root / "expert_eval" / "project1" / "deliverables" / "old_delivery"
    if not chrome_package_stale:
        chrome_package = package_dir

    _write_json(
        root / "results" / "project1_delivery_release_manifest_latest.json",
        {
            "zip_file": str(zip_path.relative_to(root)),
            "zip_name": zip_path.name,
            "zip_size_bytes": zip_path.stat().st_size,
            "zip_sha256": sha,
            "zip_regular_file_count": 1,
            "commercial_delivery_all_pass": True,
            "folder_integrity_all_pass": True,
            "zip_integrity_all_pass": True,
            "score_count": 40,
            "mp3_count": 240,
            "midi_count": 240,
            "manifest_rows": 240,
        },
    )
    _write_json(root / "results" / "project1_commercial_delivery_audit_latest.json", {"all_pass": True, "commercial_delivery_score": 100})
    _write_json(root / "results" / "project1_delivery_integrity_report_latest.json", {"all_pass": True, "checked_file_count": 846})
    _write_json(root / "results" / "project1_delivery_zip_integrity_report_latest.json", {"all_pass": True, "checked_file_count": 846})
    _write_json(root / "results" / "project1_delivery_media_audit_latest.json", {"all_pass": True, "media_delivery_score": 100})
    _write_json(root / "results" / "project1_delivery_conformance_audit_latest.json", {"all_pass": True, "conformance_score": 100})
    _write_json(
        root / "results" / "project1_delivery_player_static_audit_latest.json",
        {
            "all_pass": True,
            "status": "pass",
            "package_dir": str(static_package.relative_to(root)),
            "score_count": 40,
            "manifest_rows": 240,
            "bad_text_files": [],
        },
    )
    _write_json(
        root / "results" / "project1_delivery_player_qa_latest.json",
        {
            "status": "pass" if real_browser_qa else "fallback_static_pass",
            "browser_status": "pass" if real_browser_qa else "not_run",
            "package_dir": str(chrome_package.relative_to(root)),
            "nav_items": 40,
            "audio_controls_initial": 6,
            "audio_controls_after_search": 6,
            "screenshot": "results/project1_delivery_player_qa_latest.png" if real_browser_qa else "",
        },
    )
    if real_browser_qa:
        (root / "results" / "project1_delivery_player_qa_latest.png").write_bytes(b"png")
    _write_json(
        root / "results" / "project1_recipient_usability_audit_latest.json",
        {"all_pass": True, "recipient_usability_score": 100, "status": "pass", "issues": []},
    )
    _write_json(root / "results" / "project1_playback_license_audit_latest.json", {"all_pass": True, "license_audit_score": 100})
    _write_json(root / "results" / "project1_pro_playback_traceability_audit_latest.json", {"all_pass": True, "score_audio_traceability_score": 100})
    _write_json(root / "results" / "project1_commercial_claims_audit_latest.json", {"all_pass": True, "violation_count": 0})
    _write_json(
        root / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json",
        {
            "schema": "project1_commercial_legal_review_packet_v1",
            "status": "manual review required",
            "packet_dir": "results/project1_commercial_legal_review_packet",
            "delivery_zip": "expert_eval/project1/deliverables/old_delivery.zip"
            if legal_packet_stale
            else str(zip_path.relative_to(root)),
            "delivery_zip_sha256": "old-sha" if legal_packet_stale else sha,
        },
    )
    _write_json(root / "results" / "project1_commercial_readiness_audit.json", {"commercial_readiness_score": 75.0, "all_pass": False})
    _write_json(
        root / "results" / "project1_commercial_acceptance_report_latest.json",
        {
            "engineering_acceptance": "pass",
            "commercial_release": "pending_external_evidence",
            "all_commercial_gates_pass": False,
        },
    )
    _write_json(
        root / "results" / "project1_commercial_release_gate_latest.json",
        {
            "commercial_release_ready": False,
            "release_score": 75,
            "blocking_items": ["returned_expert_evaluation", "commercial_legal_signoff"],
        },
    )


def test_release_candidate_separates_engineering_ready_from_commercial_blockers(tmp_path: Path) -> None:
    _write_candidate_fixture(tmp_path)

    report = build_release_candidate_report(tmp_path)

    assert report["engineering_release_candidate_ready"] is True
    assert report["customer_review_ready"] is False
    assert report["customer_review_blockers"] == ["real_browser_player_qa"]
    assert report["commercial_release_ready"] is False
    assert report["engineering_blockers"] == []
    assert report["commercial_blockers"] == ["returned_expert_evaluation", "commercial_legal_signoff"]
    assert report["deliverable"]["zip_regular_file_count"] == 1
    assert report["optional_checks"][0]["status"] == "fallback_static_pass"


def test_release_candidate_blocks_stale_static_player_package(tmp_path: Path) -> None:
    _write_candidate_fixture(tmp_path, static_package_stale=True)

    report = build_release_candidate_report(tmp_path)

    assert report["engineering_release_candidate_ready"] is False
    assert "static_player_audit" in report["engineering_blockers"]


def test_release_candidate_marks_stale_chrome_qa_as_optional_failure(tmp_path: Path) -> None:
    _write_candidate_fixture(tmp_path, chrome_package_stale=True)

    report = build_release_candidate_report(tmp_path)

    assert report["engineering_release_candidate_ready"] is True
    assert report["optional_checks"][0]["passed"] is False
    assert "stale" in report["optional_checks"][0]["status"]


def test_release_candidate_blocks_stale_legal_review_packet(tmp_path: Path) -> None:
    _write_candidate_fixture(tmp_path, legal_packet_stale=True)

    report = build_release_candidate_report(tmp_path)

    assert report["engineering_release_candidate_ready"] is False
    assert "commercial_legal_review_packet" in report["engineering_blockers"]


def test_release_candidate_marks_customer_review_ready_after_real_browser_qa(tmp_path: Path) -> None:
    _write_candidate_fixture(tmp_path, real_browser_qa=True)

    report = build_release_candidate_report(tmp_path)

    assert report["engineering_release_candidate_ready"] is True
    assert report["customer_review_ready"] is True
    assert report["customer_review_blockers"] == []
