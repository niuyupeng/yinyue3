from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from music21 import converter

from chorale.playback_render import validate_wav_file


EXPECTED_GROUPS = {
    "absolute": {
        "musicxml": "absolute_score_musicxml",
        "pdf": "absolute_score_pdfs",
        "midi": "playback_midi/absolute_score_midi",
        "wav": "playback_audio/absolute_score_wav",
        "mp3": "playback_audio/absolute_score_mp3",
    },
    "paired": {
        "musicxml": "paired_comparison_musicxml",
        "pdf": "paired_comparison_pdfs",
        "midi": "playback_midi/paired_comparison_midi",
        "wav": "playback_audio/paired_comparison_wav",
        "mp3": "playback_audio/paired_comparison_mp3",
    },
}


def audit_package(package_dir: str | Path) -> dict[str, object]:
    package = Path(package_dir)
    if not package.is_dir():
        raise NotADirectoryError(f"Expert package directory not found: {package}")
    rows: list[dict[str, str]] = []
    errors: list[str] = []
    for group, folders in EXPECTED_GROUPS.items():
        musicxml_dir = package / folders["musicxml"]
        if not musicxml_dir.exists():
            errors.append(f"Missing MusicXML directory for {group}: {musicxml_dir}")
            continue
        for musicxml_path in sorted(musicxml_dir.glob("*.musicxml")):
            row = audit_score_entry(package, group, musicxml_path)
            rows.append(row)
            if row["entry_ok"] != "yes":
                errors.append(f"{group}/{row['score_id']}: {row['issues']}")

    summary = summarize_rows(rows, errors)
    return {"package": str(package), "summary": summary, "rows": rows, "errors": errors}


