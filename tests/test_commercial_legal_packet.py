from __future__ import annotations

import json
from pathlib import Path

from chorale.commercial_legal_packet import build_legal_packet


def test_build_legal_packet_writes_review_files(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "requirements.txt").write_text("definitely_missing_project1_package_zzz>=1\n", encoding="utf-8")
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "commercial_legal_signoff_template.json").write_text("{}", encoding="utf-8")
    (tmp_path / "results").mkdir()
    (tmp_path / "results" / "project1_delivery_release_manifest_latest.json").write_text(
        json.dumps({"zip_file": "delivery.zip", "zip_sha256": "abc123"}),
        encoding="utf-8",
    )
    for name in [
        "project1_commercial_acceptance_report_latest.md",
        "project1_playback_license_audit_latest.json",
        "project1_commercial_delivery_audit_latest.json",
        "project1_delivery_conformance_audit_latest.json",
        "project1_pro_playback_traceability_audit_latest.json",
        "project1_review_issue_intake_latest.json",
    ]:
        (tmp_path / "results" / name).write_text("{}", encoding="utf-8")

    summary = build_legal_packet(tmp_path / "packet", delivery_zip="delivery.zip")

    assert summary["status"] == "manual review required"
    packet = Path(summary["packet_dir"])
    assert (packet / "LEGAL_COMMERCIAL_REVIEW_CHECKLIST.md").is_file()
    assert (packet / "COMMERCIAL_CLAIMS_BOUNDARY.md").is_file()
    assert (packet / "dependency_license_inventory.json").is_file()
    assert (packet / "review_issue_intake.json").is_file()
    assert (packet / "commercial_legal_signoff_PREFILLED_DRAFT.json").is_file()
    draft = json.loads((packet / "commercial_legal_signoff_PREFILLED_DRAFT.json").read_text(encoding="utf-8"))
    assert draft["delivery_zip"] == "delivery.zip"
    assert draft["delivery_zip_sha256"] == "abc123"
    assert draft["approved_for_commercial_distribution"] is False
    payload = json.loads((packet / "LEGAL_PACKET_SUMMARY.json").read_text(encoding="utf-8"))
    assert payload["note"].startswith("This packet organizes")
