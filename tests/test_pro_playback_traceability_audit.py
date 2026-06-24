from __future__ import annotations

import csv
from pathlib import Path

from chorale.playback_render import musicxml_to_midi, synthesize_musicxml_to_wav_additive, validate_wav_file
from chorale.pro_playback_package import DEFAULT_VARIANTS, write_variant_musicxml_file
from chorale.pro_playback_traceability_audit import audit_pro_playback_package
from tests.test_score_tokenizer import tiny_satb_score


def test_pro_playback_traceability_audit_passes_valid_package(tmp_path: Path) -> None:
    package = make_minimal_pro_package(tmp_path / "package")

    audit = audit_pro_playback_package(package, mode="master")

    assert audit["all_pass"] is True
    assert audit["score_audio_traceability_score"] == 100
    assert audit["summary"]["entry_count"] == 6
    assert audit["summary"]["score_count"] == 1


def test_pro_playback_traceability_audit_detects_wrong_stem(tmp_path: Path) -> None:
    package = make_minimal_pro_package(tmp_path / "package")
    wrong = package / "render_xml" / "absolute" / "P1S01" / "WRONG_stem_alto.musicxml"
    wrong.write_bytes((package / "render_xml" / "absolute" / "P1S01" / "P1S01_stem_alto.musicxml").read_bytes())
    manifest = package / "audio_pro" / "pro_playback_manifest.csv"
    text = manifest.read_text(encoding="utf-8")
    manifest.write_text(text.replace("render_xml/absolute/P1S01/P1S01_stem_alto.musicxml", "render_xml/absolute/P1S01/WRONG_stem_alto.musicxml"), encoding="utf-8")

    audit = audit_pro_playback_package(package, mode="master")

    assert audit["all_pass"] is False
    assert any("file stems do not match" in issue for issue in audit["issues"])


def make_minimal_pro_package(package: Path) -> Path:
    source_dir = package / "absolute_score_musicxml"
    source_dir.mkdir(parents=True)
    source_musicxml = source_dir / "P1S01.musicxml"
    tiny_satb_score().write("musicxml", fp=str(source_musicxml))

    rows = []
    for variant in DEFAULT_VARIANTS:
        score_id = "P1S01"
        render_path = package / "render_xml" / "absolute" / score_id / f"{score_id}_{variant.name}.musicxml"
        midi_path = package / "midi_pro" / "absolute" / score_id / f"{score_id}_{variant.name}.mid"
        wav_path = package / "audio_pro" / "absolute" / score_id / f"{score_id}_{variant.name}.wav"
        mp3_path = package / "audio_pro" / "absolute" / score_id / f"{score_id}_{variant.name}.mp3"
        render_path.parent.mkdir(parents=True, exist_ok=True)
        midi_path.parent.mkdir(parents=True, exist_ok=True)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        mp3_path.parent.mkdir(parents=True, exist_ok=True)
        write_variant_musicxml_file(source_musicxml, render_path, variant)
        musicxml_to_midi(render_path, midi_path)
        synthesize_musicxml_to_wav_additive(render_path, wav_path)
        validation = validate_wav_file(wav_path)
        mp3_path.write_bytes(b"ID3" + bytes(4096))
        rows.append(
            {
                "group": "absolute",
                "score_id": score_id,
                "variant": variant.name,
                "voice": "",
                "description": variant.description,
                "source_musicxml": "absolute_score_musicxml/P1S01.musicxml",
                "render_musicxml": f"render_xml/absolute/P1S01/P1S01_{variant.name}.musicxml",
                "midi": f"midi_pro/absolute/P1S01/P1S01_{variant.name}.mid",
                "wav": f"audio_pro/absolute/P1S01/P1S01_{variant.name}.wav",
                "mp3": f"audio_pro/absolute/P1S01/P1S01_{variant.name}.mp3",
                "midi_backend": "music21",
                "audio_backend": "additive",
                "status": "ok",
                "duration_sec": f"{validation.duration_sec:.3f}",
                "rms": f"{validation.rms:.3f}",
                "peak": str(validation.peak),
                "message": "",
            }
        )

    manifest = package / "audio_pro" / "pro_playback_manifest.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return package
