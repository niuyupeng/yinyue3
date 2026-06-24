from __future__ import annotations

import hashlib
import csv
import json
from pathlib import Path

from chorale.commercial_acceptance_report import build_acceptance_report, write_report
from chorale.commercial_readiness_audit import run_readiness_audit, write_outputs
from chorale.commercial_release_gate import build_release_gate_report


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_metrics(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"model": "lstm_baseline", "task": "soprano_to_satb"},
        {"model": "transformer_no_constraints", "task": "soprano_to_satb"},
        {"model": "proposed_neural_symbolic_rule_guided", "task": "soprano_to_satb"},
        {"model": "proposed_neural_symbolic_masked_infilling", "task": "masked_infill"},
        {"model": "proposed_neural_symbolic_soprano_to_satb", "task": "soprano_to_satb"},
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["model", "task"])
        writer.writeheader()
        writer.writerows(rows)


def _write_ready_fixture(root: Path, *, expert: bool = True, legal: bool = True) -> None:
    _write_metrics(root / "results" / "project1_metrics.csv")
    _write_json(root / "results" / "project1_commercial_delivery_audit_latest.json", {"all_pass": True, "commercial_delivery_score": 100})
    _write_json(root / "results" / "project1_delivery_integrity_report_latest.json", {"all_pass": True, "checked_file_count": 10})
    _write_json(root / "results" / "project1_delivery_zip_integrity_report_latest.json", {"all_pass": True, "checked_file_count": 10})
    zip_file = root / "expert_eval" / "project1" / "deliverables" / "delivery.zip"
    zip_file.parent.mkdir(parents=True, exist_ok=True)
    zip_file.write_bytes(b"zip")
    delivery_dir = zip_file.with_suffix("")
    delivery_dir.mkdir()
    _write_json(
        root / "results" / "project1_delivery_release_manifest_latest.json",
        {
            "zip_file": str(zip_file.relative_to(root)),
            "zip_size_bytes": 3,
            "zip_sha256": "placeholder",
            "commercial_delivery_all_pass": True,
            "folder_integrity_all_pass": True,
            "zip_integrity_all_pass": True,
        },
    )
    _write_json(
        root / "results" / "project1_pro_playback_traceability_audit_latest.json",
        {"all_pass": True, "score_audio_traceability_score": 100},
    )
    _write_json(root / "results" / "project1_delivery_conformance_audit_latest.json", {"all_pass": True, "conformance_score": 100})
    _write_json(root / "results" / "project1_playback_license_audit_latest.json", {"all_pass": True, "license_audit_score": 100})
    _write_json(
        root / "results" / "project1_delivery_player_qa_latest.json",
        {
            "status": "pass",
            "package_dir": str(delivery_dir.relative_to(root)),
            "nav_items": 40,
            "audio_controls_initial": 6,
            "audio_controls_after_search": 6,
        },
    )
    _write_json(
        root / "results" / "project1_delivery_player_static_audit_latest.json",
        {
            "all_pass": True,
            "status": "pass",
            "package_dir": str(delivery_dir.relative_to(root)),
            "score_count": 40,
            "manifest_rows": 240,
            "bad_text_files": [],
        },
    )
    _write_json(
        root / "results" / "project1_recipient_usability_audit_latest.json",
        {"all_pass": True, "recipient_usability_score": 100, "status": "pass", "issues": []},
    )
    _write_json(
        root / "results" / "project1_expert_eval_summary.json",
        {
            "status": "completed" if expert else "expert evaluation pending",
            "rating_file_count": 3 if expert else 0,
            "absolute_completed_rows": 30 if expert else 0,
            "paired_completed_rows": 30 if expert else 0,
        },
    )
    _write_json(
        root / "results" / "project1_expert_return_intake_report_latest.json",
        {
            "status": "ready_to_summarize" if expert else "expert evaluation pending",
            "rating_file_count": 3 if expert else 0,
            "valid_rating_file_count": 3 if expert else 0,
            "absolute_completed_rows": 30 if expert else 0,
            "paired_completed_rows": 30 if expert else 0,
        },
    )
    _write_json(
        root / "results" / "project1_review_issue_intake_latest.json",
        {
            "schema": "project1_review_issue_intake_v1",
            "status": "no_issue_files",
            "package_dir": str(delivery_dir.relative_to(root)),
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
            "delivery_zip": str(zip_file.relative_to(root)),
            "delivery_zip_sha256": "placeholder",
        },
    )
    if legal:
        _write_json(root / "results" / "project1_commercial_legal_signoff.json", {"approved_for_commercial_distribution": True})
    paper = root / "paper"
    paper.mkdir()
    (paper / "main.pdf").write_bytes(b"%PDF")
    (paper / "main.log").write_text("Output written on main.pdf", encoding="utf-8")
    (root / "scripts").mkdir()
    (root / "scripts" / "summarize_project1_expert_ratings.ps1").write_text("", encoding="utf-8")
    (root / "scripts" / "intake_project1_review_issues.ps1").write_text("", encoding="utf-8")
    (root / "scripts" / "build_project1_issue_evidence_packet.ps1").write_text("", encoding="utf-8")
    (root / "src" / "chorale").mkdir(parents=True)
    (root / "src" / "chorale" / "expert_eval_tools.py").write_text("", encoding="utf-8")
    (root / "src" / "chorale" / "review_issue_intake.py").write_text("", encoding="utf-8")
    (root / "src" / "chorale" / "delivery_issue_packet.py").write_text("", encoding="utf-8")
    (root / "src" / "chorale" / "delivery_issue_debugger.py").write_text("", encoding="utf-8")
    (root / "paper" / "tables").mkdir()
    (root / "paper" / "tables" / "project1_expert_eval_results.tex").write_text("", encoding="utf-8")


