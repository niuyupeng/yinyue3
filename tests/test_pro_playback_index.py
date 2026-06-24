from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from chorale.pro_playback_index import build_playback_index


def _write_manifest(package: Path, *, mp3_exists: bool = True) -> None:
    (package / "audio_pro" / "absolute" / "P1S01").mkdir(parents=True)
    (package / "absolute_score_musicxml").mkdir(parents=True)
    (package / "render_xml" / "absolute" / "P1S01").mkdir(parents=True)
    (package / "audio_pro" / "absolute" / "P1S01" / "P1S01_full_choir.wav").write_bytes(b"RIFF")
    if mp3_exists:
        (package / "audio_pro" / "absolute" / "P1S01" / "P1S01_full_choir.mp3").write_bytes(b"ID3")
    (package / "absolute_score_musicxml" / "P1S01.musicxml").write_text("<score-partwise/>", encoding="utf-8")
    (package / "render_xml" / "absolute" / "P1S01" / "P1S01_full_choir.musicxml").write_text(
        "<score-partwise/>", encoding="utf-8"
    )
    with (package / "audio_pro" / "commercial_qc_summary.json").open("w", encoding="utf-8") as handle:
        json.dump({"qc_score": 100, "pass_count": 1, "fail_count": 0}, handle)
    with (package / "audio_pro" / "pro_playback_manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "group",
                "score_id",
                "variant",
                "source_musicxml",
                "render_musicxml",
                "wav",
                "mp3",
                "duration_sec",
                "rms",
                "peak",
                "status",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "group": "absolute",
                "score_id": "P1S01",
                "variant": "full_choir",
                "source_musicxml": "absolute_score_musicxml/P1S01.musicxml",
                "render_musicxml": "render_xml/absolute/P1S01/P1S01_full_choir.musicxml",
                "wav": "audio_pro/absolute/P1S01/P1S01_full_choir.wav",
                "mp3": "audio_pro/absolute/P1S01/P1S01_full_choir.mp3",
                "duration_sec": "12.5",
                "rms": "1234",
                "peak": "28834",
                "status": "ok",
            }
        )


def test_pro_playback_index_builds_static_console(tmp_path: Path) -> None:
    _write_manifest(tmp_path)

    html_path = build_playback_index(tmp_path)

    html = html_path.read_text(encoding="utf-8")
    assert "Project1 SATB 乐谱-音频审阅台" in html
    assert "P1S01" in html
    assert "P1S01_full_choir.mp3" in html
    assert "QC score: 100/100" in html


def test_pro_playback_index_fails_on_missing_audio_reference(tmp_path: Path) -> None:
    _write_manifest(tmp_path, mp3_exists=False)

    with pytest.raises(FileNotFoundError, match="P1S01/full_choir"):
        build_playback_index(tmp_path)
