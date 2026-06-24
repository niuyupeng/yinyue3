from __future__ import annotations

import csv
import json
from pathlib import Path

from chorale.commercial_readiness_audit import run_readiness_audit


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


def _complete_legal_signoff() -> dict[str, object]:
    return {
        "approved_for_commercial_distribution": True,
        "delivery_zip": "expert_eval/project1/deliverables/delivery.zip",
        "delivery_zip_sha256": "abc",
        "reviewer_name": "Commercial Reviewer",
        "reviewer_role": "legal/commercial reviewer",
        "review_date": "2026-06-20",
        "required_checks": {
            "bach_dataset_public_domain_or_license_checked": True,
            "musicxml_examples_can_be_redistributed": True,
            "soundfont_license_checked": True,
            "ffmpeg_and_fluidsynth_redistribution_checked": True,
            "expert_materials_anonymized": True,
            "no_unlicensed_third_party_scores_in_package": True,
        },
    }


def _write_expert_summary(root: Path, *, expert: bool = True, intake: bool = True) -> None:
    _write_json(
        root / "results" / "project1_expert_eval_summary.json",
        {
            "status": "completed" if expert else "expert evaluation pending",
            "rating_file_count": 3 if expert else 0,
            "absolute_completed_rows": 30 if expert else 0,
            "paired_completed_rows": 30 if expert else 0,
        },
    )
    if intake:
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


def _write_ready_fixture(
    root: Path,
    *,
    expert: bool = True,
    intake: bool = True,
    legal: bool = True,
) -> None:
    _write_metrics(root / "results" / "project1_metrics.csv")
    _write_json(root / "results" / "project1_commercial_delivery_audit_latest.json", {"all_pass": True, "commercial_delivery_score": 100})
    _write_json(
        root / "results" / "project1_delivery_integrity_report_latest.json",
        {"all_pass": True, "checked_file_count": 10},
    )
    _write_json(
        root / "results" / "project1_delivery_zip_integrity_report_latest.json",
        {"all_pass": True, "checked_file_count": 10},
    )
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
            "zip_sha256": "abc",
            "commercial_delivery_all_pass": True,
            "folder_integrity_all_pass": True,
            "zip_integrity_all_pass": True,
        },
    )
    _write_json(
        root / "results" / "project1_pro_playback_traceability_audit_latest.json",
        {"all_pass": True, "score_audio_traceability_score": 100},
    )
    _write_json(
        root / "results" / "project1_delivery_conformance_audit_latest.json",
        {"all_pass": True, "conformance_score": 100},
    )
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
    _write_expert_summary(root, expert=expert, intake=intake)
    if legal:
        _write_json(root / "results" / "project1_commercial_legal_signoff.json", _complete_legal_signoff())
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
    _write_json(
        root / "results" / "project1_review_issue_intake_latest.json",
        {
            "schema": "project1_review_issue_intake_v1",
            "status": "no_issue_files",
            "package_dir": str(delivery_dir.relative_to(root)),
            "invalid_issue_count": 0,
            "unmatched_issue_count": 0,
        },
    )
    _write_json(
        root / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json",
        {
            "schema": "project1_commercial_legal_review_packet_v1",
            "status": "manual review required",
            "packet_dir": "results/project1_commercial_legal_review_packet",
            "delivery_zip": str(zip_file.relative_to(root)),
            "delivery_zip_sha256": "abc",
        },
    )


def test_commercial_readiness_audit_blocks_without_expert_and_legal_signoff(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=False, legal=False)

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert summary["status"] == "not yet commercial release ready"
    assert "returned_expert_evaluation" in summary["blocking_items"]
    assert "commercial_legal_signoff" in summary["blocking_items"]


def test_commercial_readiness_audit_passes_when_all_gates_have_evidence(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=True)

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is True
    assert summary["commercial_readiness_score"] == 100
    assert summary["blocking_items"] == []


def test_commercial_readiness_blocks_missing_expert_intake_report(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, intake=False, legal=True)

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert "returned_expert_evaluation" in summary["blocking_items"]


def test_commercial_readiness_blocks_minimal_legal_signoff(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=False)
    _write_json(
        tmp_path / "results" / "project1_commercial_legal_signoff.json",
        {"approved_for_commercial_distribution": True},
    )

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert "commercial_legal_signoff" in summary["blocking_items"]


def test_commercial_readiness_blocks_invalid_review_issue_intake(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=True)
    _write_json(
        tmp_path / "results" / "project1_review_issue_intake_latest.json",
        {
            "schema": "project1_review_issue_intake_v1",
            "status": "has_invalid_rows",
            "package_dir": "expert_eval/project1/deliverables/delivery",
            "invalid_issue_count": 1,
            "unmatched_issue_count": 0,
        },
    )

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert "review_issue_intake_workflow" in summary["blocking_items"]


def test_commercial_readiness_blocks_stale_player_qa_package(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=True)
    _write_json(
        tmp_path / "results" / "project1_delivery_player_qa_latest.json",
        {
            "status": "fallback_static_pass",
            "package_dir": "expert_eval/project1/deliverables/old_delivery",
            "nav_items": 40,
            "audio_controls_initial": 6,
            "audio_controls_after_search": 6,
        },
    )

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert "offline_player_browser_qa" in summary["blocking_items"]


def test_commercial_readiness_blocks_stale_review_issue_intake_package(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=True)
    _write_json(
        tmp_path / "results" / "project1_review_issue_intake_latest.json",
        {
            "schema": "project1_review_issue_intake_v1",
            "status": "no_issue_files",
            "package_dir": "expert_eval/project1/deliverables/old_delivery",
            "invalid_issue_count": 0,
            "unmatched_issue_count": 0,
        },
    )

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert "review_issue_intake_workflow" in summary["blocking_items"]


def test_commercial_readiness_blocks_stale_legal_review_packet(tmp_path: Path) -> None:
    _write_ready_fixture(tmp_path, expert=True, legal=True)
    _write_json(
        tmp_path / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json",
        {
            "schema": "project1_commercial_legal_review_packet_v1",
            "status": "manual review required",
            "packet_dir": "results/project1_commercial_legal_review_packet",
            "delivery_zip": "expert_eval/project1/deliverables/old_delivery.zip",
            "delivery_zip_sha256": "old-sha",
        },
    )

    summary = run_readiness_audit(tmp_path)

    assert summary["all_pass"] is False
    assert "commercial_legal_review_packet_current" in summary["blocking_items"]
