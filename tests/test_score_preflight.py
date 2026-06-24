from __future__ import annotations

from pathlib import Path

from music21 import chord, instrument, note, stream

from chorale.score_preflight import analyze_score_input


def test_preflight_accepts_simple_soprano_melody(tmp_path: Path) -> None:
    input_path = tmp_path / "soprano.musicxml"
    write_single_voice_score(input_path, "Soprano", [60, 62, 64, 65])

    report = analyze_score_input(input_path, task="soprano_to_satb", input_role="soprano")

    assert report["status"] == "pass"
    assert report["part_count"] == 1
    assert report["note_count"] == 4
    assert report["resolved_known_voices"] == ["soprano"]
    assert report["will_truncate"] is False


def test_preflight_marks_polyphonic_melody_for_review(tmp_path: Path) -> None:
    input_path = tmp_path / "chord_melody.musicxml"
    score = stream.Score()
    part = stream.Part(id="Soprano")
    part.partName = "Soprano"
    part.insert(0, instrument.Vocalist())
    c = chord.Chord([60, 64, 67])
    c.duration.quarterLength = 1.0
    part.append(c)
    score.append(part)
    score.write("musicxml", fp=str(input_path))

    report = analyze_score_input(input_path, task="soprano_to_satb", input_role="soprano")

    assert report["status"] == "needs_review"
    assert any("polyphonic" in item for item in report["issues"])


def test_preflight_marks_out_of_range_voice_for_review(tmp_path: Path) -> None:
    input_path = tmp_path / "low_soprano.musicxml"
    write_single_voice_score(input_path, "Soprano", [48, 50, 52, 53])

    report = analyze_score_input(input_path, task="soprano_to_satb", input_role="soprano")

    assert report["status"] == "needs_review"
    assert report["parts"][0]["out_of_range_count"] == 4
    assert any("outside" in item for item in report["issues"])


def test_preflight_marks_long_score_for_review(tmp_path: Path) -> None:
    input_path = tmp_path / "long.musicxml"
    write_single_voice_score(input_path, "Soprano", [60] * 12)

    report = analyze_score_input(input_path, task="soprano_to_satb", input_role="soprano", max_seq_len=8)

    assert report["status"] == "needs_review"
    assert report["will_truncate"] is True
    assert any("will be truncated" in item for item in report["issues"])


def test_preflight_fails_bad_musicxml(tmp_path: Path) -> None:
    input_path = tmp_path / "bad.musicxml"
    input_path.write_text("not musicxml", encoding="utf-8")

    report = analyze_score_input(input_path)

    assert report["status"] == "failed"
    assert report["critical"]


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
