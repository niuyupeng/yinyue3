from __future__ import annotations

import json
from pathlib import Path

from music21 import converter, instrument, note, stream

from chorale.batch_harmonize import batch_harmonize


def test_batch_harmonize_writes_per_score_outputs_and_summary(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    write_single_voice_score(input_dir / "melody_a.musicxml", "Soprano", [60, 62, 64, 65])
    write_single_voice_score(input_dir / "melody_b.musicxml", "Soprano", [67, 65, 64, 62])

    report = batch_harmonize(input_dir, tmp_path / "batch_out", task="soprano_to_satb", input_role="soprano")

    assert report["discovered_files"] == 2
    assert report["completed"] == 2
    assert report["failed"] == 0
    assert report["all_pass"] is True
    assert (tmp_path / "batch_out" / "batch_harmonization_summary.json").is_file()
    assert (tmp_path / "batch_out" / "batch_harmonization_summary.csv").is_file()
    assert (tmp_path / "batch_out" / "batch_harmonization_summary.md").is_file()
    assert (tmp_path / "batch_out" / "batch_review_queue.csv").is_file()
    assert (tmp_path / "batch_out" / "batch_review_queue.md").is_file()
    for row in report["rows"]:
        assert row["quality_status"] in {"pass", "needs_review"}
        assert row["quality_score"] != ""
        assert row["known_voice_preservation_pass"] is True
        assert int(row["known_voice_mismatches"]) == 0
        assert row["input_preflight_status"] == "pass"
        assert int(row["input_part_count"]) == 1
        assert int(row["input_note_count"]) > 0
        assert row["score_parse_ok"] is True
        assert int(row["score_part_count"]) == 4
        assert row["cadential_repair_enabled"] is True
        output = Path(row["harmonized_musicxml"])
        parsed = converter.parse(str(output))
        assert output.is_file()
        assert len(parsed.parts) == 4
        assert Path(row["rule_report_json"]).is_file()
        assert Path(row["summary_json"]).is_file()


def test_batch_harmonize_records_bad_input_without_losing_good_scores(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    write_single_voice_score(input_dir / "good.musicxml", "Soprano", [60, 62, 64, 65])
    (input_dir / "bad.musicxml").write_text("not musicxml", encoding="utf-8")

    report = batch_harmonize(input_dir, tmp_path / "batch_out", task="soprano_to_satb", input_role="soprano")

    assert report["discovered_files"] == 2
    assert report["completed"] == 1
    assert report["failed"] == 1
    failed = [row for row in report["rows"] if row["status"] == "failed"]
    assert failed and failed[0]["error_type"]
    assert failed[0]["quality_status"] == "failed"
    assert report["needs_review"] >= 1
    assert report["all_quality_pass"] is False
    assert (tmp_path / "batch_out" / "batch_review_queue.csv").is_file()
    saved = json.loads((tmp_path / "batch_out" / "batch_harmonization_summary.json").read_text(encoding="utf-8"))
    assert saved["failed"] == 1


def test_batch_harmonize_review_queue_records_audio_quality_requirement(tmp_path: Path) -> None:
    input_dir = tmp_path / "inputs"
    input_dir.mkdir()
    write_single_voice_score(input_dir / "melody.musicxml", "Soprano", [60, 62, 64, 65])

    report = batch_harmonize(
        input_dir,
        tmp_path / "batch_out",
        task="soprano_to_satb",
        input_role="soprano",
        require_audio_for_quality=True,
    )

    assert report["completed"] == 1
    assert report["needs_review"] == 1
    assert report["all_quality_pass"] is False
    assert report["review_queue"][0]["quality_status"] == "needs_review"
    review_md = (tmp_path / "batch_out" / "batch_review_queue.md").read_text(encoding="utf-8")
    assert "Project1 Batch Review Queue" in review_md


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
