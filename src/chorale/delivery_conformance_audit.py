from __future__ import annotations

import argparse
import array
import csv
import json
import math
import os
import shutil
import struct
import subprocess
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from music21 import converter


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
class ConformanceConfig:
    expected_entries: int = 240
    min_full_pitch_similarity: float = 0.85
    min_stem_pitch_similarity: float = 0.88
    min_stem_target_margin: float = 0.25
    min_event_recall: float = 0.98
    min_event_precision: float = 0.98
    min_duration_similarity: float = 0.95
    event_quantum_quarter: float = 0.25
    min_mp3_rms: float = 0.005
    min_mp3_peak: float = 0.02
    audio_sample_rate: int = 8000
    require_complete_variant_set: bool = True


@dataclass(frozen=True)
class ScoreSignature:
    part_pitch_sequences: tuple[tuple[int, ...], ...]
    part_event_sequences: tuple[tuple[tuple[int, float, float], ...], ...]
    highest_time: float
    event_highest_time: float

    @property
    def total_notes(self) -> int:
        return sum(len(seq) for seq in self.part_pitch_sequences)

    @property
    def flat_pitch_sequence(self) -> tuple[int, ...]:
        return tuple(pitch for seq in self.part_pitch_sequences for pitch in seq)

    @property
    def flat_events(self) -> tuple[tuple[int, float, float], ...]:
        return tuple(event for seq in self.part_event_sequences for event in seq)


def audit_delivery_conformance(package_dir: str | Path, config: ConformanceConfig | None = None) -> dict[str, object]:
    config = config or ConformanceConfig()
    package = Path(package_dir)
    manifest_path = package / "audio_pro" / "pro_playback_manifest.csv"
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Playback manifest not found: {manifest_path}")

    rows = read_manifest(manifest_path)
    ffmpeg = find_ffmpeg()
    signature_cache: dict[Path, ScoreSignature] = {}
    audited_rows = [
        audit_row(package, row, config=config, ffmpeg=ffmpeg, signature_cache=signature_cache)
        for row in rows
    ]
    failures = [row for row in audited_rows if row["status"] != "pass"]
    score_variants = summarize_variants(audited_rows)
    missing_variant_groups = (
        {
            key: sorted(REQUIRED_VARIANTS - variants)
            for key, variants in score_variants.items()
            if variants != REQUIRED_VARIANTS
        }
        if config.require_complete_variant_set
        else {}
    )
    if missing_variant_groups:
        failures.extend(
            {
                "group": key.split("/", 1)[0],
                "score_id": key.split("/", 1)[1],
                "variant": "",
                "issues": f"missing variants: {','.join(value)}",
                "status": "fail",
            }
            for key, value in missing_variant_groups.items()
        )

    summary = {
        "schema": "project1_delivery_conformance_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_dir": str(package),
        "ffmpeg": str(ffmpeg) if ffmpeg else "",
        "all_pass": not failures and len(audited_rows) == config.expected_entries and ffmpeg is not None,
        "conformance_score": 100
        if not failures and len(audited_rows) == config.expected_entries and ffmpeg is not None
        else max(0, round(100 * (1.0 - len(failures) / max(len(audited_rows), 1)))),
        "entry_count": len(audited_rows),
        "pass_count": len(audited_rows) - sum(1 for row in audited_rows if row["status"] != "pass"),
        "fail_count": len(failures),
        "ffmpeg_missing": ffmpeg is None,
        "mp3_audible_count": sum(1 for row in audited_rows if row["mp3_audio_status"] == "ok"),
        "midi_render_pitch_check_pass_count": sum(1 for row in audited_rows if row["midi_render_pitch_check"] == "pass"),
        "stem_target_check_pass_count": sum(1 for row in audited_rows if row["stem_target_check"] in {"pass", "not_applicable"}),
        "event_alignment_pass_count": sum(1 for row in audited_rows if row["event_alignment_check"] == "pass"),
        "min_pitch_similarity": min(
            [float(row["pitch_similarity"]) for row in audited_rows if row.get("pitch_similarity")]
            or [0.0]
        ),
        "min_event_recall": min([float(row["event_recall"]) for row in audited_rows if row.get("event_recall")] or [0.0]),
        "min_event_precision": min(
            [float(row["event_precision"]) for row in audited_rows if row.get("event_precision")] or [0.0]
        ),
        "min_duration_similarity": min(
            [float(row["duration_similarity"]) for row in audited_rows if row.get("duration_similarity")] or [0.0]
        ),
        "min_mp3_rms": min([float(row["mp3_rms"]) for row in audited_rows if row.get("mp3_rms")] or [0.0]),
        "failure_examples": failures[:10],
        "method_note": (
            "This audit verifies score-derived playback conformance using MusicXML/MIDI pitch signatures, "
            "event-level onset/pitch alignment, duration similarity, and MP3 signal energy. It does not "
            "perform human-level audio transcription or judge musical taste."
        ),
    }
    return {"summary": summary, "rows": audited_rows}


