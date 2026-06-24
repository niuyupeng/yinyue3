from __future__ import annotations

import json
from pathlib import Path

from music21 import converter, instrument, note, stream

from chorale.harmonize import harmonize_musicxml


def test_harmonize_soprano_musicxml_preserves_melody_and_exports_satb(tmp_path: Path) -> None:
    input_path = tmp_path / "soprano.musicxml"
    write_single_voice_score(input_path, "Soprano", [60, 62, 64, 65])

    summary = harmonize_musicxml(
        input_path,
        tmp_path / "out",
        task="soprano_to_satb",
        input_role="soprano",
        prefix="soprano_case",
    )

    output = Path(summary["outputs"]["harmonized_musicxml"])
    report = Path(summary["outputs"]["rule_report_json"])
    parsed = converter.parse(str(output))

    assert output.is_file()
    assert report.is_file()
    assert len(parsed.parts) == 4
    assert first_part_pitches(parsed) == [60, 62, 64, 65]
    assert summary["known_voices"] == ["soprano"]
    assert summary["input_preflight"]["status"] == "pass"
    assert summary["engine"] == "rule_baseline_practical"
    assert summary["symbolic_repair"]["enabled"] is True
    assert json.loads(report.read_text(encoding="utf-8"))["title"].endswith("rule report")
    saved_summary = json.loads(Path(summary["outputs"]["summary_json"]).read_text(encoding="utf-8"))
    assert saved_summary["outputs"]["summary_json"].endswith("soprano_case_harmonization_summary.json")
    assert "reported_final_total_violations" in saved_summary["symbolic_repair"]
    assert saved_summary["quality_gate"]["status"] in {"pass", "needs_review"}
    assert "thresholds" in saved_summary["quality_gate"]
    assert saved_summary["known_voice_preservation"]["pass"] is True
    assert saved_summary["known_voice_preservation"]["mismatches"] == 0
    assert saved_summary["score_validation"]["parse_ok"] is True
    assert saved_summary["score_validation"]["part_count"] == 4
    assert saved_summary["input_preflight"]["resolved_known_voices"] == ["soprano"]
    assert saved_summary["cadential_repair"]["enabled"] is True


def test_harmonize_bass_musicxml_preserves_bass_line_and_exports_satb(tmp_path: Path) -> None:
    input_path = tmp_path / "bass.musicxml"
    write_single_voice_score(input_path, "Bass", [48, 43, 45, 40])

    summary = harmonize_musicxml(
        input_path,
        tmp_path / "out",
        task="bass_to_satb",
        input_role="bass",
        prefix="bass_case",
    )

    output = Path(summary["outputs"]["harmonized_musicxml"])
    parsed = converter.parse(str(output))

    assert output.is_file()
    assert len(parsed.parts) == 4
    assert part_pitches(parsed.parts[3]) == [48, 43, 45, 40]
    assert summary["known_voices"] == ["bass"]


def write_single_voice_score(path: Path, part_name: str, pitches: list[int]) -> None:
    score = stream.Score()
    part = stream.Part(id=part_name)
    part.partName = part_name
    part.insert(0, instrument.Vocalist())
    for midi in pitches:
        n = note.Note(midi)
        n.duration.quarterLength = 1.0
        part.append(n)
    score.append(part)
    score.write("musicxml", fp=str(path))


def first_part_pitches(score: stream.Score) -> list[int]:
    return part_pitches(score.parts[0])


def part_pitches(part: stream.Part) -> list[int]:
    return [int(n.pitch.midi) for n in part.flatten().notes]
