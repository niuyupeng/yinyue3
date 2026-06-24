from __future__ import annotations

import csv
from pathlib import Path

from music21 import note, stream

from chorale import delivery_conformance_audit
from chorale.delivery_conformance_audit import ConformanceConfig, audit_delivery_conformance


def test_delivery_conformance_audit_passes_matching_full_choir(tmp_path: Path, monkeypatch) -> None:
    package = make_package(tmp_path, variant="full_choir", midi_pitches=[[72, 74], [60, 62], [55, 57], [48, 50]])
    monkeypatch.setattr(delivery_conformance_audit, "find_ffmpeg", lambda: Path("ffmpeg.exe"))
    monkeypatch.setattr(
        delivery_conformance_audit,
        "decode_mp3_audio_stats",
        lambda ffmpeg, mp3_path, sample_rate=8000: {"status": "ok", "rms": 0.1, "peak": 0.7, "sample_count": 8000},
    )

    audit = audit_delivery_conformance(package, ConformanceConfig(expected_entries=1, require_complete_variant_set=False))

    assert audit["summary"]["all_pass"] is True
    assert audit["summary"]["conformance_score"] == 100
    assert audit["rows"][0]["midi_render_pitch_check"] == "pass"
    assert audit["rows"][0]["event_alignment_check"] == "pass"
    assert audit["summary"]["event_alignment_pass_count"] == 1


def test_delivery_conformance_audit_detects_wrong_stem_voice(tmp_path: Path, monkeypatch) -> None:
    package = make_package(tmp_path, variant="stem_soprano", midi_pitches=[[60, 62]])
    monkeypatch.setattr(delivery_conformance_audit, "find_ffmpeg", lambda: Path("ffmpeg.exe"))
    monkeypatch.setattr(
        delivery_conformance_audit,
        "decode_mp3_audio_stats",
        lambda ffmpeg, mp3_path, sample_rate=8000: {"status": "ok", "rms": 0.1, "peak": 0.7, "sample_count": 8000},
    )

    audit = audit_delivery_conformance(package, ConformanceConfig(expected_entries=1, require_complete_variant_set=False))

    assert audit["summary"]["all_pass"] is False
    assert audit["rows"][0]["stem_target_check"] == "fail"
    assert "target-voice similarity" in audit["rows"][0]["issues"]


def test_delivery_conformance_audit_detects_timing_mismatch_with_same_pitch_histogram(
    tmp_path: Path,
    monkeypatch,
) -> None:
    package = make_package(tmp_path, variant="full_choir", midi_pitches=[[74, 72], [62, 60], [57, 55], [50, 48]])
    monkeypatch.setattr(delivery_conformance_audit, "find_ffmpeg", lambda: Path("ffmpeg.exe"))
    monkeypatch.setattr(
        delivery_conformance_audit,
        "decode_mp3_audio_stats",
        lambda ffmpeg, mp3_path, sample_rate=8000: {"status": "ok", "rms": 0.1, "peak": 0.7, "sample_count": 8000},
    )

    audit = audit_delivery_conformance(package, ConformanceConfig(expected_entries=1, require_complete_variant_set=False))

    assert audit["summary"]["all_pass"] is False
    assert audit["rows"][0]["midi_render_pitch_check"] == "pass"
    assert audit["rows"][0]["event_alignment_check"] == "fail"
    assert "event recall" in audit["rows"][0]["issues"]


def test_find_ffmpeg_reads_project_env(monkeypatch, tmp_path: Path) -> None:
    exe = tmp_path / "ffmpeg.exe"
    exe.write_bytes(b"exe")
    monkeypatch.setenv("CHORALE_FFMPEG_EXE", str(exe))

    assert delivery_conformance_audit.find_ffmpeg() == exe


def make_package(tmp_path: Path, *, variant: str, midi_pitches: list[list[int]]) -> Path:
    package = tmp_path / "package"
    score_id = "P1S01"
    source = package / "absolute_score_musicxml" / f"{score_id}.musicxml"
    render = package / "render_xml" / "absolute" / score_id / f"{score_id}_{variant}.musicxml"
    midi = package / "midi_pro" / "absolute" / score_id / f"{score_id}_{variant}.mid"
    mp3 = package / "audio_pro" / "absolute" / score_id / f"{score_id}_{variant}.mp3"
    for path in [source, render, midi, mp3]:
        path.parent.mkdir(parents=True, exist_ok=True)

    source_pitches = [[72, 74], [60, 62], [55, 57], [48, 50]]
    write_score(source, source_pitches)
    if variant == "stem_soprano":
        write_score(render, [[72, 74], [], [], []])
    else:
        write_score(render, source_pitches)
    write_score(midi, midi_pitches)
    mp3.write_bytes(b"ID3fake")

    rows = [
        {
            "group": "absolute",
            "score_id": score_id,
            "variant": variant,
            "source_musicxml": source.relative_to(package).as_posix(),
            "render_musicxml": render.relative_to(package).as_posix(),
            "midi": midi.relative_to(package).as_posix(),
            "mp3": mp3.relative_to(package).as_posix(),
            "duration_sec": "2.000",
        }
    ]
    manifest = package / "audio_pro" / "pro_playback_manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return package


def write_score(path: Path, part_pitches: list[list[int]]) -> None:
    score = stream.Score()
    for idx, pitches in enumerate(part_pitches):
        part = stream.Part(id=f"P{idx}")
        if pitches:
            for pitch in pitches:
                part.append(note.Note(pitch, quarterLength=1.0))
        else:
            part.append(note.Rest(quarterLength=2.0))
        score.insert(0, part)
    fmt = "midi" if path.suffix.lower() in {".mid", ".midi"} else "musicxml"
    score.write(fmt, fp=str(path))
