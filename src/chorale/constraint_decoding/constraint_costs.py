from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from chorale.data.score_tokenizer import VOICE_NAMES, VOICE_RANGES


@dataclass(frozen=True)
class ConstraintViolation:
    name: str
    severity: float
    hard: bool = False


@dataclass(frozen=True)
class ConstraintWeights:
    melodic_smoothness: float = 0.6
    common_tone_retention: float = 0.25
    contrary_motion_preference: float = 0.2
    cadence_strength: float = 0.5
    stylistic_similarity_proxy: float = 0.2
    singability_proxy: float = 0.35

    @classmethod
    def from_config(cls, values: dict | None) -> "ConstraintWeights":
        values = values or {}
        allowed = {field for field in cls.__dataclass_fields__}
        return cls(**{key: float(value) for key, value in values.items() if key in allowed})


def hard_constraint_violations(
    previous_row: np.ndarray | None,
    current_row: np.ndarray,
    next_row: np.ndarray | None = None,
    *,
    key_tonic_pc: int | None = None,
    chord_root: int = -1,
    is_seventh_chord: bool = False,
    is_phrase_end: bool = False,
    enabled: Iterable[str] | None = None,
) -> list[ConstraintViolation]:
    enabled_set = set(enabled or ())
    if not enabled_set:
        enabled_set = {
            "voice_range",
            "voice_crossing",
            "adjacent_spacing",
            "parallel_fifths",
            "parallel_octaves",
            "unresolved_chordal_seventh",
            "leading_tone_resolution",
            "final_cadence_legality",
        }
    violations: list[ConstraintViolation] = []
    if "voice_range" in enabled_set:
        violations.extend(check_voice_range(current_row))
    if "voice_crossing" in enabled_set:
        violations.extend(check_voice_crossing(current_row))
    if "adjacent_spacing" in enabled_set:
        violations.extend(check_adjacent_spacing(current_row))
    if previous_row is not None:
        if "parallel_fifths" in enabled_set:
            violations.extend(check_parallel_interval(previous_row, current_row, interval_pc=7, name="parallel_fifths"))
        if "parallel_octaves" in enabled_set:
            violations.extend(check_parallel_interval(previous_row, current_row, interval_pc=0, name="parallel_octaves"))
        if "leading_tone_resolution" in enabled_set and key_tonic_pc is not None:
            violations.extend(check_leading_tone(previous_row, current_row, key_tonic_pc))
    if (
        "unresolved_chordal_seventh" in enabled_set
        and is_seventh_chord
        and chord_root >= 0
        and next_row is not None
    ):
        violations.extend(check_chordal_seventh_resolution(current_row, next_row, chord_root))
    if "final_cadence_legality" in enabled_set and is_phrase_end and key_tonic_pc is not None:
        violations.extend(check_final_cadence(current_row, key_tonic_pc))
    return violations


def soft_constraint_cost(
    previous_row: np.ndarray | None,
    current_row: np.ndarray,
    next_row: np.ndarray | None = None,
    *,
    key_tonic_pc: int | None = None,
    is_phrase_end: bool = False,
    weights: ConstraintWeights | None = None,
) -> float:
    weights = weights or ConstraintWeights()
    cost = 0.0
    cost += weights.singability_proxy * singability_cost(previous_row, current_row, next_row)
    cost += weights.melodic_smoothness * melodic_smoothness_cost(previous_row, current_row)
    cost += weights.common_tone_retention * common_tone_cost(previous_row, current_row)
    cost += weights.contrary_motion_preference * contrary_motion_cost(previous_row, current_row)
    cost += weights.stylistic_similarity_proxy * stylistic_spacing_cost(current_row)
    if is_phrase_end and key_tonic_pc is not None:
        cost += weights.cadence_strength * cadence_strength_cost(current_row, key_tonic_pc)
    return float(cost)


