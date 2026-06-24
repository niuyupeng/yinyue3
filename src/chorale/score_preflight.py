from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
from music21 import chord, converter, note, stream

from chorale.data.score_tokenizer import VOICE_NAMES, VOICE_RANGES
from chorale.theory.roman_numeral import approximate_key, key_label_and_tonic_pc
from chorale.utils import write_json


MUSICXML_SUFFIXES = {".musicxml", ".xml", ".mxl"}
VOICE_TO_INDEX = {name: idx for idx, name in enumerate(VOICE_NAMES)}


def analyze_score_input(
    input_musicxml: str | Path,
    *,
    task: str = "auto",
    input_role: str = "soprano",
    known_voices: str | list[str] | None = None,
    grid_quarter_length: float = 0.25,
    max_seq_len: int = 256,
) -> dict[str, Any]:
    """Preflight a user score before SATB harmonization.

    The preflight is deliberately conservative: it validates that the file can
    be parsed, that there is usable pitch material, that known input voices can
    be resolved, and that the material is compatible with the fixed symbolic
    grid used by the harmonizer.
    """
    path = Path(input_musicxml)
    critical: list[str] = []
    issues: list[str] = []
    warnings: list[str] = []

    if not path.is_file():
        return failed_preflight(path, f"input file not found: {path}")
    if path.suffix.lower() not in MUSICXML_SUFFIXES:
        warnings.append(f"input suffix {path.suffix or '<none>'} is not a standard MusicXML suffix")

    try:
        parsed = converter.parse(str(path))
        score = normalize_to_score(parsed)
    except Exception as exc:
        return failed_preflight(path, f"MusicXML parse failed: {type(exc).__name__}: {exc}")

    parts = list(score.parts)
    if not parts:
        return failed_preflight(path, "score has no parts")

    total_duration = max((float(part.duration.quarterLength) for part in parts), default=0.0)
    estimated_timesteps = max(1, int(np.ceil(total_duration / float(grid_quarter_length)))) if total_duration > 0 else 0
    if estimated_timesteps <= 0:
        critical.append("score has no positive duration")
    if estimated_timesteps > int(max_seq_len):
        issues.append(
            f"score length {estimated_timesteps} grid steps exceeds max_seq_len {int(max_seq_len)} and will be truncated"
        )

    part_reports = [analyze_part(part, idx, grid_quarter_length) for idx, part in enumerate(parts)]
    total_notes = sum(int(item["note_count"]) for item in part_reports)
    if total_notes <= 0:
        critical.append("score has no notes")

    inferred_voice_indices = infer_part_voice_indices(score, input_role)
    resolved_known_indices = resolve_known_voice_indices(score, task, input_role, known_voices)
    if not resolved_known_indices:
        critical.append("could not resolve any known input voice")

    if len(parts) not in {1, 2, 4}:
        issues.append(f"score has {len(parts)} parts; one-part, two-part, or SATB four-part input is safest")
    if len(parts) > 4:
        issues.append("score has more than four parts; extra parts may be ignored by the harmonizer")

    for idx, report in enumerate(part_reports):
        role_idx = inferred_voice_indices[idx] if idx < len(inferred_voice_indices) else -1
        role_name = VOICE_NAMES[role_idx] if 0 <= role_idx < len(VOICE_NAMES) else "unknown"
        report["inferred_voice"] = role_name
        if int(report["non_quantized_events"]) > 0:
            issues.append(
                f"part {idx + 1} has {int(report['non_quantized_events'])} events off the {grid_quarter_length} quarter-note grid"
            )
        if bool(report["has_chords"]) or int(report["max_simultaneous_pitches"]) > 1:
            if role_name in {"soprano", "bass"} or len(parts) == 1:
                issues.append(f"part {idx + 1} appears polyphonic; melody/bass inputs should be monophonic")
            else:
                warnings.append(f"part {idx + 1} contains chords or overlapping notes")
        if role_name in VOICE_RANGES:
            low, high = VOICE_RANGES[role_name]
            out_of_range = count_out_of_range(report["pitches"], low, high)
            report["range_low"] = low
            report["range_high"] = high
            report["out_of_range_count"] = out_of_range
            if out_of_range > 0:
                issues.append(
                    f"part {idx + 1} inferred as {role_name} has {out_of_range} pitches outside {low}-{high}"
                )

    try:
        key_obj = approximate_key(score)
        key_label, key_tonic_pc = key_label_and_tonic_pc(key_obj)
    except Exception:
        key_label, key_tonic_pc = "UNKNOWN", -1
        warnings.append("automatic key estimation failed")

    status = "failed" if critical else ("needs_review" if issues else "pass")
    return {
        "schema": "project1_score_input_preflight_v1",
        "input_musicxml": str(path),
        "status": status,
        "critical": critical,
        "issues": issues,
        "warnings": warnings,
        "task": task,
        "input_role": input_role,
        "explicit_known_voices": normalize_known_voice_names(known_voices),
        "resolved_known_voices": [VOICE_NAMES[idx] for idx in resolved_known_indices],
        "part_count": len(parts),
        "note_count": int(total_notes),
        "total_duration_quarters": float(total_duration),
        "grid_quarter_length": float(grid_quarter_length),
        "estimated_timesteps": int(estimated_timesteps),
        "max_seq_len": int(max_seq_len),
        "will_truncate": bool(estimated_timesteps > int(max_seq_len)),
        "key_label": key_label,
        "key_tonic_pc": int(key_tonic_pc),
        "parts": part_reports,
        "recommendations": recommendations_for(status, issues, warnings),
    }