def audit_row(
    package: Path,
    row: dict[str, str],
    *,
    config: ConformanceConfig,
    ffmpeg: Path | None,
    signature_cache: dict[Path, ScoreSignature],
) -> dict[str, str]:
    issues: list[str] = []
    group = row.get("group", "")
    score_id = row.get("score_id", "")
    variant = row.get("variant", "")
    source_path = package / row.get("source_musicxml", "")
    render_path = package / row.get("render_musicxml", "")
    midi_path = package / row.get("midi", "")
    mp3_path = package / row.get("mp3", "")

    for label, path in [
        ("source_musicxml", source_path),
        ("render_musicxml", render_path),
        ("midi", midi_path),
        ("mp3", mp3_path),
    ]:
        if not path.is_file():
            issues.append(f"missing {label}: {safe_rel(path, package)}")
    if variant not in REQUIRED_VARIANTS:
        issues.append(f"unexpected variant: {variant}")
    if not expected_variant_stem(score_id, variant, render_path, midi_path, mp3_path):
        issues.append("file stems do not match score_id and variant")

    source_sig = get_signature(source_path, signature_cache, issues, "source") if source_path.is_file() else None
    render_sig = get_signature(render_path, signature_cache, issues, "render") if render_path.is_file() else None
    midi_sig = get_signature(midi_path, signature_cache, issues, "midi") if midi_path.is_file() else None

    render_source_check = "not_checked"
    midi_render_check = "not_checked"
    event_alignment_check = "not_checked"
    stem_target_check = "not_applicable"
    pitch_similarity = ""
    stem_margin = ""
    event_recall = ""
    event_precision = ""
    event_f1 = ""
    duration_similarity = ""

    if source_sig and render_sig:
        render_source_check = validate_render_source(source_sig, render_sig, variant, issues)
    if source_sig and render_sig and midi_sig:
        (
            midi_render_check,
            stem_target_check,
            pitch_similarity,
            stem_margin,
            event_alignment_check,
            event_recall,
            event_precision,
            event_f1,
            duration_similarity,
        ) = validate_midi_render(
            source_sig, render_sig, midi_sig, variant, config, issues
        )

    mp3_status = "not_checked"
    mp3_rms = ""
    mp3_peak = ""
    mp3_samples = ""
    if not mp3_path.is_file():
        pass
    elif ffmpeg is None:
        issues.append("ffmpeg not found; MP3 audible signal not verified")
        mp3_status = "ffmpeg_missing"
    else:
        stats = decode_mp3_audio_stats(ffmpeg, mp3_path, sample_rate=config.audio_sample_rate)
        mp3_status = str(stats.get("status", "failed"))
        if mp3_status != "ok":
            issues.append(str(stats.get("message", "MP3 audio decode failed")))
        else:
            rms = float(stats.get("rms", 0.0))
            peak = float(stats.get("peak", 0.0))
            mp3_rms = f"{rms:.6f}"
            mp3_peak = f"{peak:.6f}"
            mp3_samples = str(stats.get("sample_count", ""))
            if rms < config.min_mp3_rms:
                issues.append(f"MP3 RMS too low: {rms:.6f}")
            if peak < config.min_mp3_peak:
                issues.append(f"MP3 peak too low: {peak:.6f}")

    return {
        "group": group,
        "score_id": score_id,
        "variant": variant,
        "status": "pass" if not issues else "fail",
        "issues": "; ".join(issues),
        "render_source_check": render_source_check,
        "midi_render_pitch_check": midi_render_check,
        "event_alignment_check": event_alignment_check,
        "stem_target_check": stem_target_check,
        "pitch_similarity": pitch_similarity,
        "stem_target_margin": stem_margin,
        "event_recall": event_recall,
        "event_precision": event_precision,
        "event_f1": event_f1,
        "duration_similarity": duration_similarity,
        "source_note_count": str(source_sig.total_notes) if source_sig else "",
        "render_note_count": str(render_sig.total_notes) if render_sig else "",
        "midi_note_count": str(midi_sig.total_notes) if midi_sig else "",
        "source_duration_quarter_length": f"{source_sig.highest_time:.3f}" if source_sig else "",
        "render_duration_quarter_length": f"{render_sig.highest_time:.3f}" if render_sig else "",
        "midi_duration_quarter_length": f"{midi_sig.highest_time:.3f}" if midi_sig else "",
        "mp3_audio_status": mp3_status,
        "mp3_rms": mp3_rms,
        "mp3_peak": mp3_peak,
        "mp3_sample_count": mp3_samples,
        "source_musicxml": row.get("source_musicxml", ""),
        "render_musicxml": row.get("render_musicxml", ""),
        "midi": row.get("midi", ""),
        "mp3": row.get("mp3", ""),
    }


