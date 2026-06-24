from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from music21 import converter

from chorale.playback_render import validate_wav_file


REQUIRED_VARIANTS = {
    "full_choir",
    "piano_reference",
    "stem_soprano",
    "stem_alto",
    "stem_tenor",
    "stem_bass",
}
VOICE_INDEX = {
    "stem_soprano": 0,
    "stem_alto": 1,
    "stem_tenor": 2,
    "stem_bass": 3,
}


@dataclass(frozen=True)
class ScoreStats:
    part_counts: tuple[int, ...]
    highest_time: float

    @property
    def total_notes(self) -> int:
        return sum(self.part_counts)


def audit_pro_playback_package(package_dir: str | Path, *, mode: str = "master") -> dict[str, object]:
    package = Path(package_dir)
    if mode not in {"master", "mp3_only"}:
        raise ValueError("mode must be 'master' or 'mp3_only'.")
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")

    manifest_path = package / "audio_pro" / "pro_playback_manifest.csv"
    issues: list[str] = []
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Pro playback manifest not found: {manifest_path}")

    rows = read_manifest(manifest_path)
    source_cache: dict[Path, ScoreStats] = {}
    render_cache: dict[Path, ScoreStats] = {}
    audited_rows = [
        audit_manifest_row(package, row, mode=mode, source_cache=source_cache, render_cache=render_cache)
        for row in rows
    ]
    for row in audited_rows:
        if row["entry_ok"] != "yes":
            issues.append(f"{row['group']}/{row['score_id']}/{row['variant']}: {row['issues']}")

    expected_score_variants = summarize_score_variants(audited_rows)
    for key, variants in expected_score_variants.items():
        missing = REQUIRED_VARIANTS - variants
        if missing:
            issues.append(f"{key} missing variants: {','.join(sorted(missing))}")

    summary = summarize(audited_rows, issues, mode)
    return {
        "package": str(package),
        "mode": mode,
        "score_audio_traceability_score": 100 if summary["all_pass"] else max(0, 100 - 5 * len(issues)),
        "all_pass": summary["all_pass"],
        "summary": summary,
        "rows": audited_rows,
        "issues": issues,
    }


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def audit_manifest_row(
    package: Path,
    row: dict[str, str],
    *,
    mode: str,
    source_cache: dict[Path, ScoreStats],
    render_cache: dict[Path, ScoreStats],
) -> dict[str, str]:
    issues: list[str] = []
    group = row.get("group", "")
    score_id = row.get("score_id", "")
    variant = row.get("variant", "")

    source_path = package / row.get("source_musicxml", "")
    render_path = package / row.get("render_musicxml", "")
    midi_path = package / row.get("midi", "")
    wav_path = package / row.get("wav", "")
    mp3_path = package / row.get("mp3", "")

    for label, path in [("source_musicxml", source_path), ("render_musicxml", render_path), ("midi", midi_path), ("mp3", mp3_path)]:
        if not path.is_file():
            issues.append(f"missing {label}: {safe_rel(path, package)}")
    if mode == "master" and not wav_path.is_file():
        issues.append(f"missing wav: {safe_rel(wav_path, package)}")
    if row.get("status") != "ok":
        issues.append(f"manifest status is {row.get('status')!r}, expected 'ok'")
    if variant not in REQUIRED_VARIANTS:
        issues.append(f"unexpected variant: {variant}")
    if not expected_variant_stem(score_id, variant, render_path, midi_path, mp3_path):
        issues.append("file stems do not match score_id and variant")

    source_stats = get_score_stats(source_path, source_cache, issues, "source") if source_path.is_file() else None
    render_stats = get_score_stats(render_path, render_cache, issues, "render") if render_path.is_file() else None
    if source_stats and render_stats:
        validate_render_matches_source(source_stats, render_stats, variant, issues)

    midi_note_count = parse_midi_note_count(midi_path, issues) if midi_path.is_file() else 0
    if render_stats and midi_path.is_file():
        validate_midi_contains_rendered_notes(render_stats, midi_note_count, variant, issues)

    wav_duration = ""
    wav_rms = ""
    wav_peak = ""
    if mode == "master" and wav_path.is_file():
        validation = validate_wav_file(wav_path)
        wav_duration = f"{validation.duration_sec:.3f}"
        wav_rms = f"{validation.rms:.3f}"
        wav_peak = str(validation.peak)
        if not validation.ok:
            issues.append(f"WAV validation failed: {validation.message}")

    if mp3_path.is_file() and mp3_path.stat().st_size < 2048:
        issues.append(f"MP3 too small: {mp3_path.stat().st_size} bytes")

    manifest_duration = row.get("duration_sec", "")
    if manifest_duration and wav_duration and abs(float(manifest_duration) - float(wav_duration)) > 0.75:
        issues.append(f"manifest duration {manifest_duration}s differs from WAV duration {wav_duration}s")

    out = {
        "group": group,
        "score_id": score_id,
        "variant": variant,
        "entry_ok": "yes" if not issues else "no",
        "issues": "; ".join(issues),
        "source_musicxml": row.get("source_musicxml", ""),
        "render_musicxml": row.get("render_musicxml", ""),
        "midi": row.get("midi", ""),
        "wav": row.get("wav", ""),
        "mp3": row.get("mp3", ""),
        "source_part_note_counts": serialize_counts(source_stats.part_counts) if source_stats else "",
        "render_part_note_counts": serialize_counts(render_stats.part_counts) if render_stats else "",
        "source_duration_quarter_length": f"{source_stats.highest_time:.3f}" if source_stats else "",
        "render_duration_quarter_length": f"{render_stats.highest_time:.3f}" if render_stats else "",
        "midi_note_count": str(midi_note_count) if midi_path.is_file() else "",
        "manifest_duration_sec": manifest_duration,
        "wav_duration_sec": wav_duration,
        "wav_rms": wav_rms,
        "wav_peak": wav_peak,
        "source_sha256": sha256_file(source_path) if source_path.is_file() else "",
        "render_sha256": sha256_file(render_path) if render_path.is_file() else "",
        "midi_sha256": sha256_file(midi_path) if midi_path.is_file() else "",
        "wav_sha256": sha256_file(wav_path) if wav_path.is_file() else "",
        "mp3_sha256": sha256_file(mp3_path) if mp3_path.is_file() else "",
    }
    return out