def failed_preflight(path: Path, message: str) -> dict[str, Any]:
    return {
        "schema": "project1_score_input_preflight_v1",
        "input_musicxml": str(path),
        "status": "failed",
        "critical": [message],
        "issues": [],
        "warnings": [],
        "resolved_known_voices": [],
        "part_count": 0,
        "note_count": 0,
        "recommendations": ["Fix the input MusicXML before running SATB harmonization."],
    }


def normalize_to_score(parsed: stream.Score | stream.Part | stream.Stream) -> stream.Score:
    if isinstance(parsed, stream.Score):
        return parsed
    score = stream.Score()
    if isinstance(parsed, stream.Part):
        score.insert(0, parsed)
    else:
        part = stream.Part()
        for element in parsed.flatten().notesAndRests:
            part.insert(float(element.offset), element)
        score.insert(0, part)
    return score


def analyze_part(part: stream.Part, index: int, grid_quarter_length: float) -> dict[str, Any]:
    elements = list(part.flatten().notesAndRests)
    notes = list(part.flatten().notes)
    events: list[tuple[float, float, int]] = []
    pitches: list[int] = []
    non_quantized = 0
    has_chords = False
    for element in elements:
        offset = float(element.offset)
        duration = max(float(element.duration.quarterLength), 0.0)
        if not is_on_grid(offset, grid_quarter_length) or not is_on_grid(duration, grid_quarter_length):
            non_quantized += 1
        if isinstance(element, chord.Chord):
            has_chords = True
            for p in element.pitches:
                midi = int(p.midi)
                pitches.append(midi)
                events.append((offset, offset + duration, midi))
        elif isinstance(element, note.Note):
            midi = int(element.pitch.midi)
            pitches.append(midi)
            events.append((offset, offset + duration, midi))

    max_simultaneous = max_simultaneous_pitches(events)
    return {
        "part_index": int(index),
        "part_name": str(part.partName or part.id or f"part_{index + 1}"),
        "note_count": int(len(notes)),
        "pitch_count": int(len(pitches)),
        "rest_count": int(sum(1 for element in elements if element.isRest)),
        "duration_quarters": float(part.duration.quarterLength),
        "lowest_midi": int(min(pitches)) if pitches else None,
        "highest_midi": int(max(pitches)) if pitches else None,
        "pitches": pitches,
        "has_chords": bool(has_chords),
        "max_simultaneous_pitches": int(max_simultaneous),
        "non_quantized_events": int(non_quantized),
    }


def is_on_grid(value: float, grid_quarter_length: float, tol: float = 1e-6) -> bool:
    if grid_quarter_length <= 0:
        return True
    scaled = float(value) / float(grid_quarter_length)
    return abs(scaled - round(scaled)) <= tol


def max_simultaneous_pitches(events: list[tuple[float, float, int]]) -> int:
    if not events:
        return 0
    boundaries = sorted({start for start, _, _ in events} | {end for _, end, _ in events})
    max_count = 0
    for t in boundaries:
        count = sum(1 for start, end, _ in events if start <= t < end and end > start)
        max_count = max(max_count, count)
    return int(max_count)


