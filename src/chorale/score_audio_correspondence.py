from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


REQUIRED_VARIANTS = {
    "full_choir",
    "piano_reference",
    "stem_soprano",
    "stem_alto",
    "stem_tenor",
    "stem_bass",
}
EXPECTED_ROWS = 240
HASH_FIELDS = [
    "source_musicxml_sha256",
    "render_musicxml_sha256",
    "midi_sha256",
    "mp3_sha256",
]


def prepare_mp3_delivery_correspondence(
    package_dir: str | Path,
    source_manifest: str | Path,
    stage_manifest: str | Path,
) -> dict[str, object]:
    """Write the MP3-only playback manifest and top-level score-audio correspondence files."""
    package = Path(package_dir)
    rows, fieldnames = read_manifest(source_manifest)
    rows = normalize_rows_for_mp3_delivery(rows)
    write_manifest(stage_manifest, rows, fieldnames)
    return write_score_audio_correspondence(package, rows, fieldnames)


def normalize_rows_for_mp3_delivery(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    normalized: list[dict[str, str]] = []
    for row in rows:
        item = dict(row)
        item["wav"] = ""
        item["message"] = (item.get("message") or "").strip()
        normalized.append(item)
    return normalized


def read_manifest(path: str | Path) -> tuple[list[dict[str, str]], list[str]]:
    with Path(path).open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        return list(reader), list(reader.fieldnames or [])


def write_manifest(path: str | Path, rows: list[dict[str, str]], fieldnames: list[str]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_score_audio_correspondence(
    package_dir: str | Path,
    rows: list[dict[str, str]],
    manifest_fieldnames: list[str],
) -> dict[str, object]:
    package = Path(package_dir)
    fields = list(manifest_fieldnames)
    for field in HASH_FIELDS:
        if field not in fields:
            fields.append(field)

    correspondence_rows = []
    for row in rows:
        item = dict(row)
        item["source_musicxml_sha256"] = sha256_for_relative(package, row.get("source_musicxml", ""))
        item["render_musicxml_sha256"] = sha256_for_relative(package, row.get("render_musicxml", ""))
        item["midi_sha256"] = sha256_for_relative(package, row.get("midi", ""))
        item["mp3_sha256"] = sha256_for_relative(package, row.get("mp3", ""))
        correspondence_rows.append(item)

    csv_path = package / "SCORE_AUDIO_CORRESPONDENCE.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(correspondence_rows)

    summary = build_summary(package, rows)
    summary_path = package / "SCORE_AUDIO_CORRESPONDENCE_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    readme_path = package / "SCORE_AUDIO_CORRESPONDENCE_README.md"
    readme_path.write_text(make_readme(summary), encoding="utf-8-sig")
    return {
        "summary": summary,
        "outputs": {
            "csv": str(csv_path),
            "json": str(summary_path),
            "markdown": str(readme_path),
        },
    }


def build_summary(package: Path, rows: list[dict[str, str]]) -> dict[str, object]:
    group_counts = Counter(row.get("group", "") for row in rows)
    variants_by_score: dict[tuple[str, str], set[str]] = defaultdict(set)
    missing_refs: list[str] = []
    bad_statuses: list[str] = []

    for row in rows:
        group = row.get("group", "")
        score_id = row.get("score_id", "")
        variant = row.get("variant", "")
        variants_by_score[(group, score_id)].add(variant)
        if row.get("status") != "ok":
            bad_statuses.append(f"{group}/{score_id}/{variant}: status={row.get('status')!r}")
        for key in ["source_musicxml", "render_musicxml", "midi", "mp3"]:
            rel = str(row.get(key, "")).replace("\\", "/")
            if not rel:
                missing_refs.append(f"{group}/{score_id}/{variant}: empty {key}")
            elif not (package / rel).is_file():
                missing_refs.append(f"{group}/{score_id}/{variant}: missing {key} -> {rel}")
        wav_rel = str(row.get("wav", "")).replace("\\", "/")
        if wav_rel and not (package / wav_rel).is_file():
            missing_refs.append(f"{group}/{score_id}/{variant}: missing wav -> {wav_rel}")

    variant_errors = []
    for (group, score_id), variants in sorted(variants_by_score.items()):
        missing = REQUIRED_VARIANTS - variants
        extra = variants - REQUIRED_VARIANTS
        if missing:
            variant_errors.append(f"{group}/{score_id}: missing variants {','.join(sorted(missing))}")
        if extra:
            variant_errors.append(f"{group}/{score_id}: unexpected variants {','.join(sorted(extra))}")

    all_pass = (
        len(rows) == EXPECTED_ROWS
        and not missing_refs
        and not bad_statuses
        and not variant_errors
    )
    return {
        "schema": "project1_score_audio_correspondence_v2",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "audio_pro/pro_playback_manifest.csv",
        "entry_count": len(rows),
        "group_counts": dict(group_counts),
        "score_variant_groups": len(variants_by_score),
        "expected_variants_per_score": sorted(REQUIRED_VARIANTS),
        "status": "pass" if all_pass else "check_required",
        "all_pass": all_pass,
        "missing_reference_count": len(missing_refs),
        "bad_status_count": len(bad_statuses),
        "variant_error_count": len(variant_errors),
        "missing_reference_examples": missing_refs[:10],
        "bad_status_examples": bad_statuses[:10],
        "variant_error_examples": variant_errors[:10],
        "note": "Top-level correspondence is derived from the pro playback manifest and uses MP3-only delivery paths.",
    }


def sha256_for_relative(package: Path, rel_path: str | None) -> str:
    rel = str(rel_path or "").strip().replace("\\", "/")
    if not rel:
        return ""
    path = package / rel
    if not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def make_readme(summary: dict[str, object]) -> str:
    return (
        "# Score-Audio Correspondence\n\n"
        "This file maps each anonymized SATB score to its source MusicXML, rendered MusicXML, MIDI, and MP3 playback files.\n"
        "The MP3 delivery package contains six playback variants per score: full choir, piano reference, and four voice stems.\n\n"
        f"- Entry count: {summary.get('entry_count')}\n"
        f"- Group counts: {summary.get('group_counts')}\n"
        f"- Score/variant groups: {summary.get('score_variant_groups')}\n"
        f"- Status: {summary.get('status')}\n"
        "- WAV references are intentionally blank in the MP3-only delivery package.\n"
        "- Use `SCORE_AUDIO_CORRESPONDENCE.csv` for path-level and SHA256-level checking.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Project1 score-audio correspondence files.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--stage-manifest", required=True)
    args = parser.parse_args()
    report = prepare_mp3_delivery_correspondence(args.package_dir, args.source_manifest, args.stage_manifest)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if not report["summary"]["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
