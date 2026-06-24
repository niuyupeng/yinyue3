from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from music21 import converter


@dataclass(frozen=True)
class MediaAuditConfig:
    min_mp3_size_bytes: int = 8192
    max_duration_delta_sec: float = 0.85
    min_bit_rate: int = 96000


def audit_delivery_media(package_dir: str | Path, config: MediaAuditConfig | None = None) -> dict[str, object]:
    config = config or MediaAuditConfig()
    package = Path(package_dir)
    manifest_path = package / "audio_pro" / "pro_playback_manifest.csv"
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Playback manifest not found: {manifest_path}")
    rows = read_manifest(manifest_path)
    ffprobe = find_ffprobe()
    audited_rows = [audit_row(package, row, config, ffprobe) for row in rows]
    failures = [row for row in audited_rows if row["status"] != "pass"]
    ffprobe_missing = ffprobe is None
    summary = {
        "schema": "project1_delivery_media_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_dir": str(package),
        "ffprobe": str(ffprobe) if ffprobe else "",
        "media_delivery_score": 100 if not failures and len(audited_rows) == 240 else max(0, round(100 * (1.0 - len(failures) / max(len(audited_rows), 1)))),
        "all_pass": not failures and len(audited_rows) == 240 and not ffprobe_missing,
        "entry_count": len(audited_rows),
        "pass_count": len(audited_rows) - len(failures),
        "fail_count": len(failures),
        "ffprobe_missing": ffprobe_missing,
        "mp3_parse_ok_count": sum(1 for row in audited_rows if row["mp3_probe_status"] == "ok"),
        "midi_parse_ok_count": sum(1 for row in audited_rows if row["midi_parse_status"] == "ok"),
        "max_abs_duration_delta_sec": max(
            [float(row["duration_delta_sec"]) for row in audited_rows if row["duration_delta_sec"] not in ("", None)]
            or [0.0]
        ),
        "failure_examples": failures[:10],
    }
    return {"summary": summary, "rows": audited_rows}


def audit_row(
    package: Path,
    row: dict[str, str],
    config: MediaAuditConfig,
    ffprobe: Path | None,
) -> dict[str, str]:
    issues: list[str] = []
    mp3_path = package / row.get("mp3", "")
    midi_path = package / row.get("midi", "")
    manifest_duration = parse_float(row.get("duration_sec", ""))

    mp3_status = "missing"
    mp3_duration = ""
    mp3_bit_rate = ""
    mp3_codec = ""
    if not mp3_path.is_file():
        issues.append(f"missing MP3: {safe_rel(mp3_path, package)}")
    elif mp3_path.stat().st_size < config.min_mp3_size_bytes:
        issues.append(f"MP3 too small: {mp3_path.stat().st_size} bytes")
    elif ffprobe is None:
        issues.append("ffprobe not found; MP3 parseability not verified")
    else:
        probe = probe_mp3(ffprobe, mp3_path)
        mp3_status = probe.get("status", "failed")
        if mp3_status != "ok":
            issues.append(str(probe.get("message", "MP3 ffprobe failed")))
        else:
            mp3_duration = f"{float(probe.get('duration_sec', 0.0)):.3f}"
            mp3_bit_rate = str(int(float(probe.get("bit_rate", 0) or 0)))
            mp3_codec = str(probe.get("codec_name", ""))
            if mp3_codec.lower() != "mp3":
                issues.append(f"unexpected MP3 codec: {mp3_codec}")
            if int(mp3_bit_rate or "0") < config.min_bit_rate:
                issues.append(f"MP3 bit rate too low: {mp3_bit_rate}")
            if manifest_duration is not None:
                delta = abs(float(mp3_duration) - manifest_duration)
                if delta > config.max_duration_delta_sec:
                    issues.append(f"MP3 duration differs from manifest by {delta:.3f}s")

    midi_status = "missing"
    midi_note_count = ""
    if not midi_path.is_file():
        issues.append(f"missing MIDI: {safe_rel(midi_path, package)}")
    else:
        midi_result = parse_midi(midi_path)
        midi_status = midi_result["status"]
        midi_note_count = str(midi_result["note_count"])
        if midi_status != "ok":
            issues.append(str(midi_result["message"]))

    duration_delta = ""
    if manifest_duration is not None and mp3_duration:
        duration_delta = f"{abs(float(mp3_duration) - manifest_duration):.3f}"

    return {
        "group": row.get("group", ""),
        "score_id": row.get("score_id", ""),
        "variant": row.get("variant", ""),
        "status": "pass" if not issues else "fail",
        "issues": "; ".join(issues),
        "manifest_duration_sec": row.get("duration_sec", ""),
        "mp3_duration_sec": mp3_duration,
        "duration_delta_sec": duration_delta,
        "mp3_bit_rate": mp3_bit_rate,
        "mp3_codec": mp3_codec,
        "mp3_probe_status": mp3_status,
        "midi_parse_status": midi_status,
        "midi_note_count": midi_note_count,
        "mp3": row.get("mp3", ""),
        "midi": row.get("midi", ""),
    }


