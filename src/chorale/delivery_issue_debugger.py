from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from music21 import chord, converter, note, stream


def debug_delivery_item(
    package_dir: str | Path,
    score_id: str,
    variant: str,
    *,
    time_sec: float | None = None,
    window_quarter: float = 1.0,
) -> dict[str, object]:
    package = Path(package_dir)
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")
    manifest_rows = read_csv(package / "audio_pro" / "pro_playback_manifest.csv")
    matches = [
        row
        for row in manifest_rows
        if row.get("score_id", "").lower() == score_id.lower()
        and row.get("variant", "").lower() == variant.lower()
    ]
    if not matches:
        available = sorted({f"{row.get('score_id')}:{row.get('variant')}" for row in manifest_rows})
        return {
            "schema": "project1_delivery_item_debug_v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "package_dir": str(package),
            "score_id": score_id,
            "variant": variant,
            "status": "not_found",
            "message": "No matching score_id and variant in audio_pro/pro_playback_manifest.csv",
            "available_examples": available[:20],
        }
    row = matches[0]
    media_row = find_audit_row(package / "DELIVERY_MEDIA_AUDIT.csv", score_id, variant)
    conformance_row = find_audit_row(package / "DELIVERY_CONFORMANCE_AUDIT.csv", score_id, variant)
    paths = {
        key: normalize_rel(row.get(key, ""))
        for key in ["source_musicxml", "render_musicxml", "midi", "mp3"]
    }
    path_status = {
        key: {
            "path": rel_path,
            "exists": bool(rel_path) and (package / rel_path).is_file(),
            "size_bytes": (package / rel_path).stat().st_size if bool(rel_path) and (package / rel_path).is_file() else 0,
        }
        for key, rel_path in paths.items()
    }
    issues = []
    for label, info in path_status.items():
        if not info["exists"]:
            issues.append(f"missing {label}: {info['path']}")
    if media_row and media_row.get("status") != "pass":
        issues.append(f"media audit: {media_row.get('issues', '')}")
    if conformance_row and conformance_row.get("status") != "pass":
        issues.append(f"conformance audit: {conformance_row.get('issues', '')}")

    report = {
        "schema": "project1_delivery_item_debug_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_dir": str(package),
        "score_id": row.get("score_id", score_id),
        "variant": row.get("variant", variant),
        "status": "pass" if not issues else "needs_attention",
        "issues": issues,
        "manifest_row": row,
        "path_status": path_status,
        "media_audit": media_row or {},
        "conformance_audit": conformance_row or {},
        "recommended_manual_check": (
            "Open score_audio_player.html, search the score_id, play the requested variant, "
            "and compare it with the listed source/render MusicXML files."
        ),
    }
    if time_sec is not None:
        report["timepoint_diagnostic"] = build_timepoint_diagnostic(
            package,
            row,
            media_row or {},
            conformance_row or {},
            time_sec,
            window_quarter,
        )
    return report


def build_timepoint_diagnostic(
    package: Path,
    manifest_row: dict[str, str],
    media_row: dict[str, str],
    conformance_row: dict[str, str],
    time_sec: float,
    window_quarter: float,
) -> dict[str, object]:
    source_rel = normalize_rel(manifest_row.get("source_musicxml", ""))
    render_rel = normalize_rel(manifest_row.get("render_musicxml", ""))
    source_path = package / source_rel
    render_path = package / render_rel
    issues: list[str] = []
    audio_duration = first_float(
        manifest_row.get("duration_sec"),
        media_row.get("mp3_duration_sec"),
        media_row.get("manifest_duration_sec"),
    )
    render_duration = first_float(conformance_row.get("render_duration_quarter_length"))
    source_duration = first_float(conformance_row.get("source_duration_quarter_length"))

    render_score = parse_score(render_path, issues, "render_musicxml")
    source_score = parse_score(source_path, issues, "source_musicxml")
    if render_duration <= 0 and render_score is not None:
        render_duration = float(render_score.highestTime or 0.0)
    if source_duration <= 0 and source_score is not None:
        source_duration = float(source_score.highestTime or 0.0)

    if audio_duration <= 0 or render_duration <= 0:
        issues.append("cannot map audio time to score offset because duration metadata is unavailable")
        estimated_offset = 0.0
    else:
        clamped_time = min(max(float(time_sec), 0.0), audio_duration)
        estimated_offset = clamped_time / audio_duration * render_duration
        if clamped_time != float(time_sec):
            issues.append(f"time_sec {time_sec} is outside audio duration and was clamped to {clamped_time:.3f}")

    measure_info = locate_measure_beat(render_score, estimated_offset) if render_score is not None else {}
    return {
        "time_sec": round(float(time_sec), 3),
        "audio_duration_sec": round(audio_duration, 3) if audio_duration else 0.0,
        "render_duration_quarter_length": round(render_duration, 3) if render_duration else 0.0,
        "source_duration_quarter_length": round(source_duration, 3) if source_duration else 0.0,
        "estimated_quarter_offset": round(estimated_offset, 3),
        "estimated_measure": measure_info.get("measure_number"),
        "estimated_beat": measure_info.get("beat"),
        "measure_start_quarter": measure_info.get("measure_start_quarter"),
        "measure_relative_offset_quarter": measure_info.get("measure_relative_offset_quarter"),
        "measure_duration_quarter": measure_info.get("measure_duration_quarter"),
        "time_signature": measure_info.get("time_signature"),
        "window_quarter": round(float(window_quarter), 3),
        "render_notes_near_time": collect_nearby_events(render_score, estimated_offset, window_quarter)
        if render_score is not None
        else [],
        "source_notes_near_time": collect_nearby_events(source_score, estimated_offset, window_quarter)
        if source_score is not None
        else [],
        "issues": issues,
        "interpretation": (
            "This is a deterministic score-time estimate based on rendered score duration and MP3 duration. "
            "It is intended for triage; final musical judgment should compare the displayed score and playback."
        ),
    }