def infer_part_voice_indices(score: stream.Score, input_role: str) -> list[int]:
    parts = list(score.parts)
    indices: list[int] = []
    for part in parts:
        label = " ".join(str(item or "") for item in (part.partName, part.partAbbreviation, part.id)).lower()
        found = next((VOICE_TO_INDEX[name] for name in VOICE_NAMES if name in label), None)
        indices.append(int(found) if found is not None else -1)
    if indices and all(idx >= 0 for idx in indices):
        return indices
    if len(parts) == 1:
        return [VOICE_TO_INDEX.get(input_role.lower().strip(), VOICE_TO_INDEX["soprano"])]
    if len(parts) == 2:
        fallback = [VOICE_TO_INDEX["soprano"], VOICE_TO_INDEX["bass"]]
    else:
        fallback = [0, 1, 2, 3]
    return [idx if idx >= 0 else fallback[pos] for pos, idx in enumerate(indices[:4])]


def resolve_known_voice_indices(
    score: stream.Score,
    task: str,
    input_role: str,
    known_voices: str | list[str] | None,
) -> list[int]:
    explicit = normalize_known_voice_names(known_voices)
    if explicit:
        return sorted({VOICE_TO_INDEX[name] for name in explicit if name in VOICE_TO_INDEX})
    normalized_task = str(task or "auto").lower().strip()
    if normalized_task == "bass_to_satb":
        return [VOICE_TO_INDEX["bass"]]
    if normalized_task == "masked_infill":
        return infer_part_voice_indices(score, input_role)
    if normalized_task == "auto":
        inferred = infer_part_voice_indices(score, input_role)
        if len(inferred) == 1:
            return inferred
        return [VOICE_TO_INDEX["soprano"]]
    return [VOICE_TO_INDEX.get(input_role.lower().strip(), VOICE_TO_INDEX["soprano"])]


def normalize_known_voice_names(known_voices: str | list[str] | None) -> list[str]:
    if not known_voices:
        return []
    if isinstance(known_voices, str):
        items = [item.strip().lower() for item in known_voices.split(",")]
    else:
        items = [str(item).strip().lower() for item in known_voices]
    return [item for item in items if item in VOICE_TO_INDEX]


def count_out_of_range(pitches: list[int], low: int, high: int) -> int:
    return int(sum(1 for pitch in pitches if int(pitch) < int(low) or int(pitch) > int(high)))


def recommendations_for(status: str, issues: list[str], warnings: list[str]) -> list[str]:
    if status == "failed":
        return ["Fix the input MusicXML before running SATB harmonization."]
    recommendations: list[str] = []
    if any("polyphonic" in item for item in issues):
        recommendations.append("Provide a single melodic line for soprano-to-SATB or bass-to-SATB tasks.")
    if any("outside" in item for item in issues):
        recommendations.append("Transpose or relabel the input voice so it falls in a normal SATB range.")
    if any("grid" in item for item in issues):
        recommendations.append("Quantize the score to the project grid or use MusicXML exported from notation software.")
    if any("truncated" in item for item in issues):
        recommendations.append("Split long scores into shorter phrases or increase max_seq_len with a compatible checkpoint.")
    if not recommendations and warnings:
        recommendations.append("Review warnings, then run harmonization if the score is intentional.")
    if not recommendations:
        recommendations.append("Input appears ready for SATB harmonization.")
    return recommendations


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight-check a user MusicXML score for Project1 SATB harmonization.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--task", default="auto", choices=["soprano_to_satb", "bass_to_satb", "masked_infill", "auto"])
    parser.add_argument("--input-role", default="soprano", choices=list(VOICE_NAMES))
    parser.add_argument("--known-voices", default=None)
    parser.add_argument("--grid-quarter-length", type=float, default=0.25)
    parser.add_argument("--max-seq-len", type=int, default=256)
    parser.add_argument("--output-json", default=None)
    args = parser.parse_args()
    report = analyze_score_input(
        args.input,
        task=args.task,
        input_role=args.input_role,
        known_voices=args.known_voices,
        grid_quarter_length=args.grid_quarter_length,
        max_seq_len=args.max_seq_len,
    )
    if args.output_json:
        write_json(report, args.output_json)
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