def audit_score_entry(package: Path, group: str, musicxml_path: Path) -> dict[str, str]:
    folders = EXPECTED_GROUPS[group]
    stem = musicxml_path.stem
    pdf_path = package / folders["pdf"] / f"{stem}.pdf"
    midi_path = package / folders["midi"] / f"{stem}.mid"
    wav_path = package / folders["wav"] / f"{stem}.wav"
    mp3_path = package / folders["mp3"] / f"{stem}.mp3"

    issues: list[str] = []
    paths = {
        "musicxml": musicxml_path,
        "pdf": pdf_path,
        "midi": midi_path,
        "wav": wav_path,
        "mp3": mp3_path,
    }
    for kind, path in paths.items():
        if not path.is_file():
            issues.append(f"missing {kind}: {path}")

    part_count = 0
    part_names = ""
    note_counts = ""
    score_duration = ""
    try:
        score = converter.parse(str(musicxml_path))
        parts = list(score.parts)
        part_count = len(parts)
        part_names = "|".join(clean_part_name(part, idx) for idx, part in enumerate(parts))
        counts = [len(part.flatten().notes) for part in parts]
        note_counts = "|".join(str(count) for count in counts)
        score_duration = f"{float(score.highestTime):.3f}"
        if part_count != 4:
            issues.append(f"expected 4 SATB parts, found {part_count}")
        if any(count <= 0 for count in counts):
            issues.append(f"one or more parts have no notes: {note_counts}")
    except Exception as exc:
        issues.append(f"MusicXML parse failed: {type(exc).__name__}: {exc}")

    wav_validation = validate_wav_file(wav_path) if wav_path.is_file() else None
    if wav_validation is not None and not wav_validation.ok:
        issues.append(f"WAV validation failed: {wav_validation.message}")
    if mp3_path.is_file() and mp3_path.stat().st_size < 1024:
        issues.append(f"MP3 too small: {mp3_path.stat().st_size} bytes")

    midi_parse_ok = ""
    midi_note_count = ""
    if midi_path.is_file():
        try:
            midi_score = converter.parse(str(midi_path))
            midi_notes = list(midi_score.flatten().notes)
            midi_parse_ok = "yes"
            midi_note_count = str(len(midi_notes))
            if not midi_notes:
                issues.append("MIDI parse succeeded but contains no notes")
        except Exception as exc:
            midi_parse_ok = "no"
            issues.append(f"MIDI parse failed: {type(exc).__name__}: {exc}")

    midi_backend = manifest_backend(
        package / "playback_midi" / "playback_midi_manifest.csv",
        stem,
        ["output_midi", "source_musicxml"],
    )
    audio_backend = manifest_backend(
        package / "playback_audio" / "playback_audio_manifest.csv",
        stem,
        ["output_wav", "output_mp3", "source_musicxml"],
    )
    if audio_backend == "fluidsynth" and midi_backend != "musescore":
        issues.append(
            "legacy playback chain uses FluidSynth without MuseScore-exported MIDI provenance; "
            "regenerate the expert package with current playback tools"
        )

    row = {
        "group": group,
        "score_id": stem,
        "entry_ok": "yes" if not issues else "no",
        "issues": "; ".join(issues),
        "musicxml": rel(musicxml_path, package),
        "pdf": rel(pdf_path, package),
        "midi": rel(midi_path, package),
        "wav": rel(wav_path, package),
        "mp3": rel(mp3_path, package),
        "same_stem_ok": "yes" if same_stem(stem, pdf_path, midi_path, wav_path, mp3_path) else "no",
        "satb_part_count": str(part_count),
        "part_names": part_names,
        "part_note_counts": note_counts,
        "all_four_parts_have_notes": "yes" if part_count == 4 and all_positive_counts(note_counts) else "no",
        "midi_parse_ok": midi_parse_ok,
        "midi_note_count": midi_note_count,
        "midi_export_backend": midi_backend,
        "audio_backend": audio_backend,
        "score_duration_quarter_length": score_duration,
        "wav_duration_sec": f"{wav_validation.duration_sec:.3f}" if wav_validation else "",
        "wav_rms": f"{wav_validation.rms:.3f}" if wav_validation else "",
        "wav_peak": str(wav_validation.peak) if wav_validation else "",
        "musicxml_sha256": sha256_file(musicxml_path) if musicxml_path.is_file() else "",
        "pdf_sha256": sha256_file(pdf_path) if pdf_path.is_file() else "",
        "midi_sha256": sha256_file(midi_path) if midi_path.is_file() else "",
        "wav_sha256": sha256_file(wav_path) if wav_path.is_file() else "",
        "mp3_sha256": sha256_file(mp3_path) if mp3_path.is_file() else "",
    }
    return row


def clean_part_name(part, idx: int) -> str:
    value = part.partName or part.id or f"Part{idx + 1}"
    return str(value).replace(",", " ").replace("|", "/")


def all_positive_counts(serialized_counts: str) -> bool:
    if not serialized_counts:
        return False
    try:
        return all(int(value) > 0 for value in serialized_counts.split("|"))
    except ValueError:
        return False


def same_stem(stem: str, *paths: Path) -> bool:
    return all(path.stem == stem for path in paths)


def rel(path: Path, package: Path) -> str:
    try:
        return str(path.relative_to(package))
    except ValueError:
        return str(path)