def validate_render_source(
    source: ScoreSignature,
    render: ScoreSignature,
    variant: str,
    issues: list[str],
) -> str:
    before = len(issues)
    if len(source.part_pitch_sequences) != 4:
        issues.append(f"source score has {len(source.part_pitch_sequences)} parts, expected 4")
    if len(render.part_pitch_sequences) != 4:
        issues.append(f"render score has {len(render.part_pitch_sequences)} parts, expected 4")
    if abs(source.highest_time - render.highest_time) > 0.05:
        issues.append(f"render duration {render.highest_time:.3f} differs from source {source.highest_time:.3f}")
    if variant in {"full_choir", "piano_reference"}:
        if render.part_pitch_sequences != source.part_pitch_sequences:
            issues.append(f"{variant} render pitch sequences do not match source score")
    elif variant in VOICE_INDEX and len(source.part_pitch_sequences) == 4 and len(render.part_pitch_sequences) == 4:
        target = VOICE_INDEX[variant]
        for idx, (source_seq, render_seq) in enumerate(zip(source.part_pitch_sequences, render.part_pitch_sequences)):
            if idx == target and render_seq != source_seq:
                issues.append(f"{variant} target render pitch sequence does not match source voice {idx}")
            if idx != target and render_seq:
                issues.append(f"{variant} non-target render voice {idx} contains {len(render_seq)} notes")
    return "pass" if len(issues) == before else "fail"


def validate_midi_render(
    source: ScoreSignature,
    render: ScoreSignature,
    midi: ScoreSignature,
    variant: str,
    config: ConformanceConfig,
    issues: list[str],
) -> tuple[str, str, str, str, str, str, str, str, str]:
    pitch_before = len(issues)
    stem_check = "not_applicable"
    similarity = 0.0
    margin = 0.0
    midi_flat = midi.flat_pitch_sequence
    if not midi_flat:
        issues.append(f"{variant} MIDI contains no notes")
        return "fail", stem_check, "0.000", "0.000", "fail", "0.000", "0.000", "0.000", "0.000"

    if variant in {"full_choir", "piano_reference"}:
        similarity = pitch_histogram_similarity(render.flat_pitch_sequence, midi_flat)
        if similarity < config.min_full_pitch_similarity:
            issues.append(f"{variant} MIDI/render pitch similarity too low: {similarity:.3f}")
    elif variant in VOICE_INDEX and len(source.part_pitch_sequences) == 4:
        target = VOICE_INDEX[variant]
        target_seq = source.part_pitch_sequences[target]
        similarity = pitch_histogram_similarity(target_seq, midi_flat)
        other_sims = [
            pitch_histogram_similarity(seq, midi_flat)
            for idx, seq in enumerate(source.part_pitch_sequences)
            if idx != target
        ]
        margin = similarity - max(other_sims or [0.0])
        stem_check = "pass"
        if similarity < config.min_stem_pitch_similarity:
            issues.append(f"{variant} MIDI target-voice similarity too low: {similarity:.3f}")
            stem_check = "fail"
        if margin < config.min_stem_target_margin:
            issues.append(f"{variant} MIDI is not clearly closest to target voice: margin={margin:.3f}")
            stem_check = "fail"
        if target_seq:
            ratio = len(midi_flat) / max(len(target_seq), 1)
            if ratio < 0.65 or ratio > 1.35:
                issues.append(f"{variant} MIDI note-count ratio to target voice is suspicious: {ratio:.3f}")
                stem_check = "fail"
    else:
        issues.append(f"cannot validate MIDI/render conformance for variant {variant!r}")

    pitch_check = "pass" if len(issues) == pitch_before else "fail"
    event_before = len(issues)
    recall, precision, f1 = event_alignment_scores(
        render.flat_events,
        midi.flat_events,
        quantum=config.event_quantum_quarter,
    )
    duration_similarity = score_duration_similarity(render.event_highest_time, midi.event_highest_time)
    if recall < config.min_event_recall:
        issues.append(f"{variant} MIDI/render event recall too low: {recall:.3f}")
    if precision < config.min_event_precision:
        issues.append(f"{variant} MIDI/render event precision too low: {precision:.3f}")
    if duration_similarity < config.min_duration_similarity:
        issues.append(f"{variant} MIDI/render duration similarity too low: {duration_similarity:.3f}")
    event_check = "pass" if len(issues) == event_before else "fail"

    return (
        pitch_check,
        stem_check,
        f"{similarity:.3f}",
        f"{margin:.3f}",
        event_check,
        f"{recall:.3f}",
        f"{precision:.3f}",
        f"{f1:.3f}",
        f"{duration_similarity:.3f}",
    )


