from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer, VOICE_NAMES, VOICE_RANGES

VOICE_PAIRS = [(0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)]
ADJACENT_PAIRS = [(0, 1), (1, 2), (2, 3)]
VOICE_PAIR_NAMES = {
    (0, 1): "soprano and alto",
    (0, 2): "soprano and tenor",
    (0, 3): "soprano and bass",
    (1, 2): "alto and tenor",
    (1, 3): "alto and bass",
    (2, 3): "tenor and bass",
}


@dataclass
class RuleViolation:
    rule: str
    timestep: int
    measure: int
    beat: float
    message: str
    penalty: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


def location_text(timestep: int, grid: float) -> tuple[int, float, str]:
    position = timestep * grid
    measure = int(position // 4.0) + 1
    beat = (position % 4.0) + 1.0
    beat_text = int(beat) if abs(beat - round(beat)) < 1e-6 else round(beat, 3)
    return measure, float(beat), f"m. {measure} beat {beat_text}"


def tokens_to_midi_matrix(tokens: np.ndarray, tokenizer: ScoreTokenizer, length: int | None = None) -> np.ndarray:
    return tokenizer.expand_holds(tokens, length=length)


def check_voice_ranges(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    ranges: dict[str, tuple[int, int]] | None = None,
) -> list[RuleViolation]:
    ranges = ranges or VOICE_RANGES
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    violations: list[RuleViolation] = []
    for t in range(midi.shape[0]):
        for v, voice in enumerate(VOICE_NAMES):
            pitch = midi[t, v]
            if np.isnan(pitch):
                continue
            low, high = ranges[voice]
            if pitch < low or pitch > high:
                measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule="voice_range",
                        timestep=t,
                        measure=measure,
                        beat=beat,
                        message=f"{loc}: {voice} range violation ({int(pitch)} outside {low}-{high})",
                    )
                )
    return violations


def check_voice_crossing(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
) -> list[RuleViolation]:
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    violations: list[RuleViolation] = []
    for t in range(midi.shape[0]):
        for upper, lower in ADJACENT_PAIRS:
            if np.isnan(midi[t, upper]) or np.isnan(midi[t, lower]):
                continue
            if midi[t, upper] < midi[t, lower]:
                measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule="voice_crossing",
                        timestep=t,
                        measure=measure,
                        beat=beat,
                        message=f"{loc}: voice crossing between {VOICE_PAIR_NAMES[(upper, lower)]}",
                    )
                )
    return violations


def check_spacing(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
) -> list[RuleViolation]:
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    limits = {(0, 1): 12, (1, 2): 12, (2, 3): 19}
    violations: list[RuleViolation] = []
    for t in range(midi.shape[0]):
        for pair, limit in limits.items():
            upper, lower = pair
            if np.isnan(midi[t, upper]) or np.isnan(midi[t, lower]):
                continue
            distance = midi[t, upper] - midi[t, lower]
            if distance > limit:
                measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule="spacing",
                        timestep=t,
                        measure=measure,
                        beat=beat,
                        message=(
                            f"{loc}: spacing violation between {VOICE_PAIR_NAMES[pair]} "
                            f"({int(distance)} semitones > {limit})"
                        ),
                    )
                )
    return violations


def check_parallel_fifths(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
) -> list[RuleViolation]:
    return _check_parallel_perfect_interval(tokens, tokenizer, interval_class=7, rule_name="parallel_fifth", length=length)


def check_parallel_octaves(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
) -> list[RuleViolation]:
    return _check_parallel_perfect_interval(tokens, tokenizer, interval_class=0, rule_name="parallel_octave", length=length)


def _check_parallel_perfect_interval(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    interval_class: int,
    rule_name: str,
    length: int | None = None,
) -> list[RuleViolation]:
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    violations: list[RuleViolation] = []
    label = "fifth" if interval_class == 7 else "octave"
    for t in range(1, midi.shape[0]):
        for pair in VOICE_PAIRS:
            a, b = pair
            values = (midi[t - 1, a], midi[t - 1, b], midi[t, a], midi[t, b])
            if any(np.isnan(x) for x in values):
                continue
            prev_a, prev_b, cur_a, cur_b = values
            motion_a = cur_a - prev_a
            motion_b = cur_b - prev_b
            if motion_a == 0 or motion_b == 0 or np.sign(motion_a) != np.sign(motion_b):
                continue
            prev_interval = abs(prev_a - prev_b)
            cur_interval = abs(cur_a - cur_b)
            if _is_interval_class(prev_interval, interval_class) and _is_interval_class(cur_interval, interval_class):
                measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule=rule_name,
                        timestep=t,
                        measure=measure,
                        beat=beat,
                        message=f"{loc}: parallel {label} between {VOICE_PAIR_NAMES[pair]}",
                    )
                )
    return violations


