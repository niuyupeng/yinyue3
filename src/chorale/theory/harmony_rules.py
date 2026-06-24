from __future__ import annotations

from collections import Counter
from typing import Any

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer, VOICE_NAMES
from chorale.theory.roman_numeral import (
    UNKNOWN,
    chordal_seventh_pitch_classes,
    is_dominant_roman,
    is_seventh_sonority,
    is_submediant_roman,
    is_tonic_roman,
)
from chorale.theory.voice_leading_rules import RuleViolation, location_text


def check_seventh_resolution(
    tokens,
    tokenizer: ScoreTokenizer,
    harmonic_labels: dict[str, Any] | None = None,
    chord_labels=None,
    length=None,
) -> dict:
    if harmonic_labels is None and chord_labels is None:
        return _empty_report(
            "seventh_resolution",
            ["Seventh-resolution checking skipped because no harmonic labels were supplied."],
        )
    labels = harmonic_labels or {}
    midi = tokenizer.expand_holds(np.asarray(tokens), length=length)
    total_steps = midi.shape[0]
    events = harmonic_event_indices(midi, labels, total_steps)
    beat_positions = label_array(labels, "beat_positions", total_steps, -1)
    violations: list[RuleViolation] = []
    confident_checks = 0

    for event_pos, timestep in enumerate(events):
        if not is_confident_harmonic_timestep(int(timestep), beat_positions, tokenizer.grid_quarter_length):
            continue
        pcs = vertical_pitch_classes(midi[timestep])
        if len(pcs) < 3:
            continue
        root_pc = int(label_array(labels, "chord_roots", total_steps, -1)[timestep])
        roman_label = str(label_array(labels, "roman_numerals", total_steps, UNKNOWN)[timestep])
        quality = str(label_array(labels, "chord_qualities", total_steps, UNKNOWN)[timestep])
        is_seventh = bool(label_array(labels, "is_seventh_chord", total_steps, False)[timestep])
        if not is_seventh:
            is_seventh = is_seventh_sonority(pcs, root_pc, roman_label, quality)
        seventh_pcs = chordal_seventh_pitch_classes(pcs, root_pc, roman_label, quality)
        if not is_seventh or not seventh_pcs:
            continue
        next_timestep = next_harmonic_event(events, event_pos)
        if next_timestep is None:
            continue
        for voice_idx, voice_name in enumerate(VOICE_NAMES):
            current_pitch = midi[timestep, voice_idx]
            next_pitch = midi[next_timestep, voice_idx]
            if np.isnan(current_pitch) or np.isnan(next_pitch):
                continue
            if int(current_pitch) % 12 not in seventh_pcs:
                continue
            confident_checks += 1
            motion = int(round(next_pitch - current_pitch))
            if motion not in (-1, -2):
                measure, beat, loc = location_text(timestep, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule="seventh_resolution",
                        timestep=int(timestep),
                        measure=measure,
                        beat=beat,
                        penalty=1.0,
                        message=f"{loc}: chordal seventh in {voice_name} does not resolve downward by step",
                    )
                )

    limitations = []
    if confident_checks == 0:
        limitations.append("No confident chordal sevenths were detected; no seventh-resolution violations were inferred.")
    return _report_from_violations("seventh_resolution", violations, total_steps, limitations, confident_checks)


