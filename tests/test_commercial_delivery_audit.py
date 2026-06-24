from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from chorale.commercial_delivery_audit import REQUIRED_VARIANTS, audit_package


def _write_minimal_delivery(root: Path, *, missing_mp3: bool = False) -> None:
    (root / "audio_pro").mkdir(parents=True)
    for path in [
        "score_audio_player.html",
        "COMMERCIAL_PLAYBACK_README_CN.md",
        "DELIVERY_README_CN.md",
        "DELIVERY_FILE_MANIFEST.json",
        "DELIVERY_FILE_MANIFEST.sha256",
        "DELIVERY_MEDIA_AUDIT.csv",
        "DELIVERY_MEDIA_AUDIT.json",
        "DELIVERY_MEDIA_AUDIT.md",
        "DELIVERY_CONFORMANCE_AUDIT.csv",
        "DELIVERY_CONFORMANCE_AUDIT.json",
        "DELIVERY_CONFORMANCE_AUDIT.md",
        "VERIFY_DELIVERY_INTEGRITY.ps1",
        "VERIFY_DELIVERY_INTEGRITY_README_CN.md",
        "THIRD_PARTY_PLAYBACK_NOTICES.md",
        "README_FOR_EXPERTS.md",
        "SCORING_RUBRIC.md",
        "START_HERE_CN.html",
        "START_HERE_CN.md",
        "OPEN_PROJECT1_REVIEW_PACKAGE.ps1",
        "PROJECT1_PACKAGE_SELF_TEST.ps1",
        "PROJECT1_PACKAGE_SELF_TEST_README_CN.md",
        "REVIEW_ISSUE_REPORT_TEMPLATE.csv",
        "REVIEW_ISSUE_REPORT_GUIDE_CN.md",
        "audio_pro/COMMERCIAL_QC_REPORT.md",
        "third_party/MuseScore_General_License.md",
        "third_party/MuseScore_General_Readme.md",
        "forms/project1_expert_rating_forms_CN.xlsx",
    ]:
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text("QC score: 100/100 Full choir Piano reference Soprano stem", encoding="utf-8")
    (root / "audio_pro" / "commercial_qc_summary.json").write_text(
        json.dumps({"qc_score": 100, "entry_count": 240, "pass_count": 240, "fail_count": 0, "all_pass": True}),
        encoding="utf-8",
    )
    (root / "audio_pro" / "pro_playback_summary.json").write_text(
        json.dumps({"entry_count": 240, "ok_count": 240, "failed_count": 0, "all_ok": True}),
        encoding="utf-8",
    )
    rows = []
    for score_idx in range(40):
        score_id = f"P1S{score_idx + 1:02d}"
        for variant in sorted(REQUIRED_VARIANTS):
            base = f"audio_pro/absolute/{score_id}/{score_id}_{variant}"
            midi = f"midi_pro/absolute/{score_id}/{score_id}_{variant}.mid"
            source = f"absolute_score_musicxml/{score_id}.musicxml"
            render = f"render_xml/absolute/{score_id}/{score_id}_{variant}.musicxml"
            for rel in [midi, source, render]:
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_bytes(b"x")
            mp3 = f"{base}.mp3"
            if not missing_mp3:
                (root / mp3).parent.mkdir(parents=True, exist_ok=True)
                (root / mp3).write_bytes(b"ID3")
            rows.append(
                {
                    "group": "absolute",
                    "score_id": score_id,
                    "variant": variant,
                    "source_musicxml": source,
                    "render_musicxml": render,
                    "midi": midi,
                    "wav": "",
                    "mp3": mp3,
                    "status": "ok",
                }
            )
    with (root / "audio_pro" / "commercial_qc_report.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["group", "score_id", "variant", "status"])
        writer.writeheader()
        writer.writerows({key: row[key] for key in ["group", "score_id", "variant", "status"]} for row in rows)
    with (root / "audio_pro" / "pro_playback_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["group", "score_id", "variant", "source_musicxml", "render_musicxml", "midi", "wav", "mp3", "status"],
        )
        writer.writeheader()
        writer.writerows(rows)


def test_commercial_delivery_audit_passes_mp3_only_folder(tmp_path: Path) -> None:
    _write_minimal_delivery(tmp_path)

    summary = audit_package(package_dir=tmp_path, mode="mp3_only")

    assert summary["commercial_delivery_score"] == 100
    assert summary["all_pass"] is True
    assert summary["mp3_count"] == 240
    assert summary["wav_count"] == 0


def test_commercial_delivery_audit_detects_missing_reference(tmp_path: Path) -> None:
    _write_minimal_delivery(tmp_path, missing_mp3=True)

    summary = audit_package(package_dir=tmp_path, mode="mp3_only")

    assert summary["all_pass"] is False
    assert any("missing manifest references" in issue for issue in summary["issues"])


def test_commercial_delivery_audit_reads_zip_without_extraction(tmp_path: Path) -> None:
    package = tmp_path / "package"
    _write_minimal_delivery(package)
    zip_path = tmp_path / "package.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for item in package.rglob("*"):
            if item.is_file():
                archive.write(item, item.relative_to(package).as_posix())

    summary = audit_package(zip_file=zip_path, mode="mp3_only")

    assert summary["all_pass"] is True
    assert summary["manifest_rows"] == 240
