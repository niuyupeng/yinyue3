from __future__ import annotations

import csv
from pathlib import Path

from chorale import delivery_media_audit
from chorale.delivery_media_audit import MediaAuditConfig, audit_delivery_media


def test_delivery_media_audit_passes_with_parseable_media(tmp_path: Path, monkeypatch) -> None:
    package = make_package(tmp_path)
    monkeypatch.setattr(delivery_media_audit, "find_ffprobe", lambda: Path("ffprobe.exe"))
    monkeypatch.setattr(
        delivery_media_audit,
        "probe_mp3",
        lambda ffprobe, mp3_path: {"status": "ok", "duration_sec": 10.12, "bit_rate": 192000, "codec_name": "mp3"},
    )
    monkeypatch.setattr(delivery_media_audit, "parse_midi", lambda midi_path: {"status": "ok", "note_count": 12, "message": ""})

    audit = audit_delivery_media(package, MediaAuditConfig(min_mp3_size_bytes=3))

    assert audit["summary"]["all_pass"] is True
    assert audit["summary"]["entry_count"] == 240
    assert audit["summary"]["mp3_parse_ok_count"] == 240
    assert audit["summary"]["midi_parse_ok_count"] == 240


def test_delivery_media_audit_detects_duration_mismatch(tmp_path: Path, monkeypatch) -> None:
    package = make_package(tmp_path)
    monkeypatch.setattr(delivery_media_audit, "find_ffprobe", lambda: Path("ffprobe.exe"))
    monkeypatch.setattr(
        delivery_media_audit,
        "probe_mp3",
        lambda ffprobe, mp3_path: {"status": "ok", "duration_sec": 3.0, "bit_rate": 192000, "codec_name": "mp3"},
    )
    monkeypatch.setattr(delivery_media_audit, "parse_midi", lambda midi_path: {"status": "ok", "note_count": 12, "message": ""})

    audit = audit_delivery_media(package, MediaAuditConfig(min_mp3_size_bytes=3, max_duration_delta_sec=0.5))

    assert audit["summary"]["all_pass"] is False
    assert audit["summary"]["fail_count"] == 240
    assert "duration differs" in audit["rows"][0]["issues"]


def test_find_ffprobe_reads_project_env(monkeypatch, tmp_path: Path) -> None:
    exe = tmp_path / "ffprobe.exe"
    exe.write_bytes(b"exe")
    monkeypatch.setenv("CHORALE_FFPROBE_EXE", str(exe))

    assert delivery_media_audit.find_ffprobe() == exe


def make_package(tmp_path: Path) -> Path:
    package = tmp_path / "package"
    (package / "audio_pro").mkdir(parents=True)
    rows: list[dict[str, str]] = []
    variants = ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]
    for score_idx in range(40):
        score_id = f"P1S{score_idx + 1:02d}"
        for variant in variants:
            mp3 = package / "audio_pro" / "absolute" / score_id / f"{score_id}_{variant}.mp3"
            midi = package / "midi_pro" / "absolute" / score_id / f"{score_id}_{variant}.mid"
            mp3.parent.mkdir(parents=True, exist_ok=True)
            midi.parent.mkdir(parents=True, exist_ok=True)
            mp3.write_bytes(b"ID3fake")
            midi.write_bytes(b"MThd")
            rows.append(
                {
                    "group": "absolute",
                    "score_id": score_id,
                    "variant": variant,
                    "duration_sec": "10.000",
                    "mp3": mp3.relative_to(package).as_posix(),
                    "midi": midi.relative_to(package).as_posix(),
                }
            )
    with (package / "audio_pro" / "pro_playback_manifest.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return package
