from __future__ import annotations

import json
import shutil
import subprocess
import csv
from pathlib import Path

import pytest

from chorale.delivery_integrity import write_manifest
from chorale.delivery_recipient_tools import (
    ISSUE_REPORT_GUIDE_CN,
    ISSUE_REPORT_TEMPLATE_CSV,
    OPEN_PACKAGE_PS1,
    PACKAGE_SELF_TEST_PS1,
    VERIFIER_PS1,
    write_recipient_verifier,
)


def test_write_recipient_verifier_files(tmp_path: Path) -> None:
    outputs = write_recipient_verifier(tmp_path)

    assert (tmp_path / VERIFIER_PS1).is_file()
    assert (tmp_path / OPEN_PACKAGE_PS1).is_file()
    assert (tmp_path / PACKAGE_SELF_TEST_PS1).is_file()
    assert (tmp_path / ISSUE_REPORT_TEMPLATE_CSV).is_file()
    assert (tmp_path / ISSUE_REPORT_GUIDE_CN).is_file()
    assert (tmp_path / "VERIFY_DELIVERY_INTEGRITY_README_CN.md").is_file()
    assert (tmp_path / "PROJECT1_PACKAGE_SELF_TEST_README_CN.md").is_file()
    assert "VERIFY_DELIVERY_INTEGRITY.ps1" in outputs["verifier_ps1"]
    assert "OPEN_PROJECT1_REVIEW_PACKAGE.ps1" in outputs["open_package_ps1"]
    assert "PROJECT1_PACKAGE_SELF_TEST.ps1" in outputs["package_self_test_ps1"]
    assert "REVIEW_ISSUE_REPORT_TEMPLATE.csv" in outputs["issue_report_template_csv"]
    assert "谱例编号" in (tmp_path / ISSUE_REPORT_TEMPLATE_CSV).read_text(encoding="utf-8-sig")
    assert "MusicXML -> MIDI -> MP3" in (tmp_path / ISSUE_REPORT_GUIDE_CN).read_text(encoding="utf-8")


def test_recipient_verifier_powershell_roundtrip(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    (tmp_path / "score.musicxml").write_text("<score-partwise version='3.1'/>", encoding="utf-8")
    write_recipient_verifier(tmp_path)
    write_manifest(tmp_path)
    out_json = tmp_path / "recipient_report.json"

    result = subprocess.run(
        [
            powershell,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / VERIFIER_PS1),
            "-PackageDir",
            str(tmp_path),
            "-OutJson",
            str(out_json),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads(out_json.read_text(encoding="utf-8-sig"))
    assert report["all_pass"] is True
    assert report["checked_file_count"] == 8


def test_open_package_script_runs_integrity_without_opening_browser(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    (tmp_path / "START_HERE_CN.html").write_text("<html><body>start</body></html>", encoding="utf-8")
    (tmp_path / "score_audio_player.html").write_text("<html><body>player</body></html>", encoding="utf-8")
    write_recipient_verifier(tmp_path)
    (tmp_path / PACKAGE_SELF_TEST_PS1).unlink()
    write_manifest(tmp_path)

    result = subprocess.run(
        [
            powershell,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / OPEN_PACKAGE_PS1),
            "-PackageDir",
            str(tmp_path),
            "-NoOpen",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "OPEN_PACKAGE_REPORT.json").read_text(encoding="utf-8-sig"))
    assert report["status"] == "pass"
    assert report["integrity_status"] == "pass"
    assert report["opened"] is False


def test_package_self_test_passes_minimal_complete_delivery(tmp_path: Path) -> None:
    powershell = shutil.which("powershell") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not available")

    make_minimal_complete_delivery(tmp_path)
    write_recipient_verifier(tmp_path)
    write_manifest(tmp_path)

    result = subprocess.run(
        [
            powershell,
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(tmp_path / PACKAGE_SELF_TEST_PS1),
            "-PackageDir",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    report = json.loads((tmp_path / "PACKAGE_SELF_TEST_REPORT.json").read_text(encoding="utf-8-sig"))
    assert report["all_pass"] is True
    assert report["manifest_rows"] == 240
    assert report["mp3_count"] == 240
    assert report["midi_count"] == 240


def make_minimal_complete_delivery(root: Path) -> None:
    for rel in [
        "START_HERE_CN.html",
        "score_audio_player.html",
        "DELIVERY_README_CN.md",
        "COMMERCIAL_PLAYBACK_README_CN.md",
        "README_FOR_EXPERTS.md",
        "SCORING_RUBRIC.md",
        "REVIEW_ISSUE_REPORT_TEMPLATE.csv",
        "REVIEW_ISSUE_REPORT_GUIDE_CN.md",
        "forms/project1_expert_rating_forms_CN.xlsx",
        "audio_pro/commercial_qc_summary.json",
    ]:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".xlsx":
            path.write_bytes(b"xlsx")
        elif path.suffix == ".json":
            path.write_text("{}", encoding="utf-8")
        else:
            path.write_text("Project1 SATB review package", encoding="utf-8")

    variants = ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]
    rows: list[dict[str, str]] = []
    for score_idx in range(40):
        score_id = f"P1S{score_idx + 1:02d}"
        source = root / "absolute_score_musicxml" / f"{score_id}.musicxml"
        pdf = root / "absolute_score_pdfs" / f"{score_id}.pdf"
        source.parent.mkdir(parents=True, exist_ok=True)
        pdf.parent.mkdir(parents=True, exist_ok=True)
        source.write_text("<score-partwise/>", encoding="utf-8")
        pdf.write_bytes(b"%PDF")
        for variant in variants:
            render = root / "render_xml" / "absolute" / score_id / f"{score_id}_{variant}.musicxml"
            midi = root / "midi_pro" / "absolute" / score_id / f"{score_id}_{variant}.mid"
            mp3 = root / "audio_pro" / "absolute" / score_id / f"{score_id}_{variant}.mp3"
            render.parent.mkdir(parents=True, exist_ok=True)
            midi.parent.mkdir(parents=True, exist_ok=True)
            mp3.parent.mkdir(parents=True, exist_ok=True)
            render.write_text("<score-partwise/>", encoding="utf-8")
            midi.write_bytes(b"MThd")
            mp3.write_bytes(b"ID3")
            rows.append(
                {
                    "group": "absolute",
                    "score_id": score_id,
                    "variant": variant,
                    "source_musicxml": f"absolute_score_musicxml/{score_id}.musicxml",
                    "render_musicxml": f"render_xml/absolute/{score_id}/{score_id}_{variant}.musicxml",
                    "midi": f"midi_pro/absolute/{score_id}/{score_id}_{variant}.mid",
                    "mp3": f"audio_pro/absolute/{score_id}/{score_id}_{variant}.mp3",
                }
            )
    with (root / "audio_pro" / "pro_playback_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["group", "score_id", "variant", "source_musicxml", "render_musicxml", "midi", "mp3"],
        )
        writer.writeheader()
        writer.writerows(rows)