def score_candidate_transition(
    previous_row: np.ndarray | None,
    current_row: np.ndarray,
    next_row: np.ndarray | None = None,
    *,
    key_tonic_pc: int | None = None,
    chord_root: int = -1,
    is_seventh_chord: bool = False,
    is_phrase_end: bool = False,
    hard_constraints: Iterable[str] | None = None,
    weights: ConstraintWeights | None = None,
    hard_violation_cost: float = 1_000_000.0,
) -> tuple[bool, float, list[ConstraintViolation]]:
    violations = hard_constraint_violations(
        previous_row,
        current_row,
        next_row,
        key_tonic_pc=key_tonic_pc,
        chord_root=chord_root,
        is_seventh_chord=is_seventh_chord,
        is_phrase_end=is_phrase_end,
        enabled=hard_constraints,
    )
    if violations:
        return False, float(hard_violation_cost + sum(v.severity for v in violations)), violations
    return True, soft_constraint_cost(
        previous_row,
        current_row,
        next_row,
        key_tonic_pc=key_tonic_pc,
        is_phrase_end=is_phrase_end,
        weights=weights,
    ), []


def check_voice_range(row: np.ndarray) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for idx, name in enumerate(VOICE_NAMES):
        pitch = row[idx]
        if np.isnan(pitch):
            continue
        low, high = VOICE_RANGES[name]
        if pitch < low or pitch > high:
            violations.append(ConstraintViolation("voice_range", abs(float(np.clip(pitch, low, high) - pitch)), True))
    return violations


def check_voice_crossing(row: np.ndarray) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for upper, lower in ((0, 1), (1, 2), (2, 3)):
        if _has_pitch(row, upper, lower) and row[upper] < row[lower]:
            violations.append(ConstraintViolation("voice_crossing", float(row[lower] - row[upper] + 1.0), True))
    return violations


def check_adjacent_spacing(row: np.ndarray) -> list[ConstraintViolation]:
    limits = {(0, 1): 12, (1, 2): 12, (2, 3): 19}
    violations: list[ConstraintViolation] = []
    for (upper, lower), limit in limits.items():
        if _has_pitch(row, upper, lower) and row[upper] - row[lower] > limit:
            violations.append(ConstraintViolation("adjacent_spacing", float(row[upper] - row[lower] - limit), True))
    return violations


def check_parallel_interval(
    previous_row: np.ndarray,
    current_row: np.ndarray,
    *,
    interval_pc: int,
    name: str,
) -> list[ConstraintViolation]:
    violations: list[ConstraintViolation] = []
    for upper, lower in _voice_pairs():
        if not (_has_pitch(previous_row, upper, lower) and _has_pitch(current_row, upper, lower)):
            continue
        previous_interval = int(round(abs(previous_row[upper] - previous_row[lower]))) % 12
        current_interval = int(round(abs(current_row[upper] - current_row[lower]))) % 12
        upper_motion = current_row[upper] - previous_row[upper]
        lower_motion = current_row[lower] - previous_row[lower]
        if previous_interval == interval_pc and current_interval == interval_pc and _same_nonzero_direction(upper_motion, lower_motion):
            violations.append(ConstraintViolation(name, 1.0 + abs(float(upper_motion + lower_motion)) / 12.0, True))
    return violations


def check_chordal_seventh_resolution(row: np.ndarray, next_row: np.ndarray, chord_root: int) -> list[ConstraintViolation]:
    seventh_pcs = {(int(chord_root) + 10) % 12, (int(chord_root) + 11) % 12}
    violations: list[ConstraintViolation] = []
    for voice_idx in range(4):
        if not _has_pitch(row, voice_idx) or not _has_pitch(next_row, voice_idx):
            continue
        if int(row[voice_idx]) % 12 in seventh_pcs and int(round(next_row[voice_idx] - row[voice_idx])) not in {-1, -2}:
            violations.append(ConstraintViolation("unresolved_chordal_seventh", 1.0, True))
    return violations