def get_score_stats(path: Path, cache: dict[Path, ScoreStats], issues: list[str], label: str) -> ScoreStats | None:
    if path in cache:
        return cache[path]
    try:
        score = converter.parse(str(path))
        part_counts = tuple(count_note_events(part) for part in score.parts)
        stats = ScoreStats(part_counts=part_counts, highest_time=float(score.highestTime))
        cache[path] = stats
        return stats
    except Exception as exc:
        issues.append(f"{label} MusicXML parse failed: {type(exc).__name__}: {exc}")
        return None


def count_note_events(part) -> int:
    count = 0
    for item in part.flatten().notes:
        pitches = getattr(item, "pitches", None)
        count += len(pitches) if pitches else 1
    return count


def validate_render_matches_source(source: ScoreStats, render: ScoreStats, variant: str, issues: list[str]) -> None:
    if len(source.part_counts) != 4:
        issues.append(f"source score has {len(source.part_counts)} parts, expected 4")
    if len(render.part_counts) != 4:
        issues.append(f"render score has {len(render.part_counts)} parts, expected 4")
    if abs(source.highest_time - render.highest_time) > 0.05:
        issues.append(
            f"render duration {render.highest_time:.3f} differs from source duration {source.highest_time:.3f}"
        )
    if variant in {"full_choir", "piano_reference"}:
        if render.part_counts != source.part_counts:
            issues.append(f"{variant} note counts {render.part_counts} do not match source {source.part_counts}")
        return
    if variant in VOICE_INDEX and len(source.part_counts) == 4 and len(render.part_counts) == 4:
        target = VOICE_INDEX[variant]
        for idx, (source_count, render_count) in enumerate(zip(source.part_counts, render.part_counts)):
            if idx == target and render_count != source_count:
                issues.append(f"{variant} target part count {render_count} does not match source {source_count}")
            if idx != target and render_count != 0:
                issues.append(f"{variant} muted part {idx} contains {render_count} notes")


def parse_midi_note_count(path: Path, issues: list[str]) -> int:
    try:
        midi_score = converter.parse(str(path))
        return count_note_events(midi_score)
    except Exception as exc:
        issues.append(f"MIDI parse failed: {type(exc).__name__}: {exc}")
        return 0