def parse_score(path: Path, issues: list[str], label: str) -> stream.Score | None:
    if not path.is_file():
        issues.append(f"{label} missing: {path}")
        return None
    try:
        parsed = converter.parse(path)
    except Exception as exc:  # pragma: no cover - parser errors depend on input files.
        issues.append(f"{label} parse failed: {type(exc).__name__}: {exc}")
        return None
    if isinstance(parsed, stream.Score):
        return parsed
    score = stream.Score()
    score.insert(0, parsed)
    return score


def locate_measure_beat(score: stream.Score | None, offset_quarter: float) -> dict[str, object]:
    if score is None or not score.parts:
        return {}
    part = score.parts[0]
    measures = list(part.getElementsByClass(stream.Measure))
    for measure in measures:
        start = global_offset(measure, score)
        duration = float(measure.duration.quarterLength or 0.0)
        end = start + duration
        if start <= offset_quarter < end or (measure is measures[-1] and offset_quarter >= start):
            local_offset = max(0.0, offset_quarter - start)
            beat = local_offset + 1.0
            time_signature = measure.timeSignature or measure.getContextByClass("TimeSignature")
            return {
                "measure_number": measure.number,
                "beat": round(beat, 3),
                "measure_start_quarter": round(start, 3),
                "measure_relative_offset_quarter": round(local_offset, 3),
                "measure_duration_quarter": round(duration, 3),
                "time_signature": time_signature.ratioString if time_signature else "",
            }
    return {}


def collect_nearby_events(score: stream.Score, center_quarter: float, window_quarter: float) -> list[dict[str, object]]:
    start = center_quarter - abs(float(window_quarter))
    end = center_quarter + abs(float(window_quarter))
    rows: list[dict[str, object]] = []
    parts = list(score.parts) if score.parts else [score]
    for part_index, part in enumerate(parts[:8]):
        part_name = part.partName or part.id or f"Part {part_index + 1}"
        for event in part.recurse().notesAndRests:
            event_start = global_offset(event, score)
            duration = float(event.duration.quarterLength or 0.0)
            event_end = event_start + duration
            if event_end < start or event_start > end:
                continue
            rows.append(
                {
                    "part_index": part_index,
                    "part_name": str(part_name),
                    "kind": event_kind(event),
                    "pitches": event_pitches(event),
                    "midi": event_midis(event),
                    "offset_quarter": round(event_start, 3),
                    "duration_quarter": round(duration, 3),
                }
            )
    rows.sort(key=lambda item: (float(item["offset_quarter"]), int(item["part_index"])))
    return rows[:64]


def global_offset(element: object, score: stream.Score) -> float:
    try:
        return float(element.getOffsetInHierarchy(score))  # type: ignore[attr-defined]
    except Exception:
        try:
            return float(element.offset)  # type: ignore[attr-defined]
        except Exception:
            return 0.0


def event_kind(event: object) -> str:
    if isinstance(event, note.Rest):
        return "rest"
    if isinstance(event, chord.Chord):
        return "chord"
    if isinstance(event, note.Note):
        return "note"
    return type(event).__name__


def event_pitches(event: object) -> list[str]:
    if isinstance(event, note.Rest):
        return []
    if isinstance(event, chord.Chord):
        return [pitch.nameWithOctave for pitch in event.pitches]
    if isinstance(event, note.Note):
        return [event.pitch.nameWithOctave]
    return []


def event_midis(event: object) -> list[int]:
    if isinstance(event, chord.Chord):
        return [int(pitch.midi) for pitch in event.pitches]
    if isinstance(event, note.Note):
        return [int(event.pitch.midi)]
    return []


def first_float(*values: object) -> float:
    for value in values:
        try:
            parsed = float(str(value).strip())
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0.0