def check_leading_tone(previous_row: np.ndarray, current_row: np.ndarray, key_tonic_pc: int) -> list[ConstraintViolation]:
    leading_pc = (int(key_tonic_pc) - 1) % 12
    tonic_pc = int(key_tonic_pc) % 12
    violations: list[ConstraintViolation] = []
    for voice_idx in range(4):
        if not _has_pitch(previous_row, voice_idx) or not _has_pitch(current_row, voice_idx):
            continue
        if int(previous_row[voice_idx]) % 12 == leading_pc and int(current_row[voice_idx]) % 12 != tonic_pc:
            violations.append(ConstraintViolation("leading_tone_resolution", 1.0, True))
    return violations


def check_final_cadence(row: np.ndarray, key_tonic_pc: int) -> list[ConstraintViolation]:
    pitches = [int(pitch) for pitch in row if not np.isnan(pitch)]
    if len(pitches) < 3:
        return []
    tonic = int(key_tonic_pc) % 12
    pcs = {pitch % 12 for pitch in pitches}
    tonic_triad_major_minor = {tonic, (tonic + 3) % 12, (tonic + 4) % 12, (tonic + 7) % 12}
    if tonic not in pcs or not pcs.issubset(tonic_triad_major_minor):
        return [ConstraintViolation("final_cadence_legality", 1.0, True)]
    return []


def melodic_smoothness_cost(previous_row: np.ndarray | None, row: np.ndarray) -> float:
    if previous_row is None:
        return 0.0
    cost = 0.0
    for voice_idx in range(4):
        if _has_pitch(previous_row, voice_idx) and _has_pitch(row, voice_idx):
            leap = abs(float(row[voice_idx] - previous_row[voice_idx]))
            if leap > 7:
                cost += (leap - 7.0) / 6.0
    return cost


def singability_cost(previous_row: np.ndarray | None, row: np.ndarray, next_row: np.ndarray | None = None) -> float:
    cost = melodic_smoothness_cost(previous_row, row)
    if next_row is not None:
        cost += 0.5 * melodic_smoothness_cost(row, next_row)
    return cost


def common_tone_cost(previous_row: np.ndarray | None, row: np.ndarray) -> float:
    if previous_row is None:
        return 0.0
    prev_pcs = {int(pitch) % 12 for pitch in previous_row if not np.isnan(pitch)}
    pcs = {int(pitch) % 12 for pitch in row if not np.isnan(pitch)}
    if not prev_pcs or not pcs:
        return 0.0
    return 1.0 - (len(prev_pcs & pcs) / max(1, min(len(prev_pcs), len(pcs))))


def contrary_motion_cost(previous_row: np.ndarray | None, row: np.ndarray) -> float:
    if previous_row is None or not (_has_pitch(previous_row, 0, 3) and _has_pitch(row, 0, 3)):
        return 0.0
    soprano_motion = row[0] - previous_row[0]
    bass_motion = row[3] - previous_row[3]
    if _same_nonzero_direction(soprano_motion, bass_motion):
        return 0.5
    return 0.0


def stylistic_spacing_cost(row: np.ndarray) -> float:
    if not all(_has_pitch(row, idx) for idx in range(4)):
        return 0.0
    total_span = row[0] - row[3]
    if total_span < 12:
        return (12.0 - float(total_span)) / 12.0
    if total_span > 36:
        return (float(total_span) - 36.0) / 12.0
    return 0.0


def cadence_strength_cost(row: np.ndarray, key_tonic_pc: int) -> float:
    pitches = [int(pitch) for pitch in row if not np.isnan(pitch)]
    if len(pitches) < 3:
        return 0.0
    tonic = int(key_tonic_pc) % 12
    pcs = {pitch % 12 for pitch in pitches}
    cost = 0.0 if tonic in pcs else 1.0
    if (tonic + 7) % 12 not in pcs:
        cost += 0.5
    if not ({(tonic + 3) % 12, (tonic + 4) % 12} & pcs):
        cost += 0.5
    return cost


def _voice_pairs() -> tuple[tuple[int, int], ...]:
    return ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3))


def _has_pitch(row: np.ndarray, *indices: int) -> bool:
    return all(not np.isnan(row[index]) for index in indices)


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _same_nonzero_direction(left: float, right: float) -> bool:
    return _sign(left) == _sign(right) and _sign(left) != 0

