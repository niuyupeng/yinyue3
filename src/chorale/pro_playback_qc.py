from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
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
STEM_TO_INDEX = {
    "stem_soprano": 0,
    "stem_alto": 1,
    "stem_tenor": 2,
    "stem_bass": 3,
}


@dataclass
class QcConfig:
    target_peak: int = 28834
    peak_tolerance: int = 4
    min_rms: float = 250.0
    max_duration_spread_sec: float = 1.5
    max_quarter_length_delta: float = 0.01


def run_qc(package_dir: str | Path, config: QcConfig | None = None) -> dict[str, object]:
    config = config or QcConfig()
    package = Path(package_dir)
    manifest_path = package / "audio_pro" / "pro_playback_manifest.csv"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Pro playback manifest not found: {manifest_path}")

    rows = read_manifest(manifest_path)
    source_cache: dict[str, dict[str, object]] = {}
    render_cache: dict[str, dict[str, object]] = {}
    qc_rows: list[dict[str, str]] = []

    for row in rows:
        issues: list[str] = []
        source_path = package / row["source_musicxml"]
        render_path = package / row["render_musicxml"]
        wav_path = package / row["wav"]
        mp3_path = package / row["mp3"]
        midi_path = package / row["midi"]

        for label, path in [("source_musicxml", source_path), ("render_musicxml", render_path), ("midi", midi_path), ("wav", wav_path), ("mp3", mp3_path)]:
            if not path.is_file():
                issues.append(f"missing {label}")

        source_info = score_info(source_path, source_cache) if source_path.is_file() else {}
        render_info = score_info(render_path, render_cache) if render_path.is_file() else {}
        source_ql = float(source_info.get("highest_time", -1.0))
        render_ql = float(render_info.get("highest_time", -2.0))
        if source_ql >= 0 and abs(source_ql - render_ql) > config.max_quarter_length_delta:
            issues.append(f"render MusicXML duration differs from source: {render_ql:.3f} vs {source_ql:.3f}")

        part_offsets = render_info.get("part_offsets", [])
        if isinstance(part_offsets, list) and any(abs(float(value)) > 1e-6 for value in part_offsets):
            issues.append(f"render MusicXML has nonzero part offsets: {part_offsets}")

        note_counts = render_info.get("part_note_counts", [])
        if row["variant"] in STEM_TO_INDEX and isinstance(note_counts, list):
            target = STEM_TO_INDEX[row["variant"]]
            for idx, count in enumerate(note_counts):
                if idx == target and int(count) <= 0:
                    issues.append(f"target stem voice {target} has no notes")
                if idx != target and int(count) != 0:
                    issues.append(f"muted stem voice {idx} still has {count} notes")
        elif row["variant"] in {"full_choir", "piano_reference"} and isinstance(note_counts, list):
            if len(note_counts) != 4:
                issues.append(f"full-score variant has {len(note_counts)} parts, expected 4")
            if any(int(count) <= 0 for count in note_counts):
                issues.append(f"full-score variant has empty part notes: {note_counts}")

        wav_validation = validate_wav_file(wav_path) if wav_path.is_file() else None
        if wav_validation is None or not wav_validation.ok:
            issues.append("WAV validation failed")
        else:
            if wav_validation.rms < config.min_rms:
                issues.append(f"WAV RMS too low: {wav_validation.rms:.3f}")
            if abs(wav_validation.peak - config.target_peak) > config.peak_tolerance:
                issues.append(f"WAV peak not normalized: {wav_validation.peak}")

        if mp3_path.is_file() and mp3_path.stat().st_size < 8192:
            issues.append(f"MP3 too small: {mp3_path.stat().st_size}")

        qc_rows.append(
            {
                "group": row["group"],
                "score_id": row["score_id"],
                "variant": row["variant"],
                "status": "pass" if not issues else "fail",
                "issues": "; ".join(issues),
                "duration_sec": f"{wav_validation.duration_sec:.3f}" if wav_validation else "",
                "rms": f"{wav_validation.rms:.3f}" if wav_validation else "",
                "peak": str(wav_validation.peak) if wav_validation else "",
                "source_quarter_length": f"{source_ql:.3f}" if source_ql >= 0 else "",
                "render_quarter_length": f"{render_ql:.3f}" if render_ql >= 0 else "",
                "render_part_note_counts": "|".join(str(value) for value in note_counts) if isinstance(note_counts, list) else "",
                "source_musicxml_sha256": sha256_file(source_path) if source_path.is_file() else "",
                "render_musicxml_sha256": sha256_file(render_path) if render_path.is_file() else "",
                "midi_sha256": sha256_file(midi_path) if midi_path.is_file() else "",
                "mp3_sha256": sha256_file(mp3_path) if mp3_path.is_file() else "",
            }
        )

    add_group_level_checks(qc_rows, config)
    summary = summarize(qc_rows)
    write_outputs(package, qc_rows, summary)
    return summary


