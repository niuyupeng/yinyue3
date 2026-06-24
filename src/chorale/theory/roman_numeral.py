from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np
from music21 import chord, key, pitch, roman, stream

from chorale.data.score_tokenizer import ScoreTokenizer

UNKNOWN = "UNKNOWN"


def approximate_key(score: stream.Score) -> key.Key:
    try:
        analyzed = score.analyze("key")
        if isinstance(analyzed, key.Key):
            return analyzed
    except Exception:
        pass
    return key.Key("C")


def key_label_and_tonic_pc(local_key: key.Key) -> tuple[str, int]:
    try:
        return str(local_key), int(local_key.tonic.pitchClass)
    except Exception:
        return "C major", 0


def key_from_label_or_pc(key_label: str | None = None, tonic_pc: int | None = None) -> key.Key:
    if key_label and key_label != UNKNOWN:
        try:
            return key.Key(key_label)
        except Exception:
            pass
    tonic = pitch.Pitch()
    tonic.pitchClass = int(tonic_pc or 0) % 12
    return key.Key(tonic.name)


def approximate_chord_root_from_tokens(midi_values: list[int | None]) -> int | None:
    pcs = sorted({m % 12 for m in midi_values if m is not None})
    if not pcs:
        return None
    return pcs[0]


def chord_to_roman(ch: chord.Chord, local_key: key.Key) -> str:
    try:
        rn = roman.romanNumeralFromChord(ch, local_key)
        figure = str(rn.figure)
        return figure if figure else UNKNOWN
    except Exception:
        return UNKNOWN


def annotate_score_harmony(
    score: stream.Score,
    tokenizer: ScoreTokenizer,
    tokens: np.ndarray,
    length: int,
    measure_indices: np.ndarray | None = None,
    beat_positions: np.ndarray | None = None,
) -> dict[str, Any]:
    local_key = approximate_key(score)
    key_label, tonic_pc = key_label_and_tonic_pc(local_key)
    return annotate_tokens_harmony(
        tokens=tokens,
        tokenizer=tokenizer,
        length=length,
        key_label=key_label,
        key_tonic_pc=tonic_pc,
        measure_indices=measure_indices,
        beat_positions=beat_positions,
        local_key=local_key,
    )


def annotate_tokens_harmony(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    key_label: str | None = None,
    key_tonic_pc: int | None = None,
    measure_indices: np.ndarray | None = None,
    beat_positions: np.ndarray | None = None,
    local_key: key.Key | None = None,
) -> dict[str, Any]:
    matrix = np.asarray(tokens, dtype=np.int64)
    if length is None:
        length = matrix.shape[0]
    length = int(max(0, min(length, matrix.shape[0])))
    max_seq_len = matrix.shape[0]
    local_key = local_key or key_from_label_or_pc(key_label, key_tonic_pc)
    key_label, tonic_pc = key_label_and_tonic_pc(local_key)
    midi = tokenizer.expand_holds(matrix, length=length)

    chord_roots = np.full(max_seq_len, -1, dtype=np.int64)
    chord_qualities = np.full(max_seq_len, UNKNOWN, dtype="<U32")
    roman_numerals = np.full(max_seq_len, UNKNOWN, dtype="<U32")
    is_seventh_chord = np.zeros(max_seq_len, dtype=bool)
    is_dominant_function = np.zeros(max_seq_len, dtype=bool)
    is_phrase_end = np.zeros(max_seq_len, dtype=bool)
    chord_label_known = np.zeros(max_seq_len, dtype=bool)
    roman_numeral_known = np.zeros(max_seq_len, dtype=bool)
    active_voice_counts = np.zeros(max_seq_len, dtype=np.int64)
    distinct_pitch_class_counts = np.zeros(max_seq_len, dtype=np.int64)

    cache: dict[tuple[int, ...], tuple[int, str, str, bool, bool, bool, bool]] = {}
    for t in range(length):
        pitches = tuple(sorted(int(x) for x in midi[t] if not np.isnan(x)))
        pcs = tuple(sorted({p % 12 for p in pitches}))
        active_voice_counts[t] = len(pitches)
        distinct_pitch_class_counts[t] = len(pcs)
        if len(pcs) < 2:
            continue
        if pcs not in cache:
            cache[pcs] = _analyze_vertical_pcs(pitches, local_key, tonic_pc)
        root_pc, quality, roman_label, seventh, dominant, chord_known, roman_known = cache[pcs]
        chord_roots[t] = root_pc
        chord_qualities[t] = quality
        roman_numerals[t] = roman_label
        is_seventh_chord[t] = seventh
        is_dominant_function[t] = dominant
        chord_label_known[t] = chord_known
        roman_numeral_known[t] = roman_known

    is_phrase_end[:length] = infer_phrase_end_mask(length, tokenizer.grid_quarter_length, measure_indices)
    return {
        "key_label": key_label,
        "key_tonic_pc": np.int64(tonic_pc),
        "beat_positions": np.asarray(beat_positions[:max_seq_len], dtype=np.int64)
        if beat_positions is not None
        else np.full(max_seq_len, -1, dtype=np.int64),
        "measure_indices": np.asarray(measure_indices[:max_seq_len], dtype=np.int64)
        if measure_indices is not None
        else np.full(max_seq_len, -1, dtype=np.int64),
        "chord_roots": chord_roots,
        "chord_qualities": chord_qualities,
        "roman_numerals": roman_numerals,
        "is_seventh_chord": is_seventh_chord,
        "is_dominant_function": is_dominant_function,
        "is_phrase_end": is_phrase_end,
        "chord_label_known": chord_label_known,
        "roman_numeral_known": roman_numeral_known,
        "active_voice_counts": active_voice_counts,
        "distinct_pitch_class_counts": distinct_pitch_class_counts,
    }