def _fix_release_sha(root: Path) -> None:
    path = root / "results" / "project1_delivery_release_manifest_latest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    zip_path = root / data["zip_file"]
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    data["zip_sha256"] = sha
    path.write_text(json.dumps(data), encoding="utf-8")
    legal_packet_path = root / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json"
    if legal_packet_path.is_file():
        packet = json.loads(legal_packet_path.read_text(encoding="utf-8"))
        packet["delivery_zip_sha256"] = sha
        legal_packet_path.write_text(json.dumps(packet), encoding="utf-8")


def _write_complete_legal_signoff(root: Path) -> None:
    release = json.loads((root / "results" / "project1_delivery_release_manifest_latest.json").read_text(encoding="utf-8"))
    data = {
        "approved_for_commercial_distribution": True,
        "delivery_zip": release["zip_file"],
        "delivery_zip_sha256": release["zip_sha256"],
        "review_date": "2026-06-20",
        "reviewer_name": "Independent reviewer",
        "reviewer_role": "Commercial/legal reviewer",
        "required_checks": {
            "dataset_and_generated_score_rights_reviewed": True,
            "soundfont_and_playback_tool_licenses_reviewed": True,
            "redistribution_scope_approved": True,
            "privacy_or_human_subjects_requirements_reviewed": True,
            "commercial_claims_reviewed": True,
        },
    }
    path = root / "results" / "project1_commercial_legal_signoff.json"
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_readiness_and_acceptance(root: Path) -> None:
    readiness = run_readiness_audit(root)
    write_outputs(readiness, root / "results" / "project1_commercial_readiness_audit.json")
    report = build_acceptance_report(root)
    write_report(report, root / "results" / "project1_commercial_acceptance_report_latest.json")


def test_release_gate_blocks_without_external_evidence(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=False, legal=False)
    _fix_release_sha(tmp_path)
    _write_readiness_and_acceptance(tmp_path)

    report = build_release_gate_report(tmp_path)

    assert report["commercial_release_ready"] is False
    assert report["release_status"] == "blocked"
    assert "returned_expert_evaluation" in report["blocking_items"]
    assert "commercial_legal_signoff" in report["blocking_items"]


def test_release_gate_passes_only_with_expert_legal_and_matching_zip(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=True)
    _fix_release_sha(tmp_path)
    _write_complete_legal_signoff(tmp_path)
    _write_readiness_and_acceptance(tmp_path)

    report = build_release_gate_report(tmp_path)

    assert report["commercial_release_ready"] is True
    assert report["release_score"] == 100
    assert report["blocking_items"] == []