def get_signature(
    path: Path,
    cache: dict[Path, ScoreSignature],
    issues: list[str],
    label: str,
) -> ScoreSignature | None:
    if path in cache:
        return cache[path]
    if path.suffix.lower() in {".mid", ".midi"}:
        try:
            signature = parse_raw_midi_signature(path)
            cache[path] = signature
            return signature
        except Exception as exc:
            issues.append(f"{label} raw MIDI parse failed: {type(exc).__name__}: {exc}")
            return None
    try:
        score = converter.parse(str(path))
        parts = score.parts or [score]
        sequences: list[tuple[int, ...]] = []
        event_sequences: list[tuple[tuple[int, float, float], ...]] = []
        for part in parts:
            pitches: list[int] = []
            events: list[tuple[int, float, float]] = []
            for item in part.recurse().notes:
                offset = event_offset(item, score)
                duration = float(item.duration.quarterLength or 0.0)
                item_pitches = getattr(item, "pitches", None)
                if item_pitches:
                    for pitch in item_pitches:
                        midi = int(pitch.midi)
                        pitches.append(midi)
                        events.append((midi, offset, duration))
                else:
                    pitch = getattr(item, "pitch", None)
                    if pitch is not None:
                        midi = int(pitch.midi)
                        pitches.append(midi)
                        events.append((midi, offset, duration))
            sequences.append(tuple(pitches))
            event_sequences.append(tuple(events))
        event_duration = max_event_end(event_sequences)
        score_duration = float(score.highestTime)
        signature = ScoreSignature(
            tuple(sequences),
            tuple(event_sequences),
            score_duration,
            event_duration or score_duration,
        )
        cache[path] = signature
        return signature
    except Exception as exc:
        issues.append(f"{label} parse failed: {type(exc).__name__}: {exc}")
        return None


def parse_raw_midi_signature(path: Path) -> ScoreSignature:
    data = path.read_bytes()
    pos = 0
    if data[pos : pos + 4] != b"MThd":
        raise ValueError("missing MIDI header")
    pos += 4
    header_len = read_u32(data, pos)
    pos += 4
    if header_len < 6:
        raise ValueError(f"invalid MIDI header length: {header_len}")
    _, track_count, division = struct.unpack(">HHH", data[pos : pos + 6])
    pos += header_len
    if division & 0x8000:
        raise ValueError("SMPTE time-division MIDI is not supported")
    ticks_per_quarter = max(int(division), 1)

    events_by_channel: dict[int, list[tuple[int, float, float]]] = {idx: [] for idx in range(16)}
    for _ in range(track_count):
        if data[pos : pos + 4] != b"MTrk":
            raise ValueError("missing MIDI track chunk")
        pos += 4
        track_len = read_u32(data, pos)
        pos += 4
        track = data[pos : pos + track_len]
        pos += track_len
        parse_midi_track(track, ticks_per_quarter, events_by_channel)

    event_sequences: list[tuple[tuple[int, float, float], ...]] = []
    pitch_sequences: list[tuple[int, ...]] = []
    for channel in sorted(events_by_channel):
        events = sorted(events_by_channel[channel], key=lambda item: (item[1], item[0], item[2]))
        if not events:
            continue
        event_sequences.append(tuple(events))
        pitch_sequences.append(tuple(int(pitch) for pitch, _, _ in events))
    duration = max_event_end(event_sequences)
    return ScoreSignature(tuple(pitch_sequences), tuple(event_sequences), duration, duration)