def validate_midi_contains_rendered_notes(render: ScoreStats, midi_note_count: int, variant: str, issues: list[str]) -> None:
    expected = render.total_notes
    if expected <= 0:
        issues.append(f"{variant} render MusicXML contains no notes")
        return
    if midi_note_count <= 0:
        issues.append(f"{variant} MIDI contains no parsed notes")
        return
    minimum = max(1, int(expected * 0.70))
    maximum = max(expected * 3, expected + 12)
    if midi_note_count < minimum or midi_note_count > maximum:
        issues.append(f"{variant} MIDI note count {midi_note_count} is inconsistent with rendered note count {expected}")


def summarize_score_variants(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    by_score: dict[str, set[str]] = {}
    for row in rows:
        key = f"{row['group']}/{row['score_id']}"
        by_score.setdefault(key, set()).add(row["variant"])
    return by_score


def summarize(rows: list[dict[str, str]], issues: list[str], mode: str) -> dict[str, object]:
    by_group: dict[str, int] = {}
    by_variant: dict[str, int] = {}
    score_ids: set[tuple[str, str]] = set()
    for row in rows:
        by_group[row["group"]] = by_group.get(row["group"], 0) + 1
        by_variant[row["variant"]] = by_variant.get(row["variant"], 0) + 1
        score_ids.add((row["group"], row["score_id"]))
    return {
        "mode": mode,
        "entry_count": len(rows),
        "score_count": len(score_ids),
        "ok_count": sum(1 for row in rows if row["entry_ok"] == "yes"),
        "fail_count": sum(1 for row in rows if row["entry_ok"] != "yes"),
        "all_pass": not issues and all(row["entry_ok"] == "yes" for row in rows),
        "issue_count": len(issues),
        "by_group": by_group,
        "by_variant": by_variant,
    }


def expected_variant_stem(score_id: str, variant: str, *paths: Path) -> bool:
    expected = f"{score_id}_{variant}"
    return all(path.stem == expected for path in paths if str(path))


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def serialize_counts(counts: tuple[int, ...]) -> str:
    return "|".join(str(value) for value in counts)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_outputs(audit: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    rows = audit.get("rows", [])
    compact = {key: value for key, value in audit.items() if key != "rows"}
    out_json.write_text(json.dumps(compact, indent=2, ensure_ascii=False), encoding="utf-8")

    out_csv = out_json.with_suffix(".csv")
    if isinstance(rows, list) and rows:
        with out_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(compact), encoding="utf-8")
    return {"json": str(out_json), "csv": str(out_csv), "markdown": str(out_md)}


def make_markdown(audit: dict[str, object]) -> str:
    summary = audit.get("summary", {})
    issues = audit.get("issues", [])
    lines = [
        "# Pro Playback Score-Audio Traceability Audit",
        "",
        f"Score: {audit.get('score_audio_traceability_score')}/100",
        f"All pass: {audit.get('all_pass')}",
        f"Package: `{audit.get('package')}`",
        "",
        "## Summary",
        "",
    ]
    if isinstance(summary, dict):
        for key in ["mode", "entry_count", "score_count", "ok_count", "fail_count", "issue_count", "by_group", "by_variant"]:
            lines.append(f"- {key}: {summary.get(key)}")
    if isinstance(issues, list) and issues:
        lines.extend(["", "## Issues", ""])
        lines.extend(f"- {issue}" for issue in issues[:200])
    else:
        lines.extend(["", "No score-audio traceability issues detected."])
    lines.append("")
    lines.append(
        "This audit verifies file mapping, MusicXML part-note correspondence, stem muting, MIDI parseability, WAV non-silence, and SHA256 provenance. It does not replace human musical evaluation."
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit pro playback MusicXML/MIDI/MP3/WAV traceability.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--mode", choices=["master", "mp3_only"], default="master")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()

    audit = audit_pro_playback_package(args.package_dir, mode=args.mode)
    if args.out_json:
        write_outputs(audit, args.out_json)
    print(json.dumps({key: value for key, value in audit.items() if key != "rows"}, indent=2, ensure_ascii=False))
    if not audit["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
