from __future__ import annotations

import json
from pathlib import Path

from chorale.release_checklist import write_release_checklist


def _write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_release_checklist_uses_current_manifest_and_gate_evidence(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "results" / "project1_delivery_release_manifest_latest.json",
        {
            "commercial_delivery_score": 100,
            "zip_file": "expert_eval/project1/deliverables/current.zip",
            "zip_sha256": "abc123",
            "zip_regular_file_count": 856,
            "zip_integrity_checked_file_count": 852,
            "mp3_count": 240,
            "midi_count": 240,
            "wav_count": 0,
            "score_count": 40,
            "manifest_rows": 240,
        },
    )
    _write_json(
        tmp_path / "results" / "project1_commercial_readiness_audit.json",
        {
            "commercial_readiness_score": 75.0,
            "gates": [
                {
                    "gate": "commercial_delivery_package",
                    "weight": 15,
                    "passed": True,
                    "status": "pass",
                    "evidence": "results/project1_commercial_delivery_audit_latest.json",
                    "blocking": False,
                },
                {
                    "gate": "returned_expert_evaluation",
                    "weight": 15,
                    "passed": False,
                    "status": "expert evaluation pending",
                    "evidence": "results/project1_expert_eval_summary.json",
                    "blocking": True,
                },
            ],
        },
    )
    _write_json(
        tmp_path / "results" / "project1_commercial_release_gate_latest.json",
        {
            "release_status": "blocked",
            "commercial_release_ready": False,
            "blocking_items": ["returned_expert_evaluation"],
        },
    )
    _write_json(
        tmp_path / "results" / "project1_commercial_acceptance_report_latest.json",
        {"engineering_acceptance": "pass", "commercial_release": "pending_external_evidence"},
    )

    outputs = write_release_checklist(tmp_path, tmp_path / "docs" / "project1_100_point_release_checklist.md")
    text = Path(outputs["markdown"]).read_text(encoding="utf-8")
    summary = json.loads(Path(outputs["json"]).read_text(encoding="utf-8"))

    assert "current.zip" in text
    assert "abc123" in text
    assert "`75.0/100`" in text
    assert "`returned_expert_evaluation`" in text
    assert summary["zip_file"] == "expert_eval/project1/deliverables/current.zip"
    assert summary["blocking_items"] == ["returned_expert_evaluation"]
