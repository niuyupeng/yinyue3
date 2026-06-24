from __future__ import annotations

import csv
import json
from pathlib import Path

from chorale.delivery_player_static_audit import audit_player_package
from chorale.pro_playback_index import build_playback_index


VARIANTS = ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]


def test_delivery_player_static_audit_passes_clean_package(tmp_path: Path) -> None:
    package = make_player_package(tmp_path)
    build_playback_index(package)

    report = audit_player_package(package)

    assert report["all_pass"] is True
    assert report["score_count"] == 40
    assert report["manifest_rows"] == 240
    assert report["bad_text_file_count"] == 0


def test_delivery_player_static_audit_detects_mojibake_text(tmp_path: Path) -> None:
    package = make_player_package(tmp_path)
    build_playback_index(package)
    (package / "README_CN.md").write_text("Project1 璋遍潰-闊抽", encoding="utf-8")

    report = audit_player_package(package)

    assert report["all_pass"] is False
    assert report["bad_text_file_count"] == 1


def make_player_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    (package / "audio_pro").mkdir(parents=True)
    (package / "absolute_score_musicxml").mkdir(parents=True)
    (package / "absolute_score_pdfs").mkdir(parents=True)
    (package / "render_xml" / "absolute").mkdir(parents=True)
    (package / "midi_pro" / "absolute").mkdir(parents=True)
    rows: list[dict[str, str]] = []
    for idx in range(40):
        score_id = f"P1S{idx + 1:02d}"
        source = package / "absolute_score_musicxml" / f"{score_id}.musicxml"
        source.write_text("<score-partwise/>", encoding="utf-8")
        (package / "absolute_score_pdfs" / f"{score_id}.pdf").write_bytes(b"%PDF")
        for variant in VARIANTS:
            render = package / "render_xml" / "absolute" / score_id / f"{score_id}_{variant}.musicxml"
            midi = package / "midi_pro" / "absolute" / score_id / f"{score_id}_{variant}.mid"
            mp3 = package / "audio_pro" / "absolute" / score_id / f"{score_id}_{variant}.mp3"
            render.parent.mkdir(parents=True, exist_ok=True)
            midi.parent.mkdir(parents=True, exist_ok=True)
            mp3.parent.mkdir(parents=True, exist_ok=True)
            render.write_text("<score-partwise/>", encoding="utf-8")
            midi.write_bytes(b"MThd")
            mp3.write_bytes(b"ID3")
            rows.append(
                {
                    "group": "absolute",
                    "score_id": score_id,
                    "variant": variant,
                    "voice": "",
                    "description": "",
                    "source_musicxml": f"absolute_score_musicxml\\{score_id}.musicxml",
                    "render_musicxml": f"render_xml\\absolute\\{score_id}\\{score_id}_{variant}.musicxml",
                    "midi": f"midi_pro\\absolute\\{score_id}\\{score_id}_{variant}.mid",
                    "wav": "",
                    "mp3": f"audio_pro\\absolute\\{score_id}\\{score_id}_{variant}.mp3",
                    "midi_backend": "test",
                    "audio_backend": "test",
                    "status": "ok",
                    "duration_sec": "1.000",
                    "rms": "1.0",
                    "peak": "100",
                    "message": "",
                }
            )
    with (package / "audio_pro" / "pro_playback_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    (package / "audio_pro" / "commercial_qc_summary.json").write_text(
        json.dumps({"qc_score": 100, "pass_count": 240, "fail_count": 0}),
        encoding="utf-8",
    )
    return package