def add_group_level_checks(qc_rows: list[dict[str, str]], config: QcConfig) -> None:
    groups: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in qc_rows:
        groups[(row["group"], row["score_id"])].append(row)

    for (group, score_id), rows in groups.items():
        variants = {row["variant"] for row in rows}
        missing = sorted(REQUIRED_VARIANTS - variants)
        durations = [float(row["duration_sec"]) for row in rows if row["duration_sec"]]
        spread = max(durations) - min(durations) if durations else 999.0
        shared_issues: list[str] = []
        if missing:
            shared_issues.append(f"missing variants: {','.join(missing)}")
        if spread > config.max_duration_spread_sec:
            shared_issues.append(f"variant duration spread too large: {spread:.3f}s")
        if not shared_issues:
            continue
        for row in rows:
            issues = [row["issues"]] if row["issues"] else []
            issues.extend(shared_issues)
            row["issues"] = "; ".join(issue for issue in issues if issue)
            row["status"] = "fail"


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def score_info(path: Path, cache: dict[str, dict[str, object]]) -> dict[str, object]:
    key = str(path.resolve())
    if key in cache:
        return cache[key]
    score = converter.parse(str(path))
    parts = list(score.parts)
    info = {
        "highest_time": float(score.highestTime),
        "part_count": len(parts),
        "part_note_counts": [len(part.flatten().notes) for part in parts],
        "part_offsets": [float(part.offset) for part in parts],
    }
    cache[key] = info
    return info


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def summarize(rows: list[dict[str, str]]) -> dict[str, object]:
    by_variant: dict[str, dict[str, int]] = {}
    by_group: dict[str, dict[str, int]] = {}
    failures = [row for row in rows if row["status"] != "pass"]
    for row in rows:
        for bucket, key in [(by_variant, row["variant"]), (by_group, row["group"])]:
            bucket.setdefault(key, {"pass": 0, "fail": 0})
            bucket[key][row["status"]] = bucket[key].get(row["status"], 0) + 1
    score = 100 if not failures and len(rows) == 240 else max(0, round(100 * (1.0 - len(failures) / max(len(rows), 1))))
    return {
        "qc_score": score,
        "entry_count": len(rows),
        "pass_count": len(rows) - len(failures),
        "fail_count": len(failures),
        "all_pass": not failures,
        "by_variant": by_variant,
        "by_group": by_group,
        "failure_examples": failures[:10],
    }


def write_outputs(package: Path, rows: list[dict[str, str]], summary: dict[str, object]) -> None:
    out_dir = package / "audio_pro"
    csv_path = out_dir / "commercial_qc_report.csv"
    json_path = out_dir / "commercial_qc_summary.json"
    md_path = out_dir / "COMMERCIAL_QC_REPORT.md"
    fieldnames = [
        "group",
        "score_id",
        "variant",
        "status",
        "issues",
        "duration_sec",
        "rms",
        "peak",
        "source_quarter_length",
        "render_quarter_length",
        "render_part_note_counts",
        "source_musicxml_sha256",
        "render_musicxml_sha256",
        "midi_sha256",
        "mp3_sha256",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    json_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(make_markdown(summary), encoding="utf-8")


def make_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Commercial Playback QC Report",
        "",
        f"QC score: {summary['qc_score']}/100",
        f"All pass: {summary['all_pass']}",
        f"Entries: {summary['entry_count']}",
        f"Passed: {summary['pass_count']}",
        f"Failed: {summary['fail_count']}",
        "",
        "## Variant Coverage",
        "",
    ]
    by_variant = summary.get("by_variant", {})
    if isinstance(by_variant, dict):
        for variant, counts in sorted(by_variant.items()):
            lines.append(f"- {variant}: {counts}")
    failures = summary.get("failure_examples", [])
    if failures:
        lines.extend(["", "## Failure Examples", ""])
        for item in failures:
            if isinstance(item, dict):
                lines.append(f"- {item.get('group')}/{item.get('score_id')}/{item.get('variant')}: {item.get('issues')}")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run strict commercial QC on pro playback assets.")
    parser.add_argument("--package-dir", required=True)
    args = parser.parse_args()
    print(json.dumps(run_qc(args.package_dir), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