def check_cadence_correctness(
    tokens,
    tokenizer: ScoreTokenizer,
    harmonic_labels: dict[str, Any] | None = None,
    roman_labels=None,
    length=None,
    expected_final_cadence: str | None = None,
) -> dict:
    if harmonic_labels is None and roman_labels is None:
        return {
            **_empty_report(
                "cadence_correctness",
                ["Cadence checking skipped because no harmonic labels were supplied."],
            ),
            "cadence_type": UNKNOWN,
            "cadence_checks": 0,
            "cadence_unknown_count": 1,
            "cadence_unknown_rate": 1.0,
        }

    labels = dict(harmonic_labels or {})
    if roman_labels is not None and "roman_numerals" not in labels:
        labels["roman_numerals"] = np.asarray(roman_labels)
    total_steps = int(length if length is not None else len(labels.get("roman_numerals", [])))
    if total_steps <= 0:
        total_steps = np.asarray(tokens).shape[0]
    roman_array = label_array(labels, "roman_numerals", total_steps, UNKNOWN)
    roots = label_array(labels, "chord_roots", total_steps, -1)
    phrase_end = label_array(labels, "is_phrase_end", total_steps, False)
    active_counts = label_array(labels, "active_voice_counts", total_steps, 0)
    pc_counts = label_array(labels, "distinct_pitch_class_counts", total_steps, 0)
    dominant_function = label_array(labels, "is_dominant_function", total_steps, False)
    key_tonic_pc = int(labels.get("key_tonic_pc", 0))
    cadence_type, final_t, prev_t = classify_cadence(
        roman_array,
        roots,
        phrase_end,
        key_tonic_pc,
        total_steps,
        active_counts=active_counts,
        pc_counts=pc_counts,
        dominant_function=dominant_function,
    )

    violations: list[RuleViolation] = []
    if expected_final_cadence == "authentic" and cadence_type not in ("authentic_cadence_like", UNKNOWN):
        final_root = int(roots[final_t]) if final_t is not None else -1
        final_roman = str(roman_array[final_t]) if final_t is not None else UNKNOWN
        clear_final_not_tonic = final_root >= 0 and final_root % 12 != key_tonic_pc and final_roman != UNKNOWN
        if clear_final_not_tonic:
            measure, beat, loc = location_text(int(final_t), tokenizer.grid_quarter_length)
            violations.append(
                RuleViolation(
                    rule="cadence_correctness",
                    timestep=int(final_t),
                    measure=measure,
                    beat=beat,
                    penalty=1.0,
                    message=f"m. {measure}: expected authentic cadence-like closure, but final harmony is not tonic",
                )
            )

    unknown_count = 1 if cadence_type == UNKNOWN else 0
    report = _report_from_violations("cadence_correctness", violations, total_steps, [], 1 - unknown_count)
    report.update(
        {
            "cadence_type": cadence_type,
            "cadence_checks": 1,
            "cadence_unknown_count": unknown_count,
            "cadence_unknown_rate": float(unknown_count),
            "final_timestep": None if final_t is None else int(final_t),
            "previous_timestep": None if prev_t is None else int(prev_t),
        }
    )
    if cadence_type == UNKNOWN:
        report["limitations"].append("Cadence type is UNKNOWN because harmonic evidence was insufficient.")
    return report


def classify_cadence(
    roman_array: np.ndarray,
    roots: np.ndarray,
    phrase_end: np.ndarray,
    key_tonic_pc: int,
    total_steps: int,
    active_counts: np.ndarray | None = None,
    pc_counts: np.ndarray | None = None,
    dominant_function: np.ndarray | None = None,
) -> tuple[str, int | None, int | None]:
    candidates = [
        idx
        for idx in range(total_steps)
        if bool(phrase_end[idx])
        and is_cadence_harmony_candidate(roman_array, roots, idx, active_counts, pc_counts, dominant_function)
    ]
    if not candidates:
        candidates = [
            idx
            for idx in range(total_steps)
            if is_cadence_harmony_candidate(roman_array, roots, idx, active_counts, pc_counts, dominant_function)
        ]
    if not candidates:
        candidates = [idx for idx in range(total_steps) if is_known_harmony(roman_array, roots, idx, dominant_function)]
    if not candidates:
        return UNKNOWN, None, None
    final_t = candidates[-1]
    previous_candidates = [
        idx
        for idx in range(final_t)
        if is_cadence_harmony_candidate(roman_array, roots, idx, active_counts, pc_counts, dominant_function)
    ]
    if not previous_candidates:
        previous_candidates = [
            idx for idx in range(final_t) if is_known_harmony(roman_array, roots, idx, dominant_function)
        ]
    prev_t = previous_candidates[-1] if previous_candidates else None
    final_roman = str(roman_array[final_t])
    prev_roman = str(roman_array[prev_t]) if prev_t is not None else UNKNOWN
    final_root = int(roots[final_t]) if int(roots[final_t]) >= 0 else None
    prev_root = int(roots[prev_t]) if prev_t is not None and int(roots[prev_t]) >= 0 else None
    dominant_root_pc = (int(key_tonic_pc) + 7) % 12
    prev_dom_flag = bool(dominant_function[prev_t]) if dominant_function is not None and prev_t is not None else False
    final_dom_flag = bool(dominant_function[final_t]) if dominant_function is not None else False
    prev_is_dom = (
        is_dominant_roman(prev_roman)
        or (prev_root is not None and prev_root % 12 == dominant_root_pc)
        or prev_dom_flag
    )
    final_is_dom = (
        is_dominant_roman(final_roman)
        or (final_root is not None and final_root % 12 == dominant_root_pc)
        or final_dom_flag
    )
    final_is_tonic = is_tonic_roman(final_roman) or (final_root is not None and final_root % 12 == key_tonic_pc)
    final_is_vi = is_submediant_roman(final_roman) or (
        final_root is not None and final_root % 12 == (key_tonic_pc + 9) % 12
    )
    if prev_is_dom and final_is_tonic:
        return "authentic_cadence_like", final_t, prev_t
    if final_is_dom:
        return "half_cadence_like", final_t, prev_t
    if prev_is_dom and final_is_vi:
        return "deceptive_cadence_like", final_t, prev_t
    if final_is_tonic:
        return "tonic_closure_like", final_t, prev_t
    return UNKNOWN, final_t, prev_t


