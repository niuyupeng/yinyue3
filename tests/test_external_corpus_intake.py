from __future__ import annotations

from pathlib import Path

from music21 import duration, note, stream

from chorale.external_corpus_intake import inspect_external_musicxml_corpus


def test_external_musicxml_intake_accepts_encoded_satb_scores(tmp_path: Path) -> None:
    folder = tmp_path / "external"
    folder.mkdir()
    write_satb_score(folder / "a.musicxml")
    write_satb_score(folder / "b.musicxml")

    summary = inspect_external_musicxml_corpus(folder, min_encoded_scores=2)

    assert summary["intake_ready"] is True
    assert summary["file_count_scanned"] == 2
    assert summary["parse_ok_count"] == 2
    assert summary["satb_candidate_count"] == 2
    assert summary["encoded_count"] == 2
    assert summary["issues"] == []


def test_external_musicxml_intake_blocks_single_voice_scores(tmp_path: Path) -> None:
    folder = tmp_path / "external"
    folder.mkdir()
    write_single_voice_score(folder / "melody.musicxml")

    summary = inspect_external_musicxml_corpus(folder, min_encoded_scores=1)

    assert summary["intake_ready"] is False
    assert summary["parse_ok_count"] == 1
    assert summary["satb_candidate_count"] == 0
    assert summary["encoded_count"] == 0
    assert any("below required minimum" in issue for issue in summary["issues"])


def test_external_musicxml_intake_reports_missing_folder(tmp_path: Path) -> None:
    summary = inspect_external_musicxml_corpus(tmp_path / "missing", min_encoded_scores=1)

    assert summary["intake_ready"] is False
    assert summary["file_count_scanned"] == 0
    assert any("folder missing" in issue for issue in summary["issues"])


def write_satb_score(path: Path) -> None:
    score = stream.Score()
    pitches = {
        "Soprano": ["C5", "D5", "E5", "F5"],
        "Alto": ["G4", "A4", "G4", "A4"],
        "Tenor": ["E3", "F3", "G3", "A3"],
        "Bass": ["C3", "D3", "C3", "F2"],
    }
    for part_name, pitch_names in pitches.items():
        part = stream.Part(id=part_name)
        part.partName = part_name
        for pitch_name in pitch_names:
            n = note.Note(pitch_name)
            n.duration = duration.Duration(1.0)
            part.append(n)
        score.append(part)
    score.write("musicxml", fp=str(path))


def write_single_voice_score(path: Path) -> None:
    score = stream.Score()
    part = stream.Part(id="Soprano")
    part.partName = "Soprano"
    for pitch_name in ["C5", "D5", "E5", "F5"]:
        n = note.Note(pitch_name)
        n.duration = duration.Duration(1.0)
        part.append(n)
    score.append(part)
    score.write("musicxml", fp=str(path))
