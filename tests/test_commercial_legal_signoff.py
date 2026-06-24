from __future__ import annotations

import json
from pathlib import Path

from chorale.commercial_legal_signoff import build_prefilled_draft, validate_signoff


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _write_release(root: Path) -> None:
    _write_json(
        root / "results" / "project1_delivery_release_manifest_latest.json",
        {
            "zip_file": "expert_eval/project1/deliverables/current.zip",
            "zip_sha256": "abc123",
        },
    )


def _write_template(root: Path) -> None:
    _write_json(
        root / "docs" / "commercial_legal_signoff_template.json",
        {
            "approved_for_commercial_distribution": False,
            "review_date": "YYYY-MM-DD",
            "reviewer_name": "TODO",
            "reviewer_role": "TODO",
            "required_checks": {"rights_reviewed": False},
        },
    )


def test_prefilled_legal_signoff_draft_binds_current_release_but_remains_unapproved(tmp_path: Path) -> None:
    _write_release(tmp_path)
    _write_template(tmp_path)

    draft = build_prefilled_draft(tmp_path)

    assert draft["delivery_zip"] == "expert_eval/project1/deliverables/current.zip"
    assert draft["delivery_zip_sha256"] == "abc123"
    assert draft["approved_for_commercial_distribution"] is False
    assert draft["draft_status"] == "manual_review_required_not_approved"


def test_validate_signoff_blocks_missing_or_unapproved_file(tmp_path: Path) -> None:
    _write_release(tmp_path)

    missing = validate_signoff(tmp_path)

    assert missing["ready_for_commercial_release_gate"] is False
    assert "missing" in str(missing["problems"][0])

    _write_json(
        tmp_path / "results" / "project1_commercial_legal_signoff.json",
        {
            "approved_for_commercial_distribution": False,
            "delivery_zip": "expert_eval/project1/deliverables/current.zip",
            "delivery_zip_sha256": "abc123",
            "reviewer_name": "Reviewer",
            "reviewer_role": "Legal",
            "review_date": "2026-06-24",
            "required_checks": {"rights_reviewed": True},
        },
    )

    unapproved = validate_signoff(tmp_path)

    assert unapproved["ready_for_commercial_release_gate"] is False
    assert any("approved_for_commercial_distribution" in item for item in unapproved["problems"])


def test_validate_signoff_passes_complete_release_bound_signoff(tmp_path: Path) -> None:
    _write_release(tmp_path)
    _write_json(
        tmp_path / "results" / "project1_commercial_legal_signoff.json",
        {
            "approved_for_commercial_distribution": True,
            "delivery_zip": "expert_eval/project1/deliverables/current.zip",
            "delivery_zip_sha256": "abc123",
            "reviewer_name": "Reviewer",
            "reviewer_role": "Legal",
            "review_date": "2026-06-24",
            "required_checks": {"rights_reviewed": True},
        },
    )

    report = validate_signoff(tmp_path)

    assert report["ready_for_commercial_release_gate"] is True
    assert report["status"] == "pass"
    assert report["problems"] == []