def latest_package_dir(root: str | Path = ".") -> Path:
    release_path = Path(root) / "results" / "project1_delivery_release_manifest_latest.json"
    if not release_path.is_file():
        raise FileNotFoundError(f"Latest release manifest not found: {release_path}")
    release = json.loads(release_path.read_text(encoding="utf-8-sig"))
    zip_path = Path(str(release.get("zip_file", "")))
    if zip_path.suffix.lower() == ".zip":
        return zip_path.with_suffix("")
    return zip_path


def find_audit_row(path: Path, score_id: str, variant: str) -> dict[str, str] | None:
    if not path.is_file():
        return None
    for row in read_csv(path):
        if row.get("score_id", "").lower() == score_id.lower() and row.get("variant", "").lower() == variant.lower():
            return row
    return None


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def normalize_rel(value: str) -> str:
    return value.replace("\\", "/").strip()


def write_outputs(report: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out = Path(out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out.with_suffix(".md")
    out_md.write_text(make_markdown(report), encoding="utf-8")
    return {"json": str(out), "markdown": str(out_md)}


def make_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Project1 Delivery Item Debug Report",
        "",
        f"Score ID: `{report.get('score_id')}`",
        f"Variant: `{report.get('variant')}`",
        f"Status: `{report.get('status')}`",
        "",
        "## Files",
        "",
    ]
    path_status = report.get("path_status", {})
    if isinstance(path_status, dict):
        for key, info in path_status.items():
            if isinstance(info, dict):
                lines.append(f"- {key}: `{info.get('path')}` exists={info.get('exists')} size={info.get('size_bytes')}")
    issues = report.get("issues", [])
    lines.extend(["", "## Issues", ""])
    if isinstance(issues, list) and issues:
        lines.extend(f"- {item}" for item in issues)
    else:
        lines.append("No automatic item-level issues found.")
    timepoint = report.get("timepoint_diagnostic", {})
    if isinstance(timepoint, dict) and timepoint:
        lines.extend(
            [
                "",
                "## Timepoint Diagnostic",
                "",
                f"- time_sec: `{timepoint.get('time_sec')}`",
                f"- audio_duration_sec: `{timepoint.get('audio_duration_sec')}`",
                f"- estimated_quarter_offset: `{timepoint.get('estimated_quarter_offset')}`",
                f"- estimated_measure: `{timepoint.get('estimated_measure')}`",
                f"- estimated_beat: `{timepoint.get('estimated_beat')}`",
                f"- measure_relative_offset_quarter: `{timepoint.get('measure_relative_offset_quarter')}`",
                f"- measure_duration_quarter: `{timepoint.get('measure_duration_quarter')}`",
                f"- time_signature: `{timepoint.get('time_signature')}`",
                "",
                "### Rendered Notes Near Time",
                "",
            ]
        )
        append_event_rows(lines, timepoint.get("render_notes_near_time", []))
        lines.extend(["", "### Source Notes Near Time", ""])
        append_event_rows(lines, timepoint.get("source_notes_near_time", []))
        time_issues = timepoint.get("issues", [])
        if isinstance(time_issues, list) and time_issues:
            lines.extend(["", "### Timepoint Issues", ""])
            lines.extend(f"- {item}" for item in time_issues)
        lines.extend(["", str(timepoint.get("interpretation", ""))])
    lines.extend(["", "## Manual Check", "", str(report.get("recommended_manual_check", "")), ""])
    return "\n".join(lines)


def append_event_rows(lines: list[str], rows: object) -> None:
    if not isinstance(rows, list) or not rows:
        lines.append("No nearby note/rest events found.")
        return
    lines.append("| Part | Kind | Pitches | Offset | Duration |")
    lines.append("|---|---|---|---:|---:|")
    for item in rows[:24]:
        if not isinstance(item, dict):
            continue
        pitches = ", ".join(str(value) for value in item.get("pitches", []))
        lines.append(
            f"| {item.get('part_name')} | {item.get('kind')} | {pitches} | "
            f"{item.get('offset_quarter')} | {item.get('duration_quarter')} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug one Project1 delivery score/variant item.")
    parser.add_argument("--package-dir", default="")
    parser.add_argument("--score-id", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--time-sec", type=float, default=None)
    parser.add_argument("--window-quarter", type=float, default=1.0)
    parser.add_argument("--out-json", default="results/project1_delivery_item_debug_latest.json")
    args = parser.parse_args()
    package_dir = Path(args.package_dir) if args.package_dir else latest_package_dir(".")
    report = debug_delivery_item(
        package_dir,
        args.score_id,
        args.variant,
        time_sec=args.time_sec,
        window_quarter=args.window_quarter,
    )
    outputs = write_outputs(report, args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))
    if report.get("status") not in {"pass", "not_found"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