def is_known_harmony(
    roman_array: np.ndarray,
    roots: np.ndarray,
    idx: int,
    dominant_function: np.ndarray | None = None,
) -> bool:
    dominant_flag = bool(dominant_function[idx]) if dominant_function is not None else False
    return str(roman_array[idx]) != UNKNOWN or int(roots[idx]) >= 0 or dominant_flag


def is_cadence_harmony_candidate(
    roman_array: np.ndarray,
    roots: np.ndarray,
    idx: int,
    active_counts: np.ndarray | None,
    pc_counts: np.ndarray | None,
    dominant_function: np.ndarray | None = None,
) -> bool:
    if not is_known_harmony(roman_array, roots, idx, dominant_function):
        return False
    if active_counts is None or pc_counts is None:
        return True
    if int(active_counts[idx]) <= 0 and int(pc_counts[idx]) <= 0:
        return True
    return int(active_counts[idx]) >= 3 and int(pc_counts[idx]) >= 2


def harmonic_event_indices(midi: np.ndarray, labels: dict[str, Any], length: int) -> list[int]:
    events: list[int] = []
    roman = label_array(labels, "roman_numerals", length, UNKNOWN)
    roots = label_array(labels, "chord_roots", length, -1)
    previous_signature = None
    for t in range(length):
        signature = (
            tuple(sorted(vertical_pitch_classes(midi[t]))),
            str(roman[t]),
            int(roots[t]),
        )
        if signature != previous_signature:
            events.append(t)
            previous_signature = signature
    return events


def next_harmonic_event(events: list[int], event_pos: int) -> int | None:
    if event_pos + 1 >= len(events):
        return None
    return events[event_pos + 1]


def is_confident_harmonic_timestep(timestep: int, beat_positions: np.ndarray, grid_quarter_length: float) -> bool:
    """Limit automatic seventh checks to beat-level harmonic events when beat data exists."""
    if timestep < 0 or timestep >= len(beat_positions):
        return True
    beat_position = int(beat_positions[timestep])
    if beat_position < 0:
        return True
    steps_per_quarter = max(1, int(round(1.0 / float(grid_quarter_length))))
    return beat_position % steps_per_quarter == 0


def vertical_pitch_classes(row: np.ndarray) -> set[int]:
    return {int(p) % 12 for p in row if not np.isnan(p)}


def label_array(labels: dict[str, Any], key: str, length: int, default) -> np.ndarray:
    if key not in labels or labels[key] is None:
        return np.full(length, default)
    arr = np.asarray(labels[key])
    if arr.ndim == 0:
        return np.full(length, arr.item())
    if len(arr) < length:
        fill = np.full(length, default, dtype=arr.dtype)
        fill[: len(arr)] = arr
        return fill
    return arr[:length]


def _empty_report(rule: str, limitations: list[str]) -> dict:
    return {
        "rule": rule,
        "implemented": True,
        "total_penalty": 0.0,
        "total_violations": 0,
        "counts": {},
        "violations_per_100_timesteps": 0.0,
        "violations": [],
        "explanations": [],
        "limitations": limitations,
        "confident_checks": 0,
    }


def _report_from_violations(
    rule: str,
    violations: list[RuleViolation],
    total_steps: int,
    limitations: list[str],
    confident_checks: int,
) -> dict:
    counts = Counter(v.rule for v in violations)
    return {
        "rule": rule,
        "implemented": True,
        "total_penalty": float(sum(v.penalty for v in violations)),
        "total_violations": int(len(violations)),
        "counts": dict(counts),
        "violations_per_100_timesteps": 100.0 * len(violations) / max(1, total_steps),
        "violations": [v.to_dict() for v in violations],
        "explanations": [v.message for v in violations],
        "limitations": limitations,
        "confident_checks": int(confident_checks),
    }
