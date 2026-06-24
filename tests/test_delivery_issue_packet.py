from __future__ import annotations

import json
import zipfile
from pathlib import Path

from chorale.delivery_issue_packet import build_issue_evidence_packet
from tests.test_delivery_issue_debugger import make_package, write_simple_satb_score


def test_build_issue_evidence_packet_copies_debug_files_and_media(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")
    write_simple_satb_score(package / "absolute_score_musicxml" / "P1S01.musicxml")
    write_simple_satb_score(package / "render_xml" / "absolute" / "P1S01" / "P1S01_stem_alto.musicxml")
    pdf = package / "absolute_score_pdfs" / "P1S01.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    pdf.write_bytes(b"%PDF")

    summary = build_issue_evidence_packet(
        "P1S01",
        "stem_alto",
        package_dir=package,
        time_sec=4.0,
        out_dir=tmp_path / "issue_packets",
        packet_name="case_001",
    )

    packet_dir = Path(summary["packet_dir"])
    assert summary["debug_status"] == "pass"
    assert summary["copied_file_count"] == 5
    assert (packet_dir / "debug_report.json").is_file()
    assert (packet_dir / "debug_report.md").is_file()
    assert (packet_dir / "manifest_row.csv").is_file()
    assert (packet_dir / "media_audit_row.csv").is_file()
    assert (packet_dir / "conformance_audit_row.csv").is_file()
    assert (packet_dir / "README.md").is_file()

    debug = json.loads((packet_dir / "debug_report.json").read_text(encoding="utf-8"))
    assert debug["timepoint_diagnostic"]["estimated_measure"] == 1
    labels = {item["label"] for item in summary["copied_files"] if item["copied"]}
    assert labels == {"source_musicxml", "render_musicxml", "midi", "mp3", "score_pdf"}

    zip_path = Path(summary["zip_file"])
    assert zip_path.is_file()
    with zipfile.ZipFile(zip_path) as archive:
        names = set(archive.namelist())
    assert "case_001/debug_report.json" in names
    assert any(name.endswith("score_pdf__P1S01.pdf") for name in names)


def test_build_issue_evidence_packet_handles_unknown_item(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")

    summary = build_issue_evidence_packet(
        "P1S99",
        "stem_alto",
        package_dir=package,
        out_dir=tmp_path / "issue_packets",
        packet_name="missing_case",
    )

    packet_dir = Path(summary["packet_dir"])
    debug = json.loads((packet_dir / "debug_report.json").read_text(encoding="utf-8"))
    assert summary["debug_status"] == "not_found"
    assert debug["status"] == "not_found"
    assert Path(summary["zip_file"]).is_file()