def parse_midi_track(
    track: bytes,
    ticks_per_quarter: int,
    events_by_channel: dict[int, list[tuple[int, float, float]]],
) -> None:
    pos = 0
    tick = 0
    running_status: int | None = None
    active: dict[tuple[int, int], list[int]] = {}
    while pos < len(track):
        delta, pos = read_varlen(track, pos)
        tick += delta
        if pos >= len(track):
            break
        status = track[pos]
        first_data: int | None = None
        if status < 0x80:
            if running_status is None:
                raise ValueError("running status used before status byte")
            status_byte = running_status
            first_data = status
            pos += 1
        else:
            status_byte = status
            pos += 1
            if status_byte < 0xF0:
                running_status = status_byte

        if status_byte == 0xFF:
            if pos >= len(track):
                raise ValueError("truncated MIDI meta event")
            pos += 1
            length, pos = read_varlen(track, pos)
            pos += length
            continue
        if status_byte in {0xF0, 0xF7}:
            length, pos = read_varlen(track, pos)
            pos += length
            running_status = None
            continue
        if status_byte >= 0xF0:
            continue

        event_type = status_byte & 0xF0
        channel = status_byte & 0x0F
        data_len = 1 if event_type in {0xC0, 0xD0} else 2
        values: list[int] = []
        if first_data is not None:
            values.append(first_data)
        while len(values) < data_len:
            if pos >= len(track):
                raise ValueError("truncated MIDI channel event")
            values.append(track[pos])
            pos += 1

        if event_type not in {0x80, 0x90}:
            continue
        pitch = int(values[0])
        velocity = int(values[1])
        key = (channel, pitch)
        if event_type == 0x90 and velocity > 0:
            active.setdefault(key, []).append(tick)
            continue
        starts = active.get(key)
        if not starts:
            continue
        start_tick = starts.pop(0)
        if not starts:
            active.pop(key, None)
        if tick <= start_tick:
            continue
        offset = start_tick / ticks_per_quarter
        duration = (tick - start_tick) / ticks_per_quarter
        events_by_channel.setdefault(channel, []).append((pitch, offset, duration))


def read_u32(data: bytes, pos: int) -> int:
    if pos + 4 > len(data):
        raise ValueError("truncated integer")
    return struct.unpack(">I", data[pos : pos + 4])[0]


def read_varlen(data: bytes, pos: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if pos >= len(data):
            raise ValueError("truncated variable-length quantity")
        byte = data[pos]
        pos += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, pos
    raise ValueError("invalid variable-length quantity")


def event_offset(item: object, score: object) -> float:
    try:
        return float(item.getOffsetInHierarchy(score))  # type: ignore[attr-defined]
    except Exception:
        try:
            return float(item.offset)  # type: ignore[attr-defined]
        except Exception:
            return 0.0


def max_event_end(event_sequences: list[tuple[tuple[int, float, float], ...]]) -> float:
    ends = [
        float(offset) + float(duration)
        for sequence in event_sequences
        for _, offset, duration in sequence
    ]
    return max(ends) if ends else 0.0


def event_alignment_scores(
    expected_events: tuple[tuple[int, float, float], ...],
    observed_events: tuple[tuple[int, float, float], ...],
    *,
    quantum: float,
) -> tuple[float, float, float]:
    expected = event_counter(expected_events, quantum=quantum)
    observed = event_counter(observed_events, quantum=quantum)
    if not expected or not observed:
        return 0.0, 0.0, 0.0
    overlap = sum((expected & observed).values())
    expected_total = sum(expected.values())
    observed_total = sum(observed.values())
    recall = overlap / max(expected_total, 1)
    precision = overlap / max(observed_total, 1)
    f1 = 0.0 if recall + precision <= 0 else 2.0 * recall * precision / (recall + precision)
    return recall, precision, f1


def event_counter(events: tuple[tuple[int, float, float], ...], *, quantum: float) -> Counter:
    safe_quantum = quantum if quantum > 0 else 0.25
    return Counter(
        (
            int(round(offset / safe_quantum)),
            int(pitch),
            int(round(duration / safe_quantum)),
        )
        for pitch, offset, duration in events
    )


def score_duration_similarity(expected_duration: float, observed_duration: float) -> float:
    if expected_duration <= 0 or observed_duration <= 0:
        return 0.0
    delta = abs(expected_duration - observed_duration)
    return max(0.0, 1.0 - delta / max(expected_duration, observed_duration, 1.0))


def pitch_histogram_similarity(left: tuple[int, ...] | list[int], right: tuple[int, ...] | list[int]) -> float:
    left_counts = Counter(left)
    right_counts = Counter(right)
    if not left_counts or not right_counts:
        return 0.0
    overlap = sum((left_counts & right_counts).values())
    return overlap / max(sum(left_counts.values()), sum(right_counts.values()), 1)


def decode_mp3_audio_stats(ffmpeg: Path, mp3_path: Path, *, sample_rate: int = 8000) -> dict[str, object]:
    command = [
        str(ffmpeg),
        "-v",
        "error",
        "-i",
        str(mp3_path),
        "-f",
        "f32le",
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "pipe:1",
    ]
    completed = subprocess.run(command, capture_output=True, check=False)
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or b"ffmpeg decode failed").decode("utf-8", errors="replace")
        return {"status": "failed", "message": message.strip()}
    samples = array.array("f")
    try:
        samples.frombytes(completed.stdout)
    except ValueError as exc:
        return {"status": "failed", "message": f"decoded PCM parse failed: {exc}"}
    count = len(samples)
    if count <= 0:
        return {"status": "failed", "message": "decoded MP3 contains no PCM samples"}
    total_square = sum(float(value) * float(value) for value in samples)
    rms = math.sqrt(total_square / count)
    peak = max(abs(float(value)) for value in samples)
    return {"status": "ok", "rms": rms, "peak": peak, "sample_count": count}