def find_ffprobe() -> Path | None:
    env_path = os.environ.get("CHORALE_FFPROBE_EXE", "")
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path
    exe = shutil.which("ffprobe") or shutil.which("ffprobe.exe")
    if exe:
        path = Path(exe)
        if path.is_file():
            return path
    for candidate in Path("external_tools").glob("**/ffprobe.exe"):
        if candidate.is_file():
            return candidate
    return None


def probe_mp3(ffprobe: Path, mp3_path: Path) -> dict[str, object]:
    command = [
        str(ffprobe),
        "-v",
        "error",
        "-select_streams",
        "a:0",
        "-show_entries",
        "stream=codec_name,channels,sample_rate,duration,bit_rate",
        "-show_entries",
        "format=duration,bit_rate,size",
        "-of",
        "json",
        str(mp3_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        return {"status": "failed", "message": (completed.stderr or completed.stdout or "ffprobe failed").strip()}
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return {"status": "failed", "message": f"ffprobe JSON parse failed: {exc}"}
    streams = payload.get("streams") or []
    fmt = payload.get("format") or {}
    if not streams:
        return {"status": "failed", "message": "ffprobe found no audio stream"}
    stream = streams[0]
    duration = parse_float(stream.get("duration")) or parse_float(fmt.get("duration")) or 0.0
    bit_rate = parse_float(stream.get("bit_rate")) or parse_float(fmt.get("bit_rate")) or 0.0
    if duration <= 0:
        return {"status": "failed", "message": "ffprobe reported nonpositive duration"}
    return {
        "status": "ok",
        "duration_sec": duration,
        "bit_rate": bit_rate,
        "codec_name": stream.get("codec_name", ""),
        "channels": stream.get("channels", ""),
        "sample_rate": stream.get("sample_rate", ""),
    }


def parse_midi(path: Path) -> dict[str, object]:
    try:
        score = converter.parse(str(path))
        count = 0
        for item in score.flatten().notes:
            pitches = getattr(item, "pitches", None)
            count += len(pitches) if pitches else 1
        if count <= 0:
            return {"status": "failed", "note_count": 0, "message": "MIDI contains no parsed notes"}
        return {"status": "ok", "note_count": count, "message": ""}
    except Exception as exc:
        return {"status": "failed", "note_count": 0, "message": f"MIDI parse failed: {type(exc).__name__}: {exc}"}


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def parse_float(value: object) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_outputs(audit: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out = Path(out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = audit.get("rows", [])
    summary = audit.get("summary", {})
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    out_csv = out.with_suffix(".csv")
    if isinstance(rows, list) and rows:
        with out_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    out_md = out.with_suffix(".md")
    out_md.write_text(make_markdown(summary), encoding="utf-8")
    return {"json": str(out), "csv": str(out_csv), "markdown": str(out_md)}


def make_markdown(summary: object) -> str:
    data = summary if isinstance(summary, dict) else {}
    lines = [
        "# Project1 Delivery Media Audit",
        "",
        f"Score: {data.get('media_delivery_score')}/100",
        f"All pass: {data.get('all_pass')}",
        f"Package: `{data.get('package_dir')}`",
        f"Entries: {data.get('entry_count')}",
        f"MP3 parse OK: {data.get('mp3_parse_ok_count')}",
        f"MIDI parse OK: {data.get('midi_parse_ok_count')}",
        f"Max MP3/manifest duration delta: {data.get('max_abs_duration_delta_sec')} sec",
        "",
    ]
    failures = data.get("failure_examples", [])
    if isinstance(failures, list) and failures:
        lines.extend(["## Failure Examples", ""])
        for item in failures:
            if isinstance(item, dict):
                lines.append(f"- {item.get('group')}/{item.get('score_id')}/{item.get('variant')}: {item.get('issues')}")
    else:
        lines.append("No MP3/MIDI media-content issues detected.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit final Project1 delivery MP3/MIDI media parseability.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--out-json", default="results/project1_delivery_media_audit_latest.json")
    args = parser.parse_args()
    audit = audit_delivery_media(args.package_dir)
    outputs = write_outputs(audit, args.out_json)
    print(json.dumps({"summary": audit["summary"], "outputs": outputs}, indent=2, ensure_ascii=False))
    if not audit["summary"]["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