def manifest_backend(manifest_path: Path, stem: str, path_fields: list[str]) -> str:
    if not manifest_path.is_file():
        return ""
    try:
        with manifest_path.open("r", newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                for field in path_fields:
                    value = row.get(field) or ""
                    if value and Path(value).stem == stem:
                        return row.get("backend") or ""
    except Exception:
        return ""
    return ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize_rows(rows: list[dict[str, str]], errors: list[str]) -> dict[str, object]:
    group_counts: dict[str, int] = {}
    for row in rows:
        group_counts[row["group"]] = group_counts.get(row["group"], 0) + 1
    return {
        "entry_count": len(rows),
        "group_counts": group_counts,
        "all_entries_ok": not errors,
        "error_count": len(errors),
        "all_same_stem": all(row["same_stem_ok"] == "yes" for row in rows),
        "all_entries_have_four_parts": all(row["satb_part_count"] == "4" for row in rows),
        "all_four_parts_have_notes": all(row["all_four_parts_have_notes"] == "yes" for row in rows),
        "all_midi_parseable": all(row["midi_parse_ok"] in {"", "yes"} for row in rows),
        "all_playback_backends_current": all(
            not (row["audio_backend"] == "fluidsynth" and row["midi_export_backend"] != "musescore")
            for row in rows
        ),
        "all_wav_non_silent": all(float(row["wav_rms"] or 0.0) >= 1.0 and int(row["wav_peak"] or 0) > 0 for row in rows),
    }


def write_audit_outputs(package_dir: str | Path, audit: dict[str, object]) -> dict[str, str]:
    package = Path(package_dir)
    rows = audit["rows"]
    if not isinstance(rows, list):
        raise TypeError("audit rows must be a list")

    csv_path = package / "SCORE_AUDIO_CORRESPONDENCE.csv"
    json_path = package / "SCORE_AUDIO_CORRESPONDENCE_SUMMARY.json"
    md_path = package / "SCORE_AUDIO_CORRESPONDENCE_README.md"

    fieldnames = [
        "group",
        "score_id",
        "entry_ok",
        "issues",
        "musicxml",
        "pdf",
        "midi",
        "wav",
        "mp3",
        "same_stem_ok",
        "satb_part_count",
        "part_names",
        "part_note_counts",
        "all_four_parts_have_notes",
        "midi_parse_ok",
        "midi_note_count",
        "midi_export_backend",
        "audio_backend",
        "score_duration_quarter_length",
        "wav_duration_sec",
        "wav_rms",
        "wav_peak",
        "musicxml_sha256",
        "pdf_sha256",
        "midi_sha256",
        "wav_sha256",
        "mp3_sha256",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    json_payload = {
        "package": audit["package"],
        "summary": audit["summary"],
        "errors": audit["errors"],
    }
    json_path.write_text(json.dumps(json_payload, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(make_markdown_summary(json_payload), encoding="utf-8-sig")
    return {"csv": str(csv_path), "json": str(json_path), "markdown": str(md_path)}


def make_markdown_summary(payload: dict[str, object]) -> str:
    summary = payload["summary"]
    errors = payload["errors"]
    if not isinstance(summary, dict) or not isinstance(errors, list):
        raise TypeError("Invalid audit payload")
    status = "PASS" if summary.get("all_entries_ok") else "FAIL"
    lines = [
        "# Score-Audio Correspondence Audit",
        "",
        f"Status: {status}",
        "",
        "This audit checks that each anonymized score ID has matching PDF, MusicXML, MIDI, WAV, and MP3 files.",
        "It also parses each MusicXML file and verifies that four score parts are present and non-empty before playback files are accepted.",
        "",
        "## Summary",
        "",
        f"- Entry count: {summary.get('entry_count')}",
        f"- Group counts: {summary.get('group_counts')}",
        f"- Same-stem file mapping: {summary.get('all_same_stem')}",
        f"- Four SATB parts in every MusicXML: {summary.get('all_entries_have_four_parts')}",
        f"- All four parts contain notes: {summary.get('all_four_parts_have_notes')}",
        f"- MIDI files parse as note events: {summary.get('all_midi_parseable')}",
        f"- Playback backend provenance is current: {summary.get('all_playback_backends_current')}",
        f"- WAV files are non-silent: {summary.get('all_wav_non_silent')}",
        f"- Error count: {summary.get('error_count')}",
        "",
        "Use `SCORE_AUDIO_CORRESPONDENCE.csv` for the full per-score mapping and SHA256 hashes.",
    ]
    if errors:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {error}" for error in errors)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify PDF/MusicXML/MIDI/WAV/MP3 correspondence in an expert package.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    audit = audit_package(args.package_dir)
    if args.write:
        outputs = write_audit_outputs(args.package_dir, audit)
        print(json.dumps({"summary": audit["summary"], "outputs": outputs}, indent=2, ensure_ascii=False))
    else:
        print(json.dumps({"summary": audit["summary"], "errors": audit["errors"]}, indent=2, ensure_ascii=False))
    if not audit["summary"]["all_entries_ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