def infer_phrase_end_mask(
    length: int,
    grid_quarter_length: float,
    measure_indices: np.ndarray | None = None,
) -> np.ndarray:
    mask = np.zeros(length, dtype=bool)
    if length <= 0:
        return mask
    mask[length - 1] = True
    if measure_indices is None:
        positions = np.arange(length, dtype=np.float32) * float(grid_quarter_length)
        measures = np.floor(positions / 4.0).astype(np.int64) + 1
    else:
        measures = np.asarray(measure_indices[:length], dtype=np.int64)
    for t in range(length - 1):
        if measures[t] != measures[t + 1] and int(measures[t]) % 4 == 0:
            mask[t] = True
    final_measure = int(measures[-1])
    mask[measures >= max(1, final_measure - 1)] = True
    return mask


def _analyze_vertical_pcs(
    pitches: tuple[int, ...],
    local_key: key.Key,
    tonic_pc: int,
) -> tuple[int, str, str, bool, bool, bool, bool]:
    try:
        ch = chord.Chord(list(pitches))
        root = ch.root()
        root_pc = int(root.pitchClass) if root is not None else -1
        quality = safe_quality(ch)
        roman_label = chord_to_roman(ch, local_key)
    except Exception:
        root_pc, quality, roman_label = -1, UNKNOWN, UNKNOWN

    pcs = sorted({p % 12 for p in pitches})
    seventh = is_seventh_sonority(pcs, root_pc, roman_label, quality)
    dominant = is_dominant_function_like(root_pc, roman_label, quality, tonic_pc, pcs)
    chord_known = root_pc >= 0 and quality != UNKNOWN
    roman_known = roman_label != UNKNOWN
    return root_pc, quality, roman_label, seventh, dominant, chord_known, roman_known


def safe_quality(ch: chord.Chord) -> str:
    for attr in ("quality", "commonName"):
        try:
            value = getattr(ch, attr)
            if callable(value):
                value = value()
            if value:
                return str(value)
        except Exception:
            continue
    return UNKNOWN


def is_seventh_sonority(
    pcs: list[int] | tuple[int, ...] | set[int],
    root_pc: int,
    roman_label: str = UNKNOWN,
    quality: str = UNKNOWN,
) -> bool:
    if root_pc < 0:
        return False
    pc_set = {int(pc) % 12 for pc in pcs}
    label = (roman_label or UNKNOWN).lower()
    quality_lower = (quality or UNKNOWN).lower()
    if "7" in label or "seventh" in quality_lower:
        return True
    return ((root_pc + 10) % 12 in pc_set or (root_pc + 11) % 12 in pc_set) and len(pc_set) >= 4


def chordal_seventh_pitch_classes(
    pcs: list[int] | tuple[int, ...] | set[int],
    root_pc: int,
    roman_label: str = UNKNOWN,
    quality: str = UNKNOWN,
) -> set[int]:
    if root_pc < 0:
        return set()
    pc_set = {int(pc) % 12 for pc in pcs}
    candidates = {(root_pc + 10) % 12, (root_pc + 11) % 12}
    present = candidates & pc_set
    if present and is_seventh_sonority(pc_set, root_pc, roman_label, quality):
        return present
    return set()


def is_dominant_function_like(
    root_pc: int,
    roman_label: str = UNKNOWN,
    quality: str = UNKNOWN,
    key_tonic_pc: int = 0,
    pcs: list[int] | tuple[int, ...] | set[int] | None = None,
) -> bool:
    label = normalize_roman_label(roman_label)
    if label.startswith("V") and not label.startswith("VI"):
        return True
    tonic_pc = int(key_tonic_pc) % 12
    dominant_root_pc = (tonic_pc + 7) % 12
    if root_pc >= 0 and root_pc % 12 == dominant_root_pc:
        quality_lower = (quality or UNKNOWN).lower()
        if any(word in quality_lower for word in ("major", "dominant", "seventh")):
            return True
    if pcs is not None:
        pc_set = {int(pc) % 12 for pc in pcs}
        dominant_third_pc = (tonic_pc + 11) % 12
        dominant_fifth_pc = (tonic_pc + 2) % 12
        dominant_seventh_pc = (tonic_pc + 5) % 12
        has_root = dominant_root_pc in pc_set
        has_leading_tone = dominant_third_pc in pc_set
        has_fifth_or_seventh = dominant_fifth_pc in pc_set or dominant_seventh_pc in pc_set
        if has_root and has_leading_tone and has_fifth_or_seventh:
            return True
    return False


def normalize_roman_label(label: str | None) -> str:
    if not label:
        return UNKNOWN
    cleaned = str(label).strip()
    if cleaned == "":
        return UNKNOWN
    for prefix in ("#", "b", "-"):
        cleaned = cleaned.replace(prefix, "")
    return cleaned


def is_tonic_roman(label: str | None) -> bool:
    cleaned = normalize_roman_label(label)
    return cleaned.startswith("I") and not cleaned.startswith("II")


def is_dominant_roman(label: str | None) -> bool:
    cleaned = normalize_roman_label(label)
    return cleaned.startswith("V") and not cleaned.startswith("VI")


def is_submediant_roman(label: str | None) -> bool:
    cleaned = normalize_roman_label(label)
    return cleaned.upper().startswith("VI")