def check_hidden_direct_intervals(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
) -> list[RuleViolation]:
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    violations: list[RuleViolation] = []
    pair = (0, 3)
    for t in range(1, midi.shape[0]):
        prev_s, prev_b, cur_s, cur_b = midi[t - 1, 0], midi[t - 1, 3], midi[t, 0], midi[t, 3]
        if any(np.isnan(x) for x in (prev_s, prev_b, cur_s, cur_b)):
            continue
        soprano_motion = cur_s - prev_s
        bass_motion = cur_b - prev_b
        if soprano_motion == 0 or bass_motion == 0 or np.sign(soprano_motion) != np.sign(bass_motion):
            continue
        if abs(soprano_motion) <= 2:
            continue
        cur_interval = abs(cur_s - cur_b)
        prev_interval = abs(prev_s - prev_b)
        if (_is_interval_class(cur_interval, 7) or _is_interval_class(cur_interval, 0)) and not (
            _is_interval_class(prev_interval, 7) or _is_interval_class(prev_interval, 0)
        ):
            label = "fifth" if _is_interval_class(cur_interval, 7) else "octave"
            measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
            violations.append(
                RuleViolation(
                    rule=f"hidden_direct_{label}",
                    timestep=t,
                    measure=measure,
                    beat=beat,
                    penalty=0.5,
                    message=f"{loc}: hidden/direct {label} between {VOICE_PAIR_NAMES[pair]}",
                )
            )
    return violations


def check_leading_tone_resolution(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    key_tonic_pc: int = 0,
    length: int | None = None,
) -> list[RuleViolation]:
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    leading_pc = (int(key_tonic_pc) - 1) % 12
    tonic_pc = int(key_tonic_pc) % 12
    violations: list[RuleViolation] = []
    for v, voice in enumerate(VOICE_NAMES):
        events = pitch_events(midi[:, v])
        for event_idx, (t, cur) in enumerate(events[:-1]):
            next_pitch = events[event_idx + 1][1]
            if cur is None:
                continue
            if int(cur) % 12 == leading_pc and (next_pitch is None or int(next_pitch) % 12 != tonic_pc):
                measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule="leading_tone_resolution",
                        timestep=t,
                        measure=measure,
                        beat=beat,
                        penalty=0.75,
                        message=f"{loc}: approximate leading tone in {voice} does not resolve to tonic",
                    )
                )
    return violations


def pitch_events(voice_midi: np.ndarray) -> list[tuple[int, int | None]]:
    """Return event starts after collapsing held repetitions.

    The fixed-grid representation expands a held note over many timesteps.
    Resolution rules should be evaluated when a voice actually changes pitch
    or moves to rest, not once per quantized frame of the same sustained note.
    """
    events: list[tuple[int, int | None]] = []
    previous: int | None | str = "START"
    for timestep, raw_pitch in enumerate(voice_midi):
        current: int | None
        if np.isnan(raw_pitch):
            current = None
        else:
            current = int(round(float(raw_pitch)))
        if current != previous:
            events.append((int(timestep), current))
            previous = current
    return events


def check_melodic_leap_recovery(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
) -> list[RuleViolation]:
    midi = tokens_to_midi_matrix(tokens, tokenizer, length)
    violations: list[RuleViolation] = []
    for t in range(1, midi.shape[0] - 1):
        for v, voice in enumerate(VOICE_NAMES):
            prev_pitch, cur_pitch, next_pitch = midi[t - 1, v], midi[t, v], midi[t + 1, v]
            if any(np.isnan(x) for x in (prev_pitch, cur_pitch, next_pitch)):
                continue
            leap = cur_pitch - prev_pitch
            recovery = next_pitch - cur_pitch
            if abs(leap) > 7 and not (np.sign(leap) == -np.sign(recovery) and abs(recovery) <= 2):
                measure, beat, loc = location_text(t, tokenizer.grid_quarter_length)
                violations.append(
                    RuleViolation(
                        rule="melodic_leap_recovery",
                        timestep=t,
                        measure=measure,
                        beat=beat,
                        penalty=0.5,
                        message=f"{loc}: {voice} large leap is not recovered by contrary stepwise motion",
                    )
                )
    return violations


def evaluate_voice_leading(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    key_tonic_pc: int = 0,
) -> dict:
    checks: list[Iterable[RuleViolation]] = [
        check_voice_ranges(tokens, tokenizer, length),
        check_voice_crossing(tokens, tokenizer, length),
        check_spacing(tokens, tokenizer, length),
        check_parallel_fifths(tokens, tokenizer, length),
        check_parallel_octaves(tokens, tokenizer, length),
        check_hidden_direct_intervals(tokens, tokenizer, length),
        check_leading_tone_resolution(tokens, tokenizer, key_tonic_pc=key_tonic_pc, length=length),
        check_melodic_leap_recovery(tokens, tokenizer, length),
    ]
    violations = [item for group in checks for item in group]
    counts = Counter(v.rule for v in violations)
    total_steps = int(length if length is not None else np.asarray(tokens).shape[0])
    penalty = float(sum(v.penalty for v in violations))
    return {
        "total_penalty": penalty,
        "total_violations": int(len(violations)),
        "counts": dict(counts),
        "violations_per_100_timesteps": 100.0 * len(violations) / max(1, total_steps),
        "violations": [v.to_dict() for v in violations],
        "explanations": [v.message for v in violations],
        "limitations": [
            "Harmony-level seventh and cadence checks are evaluated separately when automatic harmonic labels are available.",
        ],
    }


def _is_interval_class(interval: float, interval_class: int) -> bool:
    interval_int = int(round(abs(interval)))
    if interval_int == 0:
        return interval_class == 0
    return interval_int % 12 == interval_class
