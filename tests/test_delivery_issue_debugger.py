from __future__ import annotations

import csv
from pathlib import Path

from music21 import meter, note, stream

from chorale.delivery_issue_debugger import debug_delivery_item


def test_delivery_issue_debugger_reports_pass_for_clean_item(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")

    report = debug_delivery_item(package, "P1S01", "stem_alto")

    assert report["status"] == "pass"
    assert report["path_status"]["mp3"]["exists"] is True
    assert report["conformance_audit"]["status"] == "pass"


def test_delivery_issue_debugger_surfaces_conformance_issue(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="fail", media_status="pass")

    report = debug_delivery_item(package, "P1S01", "stem_alto")

    assert report["status"] == "needs_attention"
    assert any("conformance audit" in issue for issue in report["issues"])


def test_delivery_issue_debugger_maps_audio_time_to_score_context(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")
    write_simple_satb_score(package / "absolute_score_musicxml" / "P1S01.musicxml")
    write_simple_satb_score(package / "render_xml" / "absolute" / "P1S01" / "P1S01_stem_alto.musicxml")

    report = debug_delivery_item(package, "P1S01", "stem_alto", time_sec=4.0, window_quarter=0.1)

    diagnostic = report["timepoint_diagnostic"]
    assert diagnostic["audio_duration_sec"] == 8.0
    assert diagnostic["render_duration_quarter_length"] == 4.0
    assert diagnostic["estimated_quarter_offset"] == 2.0
    assert diagnostic["estimated_measure"] == 1
    assert diagnostic["estimated_beat"] == 3.0
    assert diagnostic["measure_relative_offset_quarter"] == 2.0
    assert diagnostic["measure_duration_quarter"] == 4.0
    assert diagnostic["time_signature"] == "4/4"
    nearby = diagnostic["render_notes_near_time"]
    assert any("F4" in row["pitches"] for row in nearby)


def make_package(tmp_path: Path, *, conformance_status: str, media_status: str) -> Path:
    package = tmp_path / "package"
    score_id = "P1S01"
    variant = "stem_alto"
    row = {
        "group": "absolute",
        "score_id": score_id,
        "variant": variant,
        "voice": "alto",
        "description": "Alto stem.",
        "source_musicxml": "absolute_score_musicxml/P1S01.musicxml",
        "render_musicxml": "render_xml/absolute/P1S01/P1S01_stem_alto.musicxml",
        "midi": "midi_pro/absolute/P1S01/P1S01_stem_alto.mid",
        "wav": "",
        "mp3": "audio_pro/absolute/P1S01/P1S01_stem_alto.mp3",
        "midi_backend": "musescore",
        "audio_backend": "fluidsynth",
        "status": "ok",
        "duration_sec": "8.0",
        "rms": "0.1",
        "peak": "0.5",
        "message": "",
    }
    for rel in [row["source_musicxml"], row["render_musicxml"], row["midi"], row["mp3"]]:
        path = package / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    write_csv(package / "audio_pro" / "pro_playback_manifest.csv", [row])
    write_csv(
        package / "DELIVERY_MEDIA_AUDIT.csv",
        [{**row, "status": media_status, "issues": "" if media_status == "pass" else "media failed"}],
    )
    write_csv(
        package / "DELIVERY_CONFORMANCE_AUDIT.csv",
        [
            {
                **row,
                "status": conformance_status,
                "issues": "" if conformance_status == "pass" else "wrong stem",
                "render_duration_quarter_length": "4.0",
                "source_duration_quarter_length": "4.0",
            }
        ],
    )
    return package


def write_simple_satb_score(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    score = stream.Score(id="P1S01")
    parts = [
        ("Soprano", ["C5", "D5", "E5", "F5"]),
        ("Alto", ["C4", "E4", "F4", "G4"]),
        ("Tenor", ["G3", "A3", "B3", "C4"]),
        ("Bass", ["C3", "D3", "E3", "F3"]),
    ]
    for part_name, pitches in parts:
        part = stream.Part(id=part_name)
        part.partName = part_name
        measure = stream.Measure(number=1)
        measure.append(meter.TimeSignature("4/4"))
        for pitch_name in pitches:
            measure.append(note.Note(pitch_name, quarterLength=1.0))
        part.append(measure)
        score.insert(0, part)
    score.write("musicxml", fp=path)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
