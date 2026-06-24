from __future__ import annotations

import csv
from pathlib import Path

from chorale.score_audio_correspondence import (
    REQUIRED_VARIANTS,
    prepare_mp3_delivery_correspondence,
    read_manifest,
)


FIELDNAMES = [
    "group",
    "score_id",
    "variant",
    "source_musicxml",
    "render_musicxml",
    "midi",
    "wav",
    "mp3",
    "status",
    "message",
]


def _write_package_with_source_manifest(root: Path, *, missing_mp3: bool = False) -> Path:
    source_manifest = root / "master" / "audio_pro" / "pro_playback_manifest.csv"
    rows = []
    variants = sorted(REQUIRED_VARIANTS)
    for idx in range(40):
        group = "absolute" if idx < 20 else "paired"
        score_id = f"P1S{idx + 1:02d}"
        for variant in variants:
            source = f"{group}_score_musicxml/{score_id}.musicxml"
            render = f"render_xml/{group}/{score_id}/{score_id}_{variant}.musicxml"
            midi = f"midi_pro/{group}/{score_id}/{score_id}_{variant}.mid"
            wav = f"audio_pro/{group}/{score_id}/{score_id}_{variant}.wav"
            mp3 = f"audio_pro/{group}/{score_id}/{score_id}_{variant}.mp3"
            for rel in [source, render, midi]:
                (root / "package" / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / "package" / rel).write_bytes(f"{score_id}-{variant}-{rel}".encode("ascii"))
            if not (missing_mp3 and score_id == "P1S01" and variant == "stem_alto"):
                (root / "package" / mp3).parent.mkdir(parents=True, exist_ok=True)
                (root / "package" / mp3).write_bytes(b"ID3" + score_id.encode("ascii") + variant.encode("ascii"))
            rows.append(
                {
                    "group": group,
                    "score_id": score_id,
                    "variant": variant,
                    "source_musicxml": source,
                    "render_musicxml": render,
                    "midi": midi,
                    "wav": wav,
                    "mp3": mp3,
                    "status": "ok",
                    "message": " padded ",
                }
            )
    source_manifest.parent.mkdir(parents=True, exist_ok=True)
    with source_manifest.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return source_manifest


def test_prepare_mp3_delivery_correspondence_writes_clean_240_row_mapping(tmp_path: Path) -> None:
    source_manifest = _write_package_with_source_manifest(tmp_path)
    package = tmp_path / "package"
    stage_manifest = package / "audio_pro" / "pro_playback_manifest.csv"

    report = prepare_mp3_delivery_correspondence(package, source_manifest, stage_manifest)
    rows, fieldnames = read_manifest(package / "SCORE_AUDIO_CORRESPONDENCE.csv")
    stage_rows, _ = read_manifest(stage_manifest)

    assert report["summary"]["all_pass"] is True
    assert report["summary"]["entry_count"] == 240
    assert report["summary"]["score_variant_groups"] == 40
    assert len(rows) == 240
    assert len(stage_rows) == 240
    assert all(row["wav"] == "" for row in rows)
    assert all(row["wav"] == "" for row in stage_rows)
    assert "source_musicxml_sha256" in fieldnames
    assert "render_musicxml_sha256" in fieldnames
    assert "midi_sha256" in fieldnames
    assert "mp3_sha256" in fieldnames
    assert all(row["mp3_sha256"] for row in rows)
    assert (package / "SCORE_AUDIO_CORRESPONDENCE_SUMMARY.json").is_file()
    assert (package / "SCORE_AUDIO_CORRESPONDENCE_README.md").is_file()


def test_prepare_mp3_delivery_correspondence_reports_missing_references(tmp_path: Path) -> None:
    source_manifest = _write_package_with_source_manifest(tmp_path, missing_mp3=True)
    package = tmp_path / "package"
    stage_manifest = package / "audio_pro" / "pro_playback_manifest.csv"

    report = prepare_mp3_delivery_correspondence(package, source_manifest, stage_manifest)

    assert report["summary"]["all_pass"] is False
    assert report["summary"]["missing_reference_count"] == 1
    assert "missing mp3" in report["summary"]["missing_reference_examples"][0]