def find_ffmpeg() -> Path | None:
    env_path = os.environ.get("CHORALE_FFMPEG_EXE", "")
    if env_path:
        path = Path(env_path)
        if path.is_file():
            return path
    exe = shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if exe:
        path = Path(exe)
        if path.is_file():
            return path
    for candidate in Path("external_tools").glob("**/ffmpeg.exe"):
        if candidate.is_file():
            return candidate
    return None


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def summarize_variants(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in rows:
        key = f"{row.get('group', '')}/{row.get('score_id', '')}"
        out.setdefault(key, set()).add(str(row.get("variant", "")))
    return out


def expected_variant_stem(score_id: str, variant: str, *paths: Path) -> bool:
    expected = f"{score_id}_{variant}"
    return all(path.stem == expected for path in paths if str(path))


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
        "# Project1 Delivery Conformance Audit",
        "",
        f"Score: {data.get('conformance_score')}/100",
        f"All pass: {data.get('all_pass')}",
        f"Package: `{data.get('package_dir')}`",
        f"Entries: {data.get('entry_count')}",
        f"MP3 audible: {data.get('mp3_audible_count')}",
        f"MIDI/render pitch checks passed: {data.get('midi_render_pitch_check_pass_count')}",
        f"Stem target checks passed: {data.get('stem_target_check_pass_count')}",
        f"Event alignment checks passed: {data.get('event_alignment_pass_count')}",
        f"Minimum pitch similarity: {data.get('min_pitch_similarity')}",
        f"Minimum event recall: {data.get('min_event_recall')}",
        f"Minimum event precision: {data.get('min_event_precision')}",
        f"Minimum duration similarity: {data.get('min_duration_similarity')}",
        f"Minimum MP3 RMS: {data.get('min_mp3_rms')}",
        "",
        str(data.get("method_note", "")),
        "",
    ]
    failures = data.get("failure_examples", [])
    if isinstance(failures, list) and failures:
        lines.extend(["## Failure Examples", ""])
        for item in failures:
            if isinstance(item, dict):
                lines.append(f"- {item.get('group')}/{item.get('score_id')}/{item.get('variant')}: {item.get('issues')}")
    else:
        lines.append("No score-playback conformance issues detected by this automatic audit.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit score-playback conformance for the final Project1 delivery package.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--out-json", default="results/project1_delivery_conformance_audit_latest.json")
    args = parser.parse_args()
    audit = audit_delivery_conformance(args.package_dir)
    outputs = write_outputs(audit, args.out_json)
    print(json.dumps({"summary": audit["summary"], "outputs": outputs}, indent=2, ensure_ascii=False))
    if not audit["summary"].get("all_pass"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
