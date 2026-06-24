from __future__ import annotations

from itertools import product

import numpy as np
import torch

from chorale.data.score_tokenizer import ScoreTokenizer, VOICE_NAMES, VOICE_RANGES


def apply_constraint_reranking(
    tokens: np.ndarray,
    logits: torch.Tensor | np.ndarray,
    target_mask: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    harmonic_labels: dict | None = None,
    top_k: int = 4,
    rule_weight: float = 1.0,
    harmony_weight: float = 0.25,
    temporal_weight: float = 1.0,
    seventh_weight: float = 1.0,
) -> np.ndarray:
    """Rerank top-k pitch candidates with symbolic vertical and temporal costs."""
    reranked = tokenizer.sanitize_for_export(tokens, length=length)
    if length is None:
        length = reranked.shape[0]
    length = min(int(length), reranked.shape[0])
    logits_np = logits.detach().cpu().numpy() if torch.is_tensor(logits) else np.asarray(logits)
    target_mask = np.asarray(target_mask, dtype=bool)
    if logits_np.ndim == 4:
        logits_np = logits_np[0]
    if target_mask.ndim == 3:
        target_mask = target_mask[0]
    midi = tokenizer.expand_holds(reranked, length=length)
    chord_roots = None
    is_seventh = None
    is_dominant = None
    key_tonic_pc = None
    if harmonic_labels:
        chord_roots = np.asarray(harmonic_labels.get("chord_roots", np.full(length, -1)))[:length]
        is_seventh = np.asarray(harmonic_labels.get("is_seventh_chord", np.zeros(length, dtype=bool)))[:length]
        is_dominant = np.asarray(harmonic_labels.get("is_dominant_function", np.zeros(length, dtype=bool)))[:length]
        key_tonic_pc = _safe_pc(harmonic_labels.get("key_tonic_pc"))

    for t in range(length):
        voices_to_fill = [v for v in range(4) if target_mask[t, v]]
        if not voices_to_fill:
            continue
        row = midi[t].copy()
        candidate_lists = [
            top_pitch_candidates(logits_np[t, voice_idx], tokenizer, top_k=top_k)
            for voice_idx in voices_to_fill
        ]
        if not all(candidate_lists):
            continue
        best_score = float("inf")
        best_row = row.copy()
        for combo in product(*candidate_lists):
            candidate_row = row.copy()
            nll_cost = 0.0
            for voice_idx, (token, midi_pitch, nll) in zip(voices_to_fill, combo):
                candidate_row[voice_idx] = midi_pitch
                nll_cost += float(nll)
            rule_cost = local_rule_cost(candidate_row)
            temporal_cost = temporal_voice_leading_cost(
                midi[t - 1] if t > 0 else None,
                candidate_row,
                midi[t + 1] if t + 1 < length else None,
                key_tonic_pc=key_tonic_pc,
            )
            seventh_cost = seventh_resolution_transition_cost(
                midi[t - 1] if t > 0 else None,
                candidate_row,
                midi[t + 1] if t + 1 < length else None,
                previous_chord_root=int(chord_roots[t - 1]) if chord_roots is not None and t > 0 else -1,
                current_chord_root=int(chord_roots[t]) if chord_roots is not None else -1,
                previous_is_seventh=bool(is_seventh[t - 1]) if is_seventh is not None and t > 0 else False,
                current_is_seventh=bool(is_seventh[t]) if is_seventh is not None else False,
            )
            harmony_cost = 0.0
            if chord_roots is not None:
                harmony_cost = local_harmony_cost(
                    candidate_row,
                    int(chord_roots[t]),
                    bool(is_seventh[t]) if is_seventh is not None else False,
                    bool(is_dominant[t]) if is_dominant is not None else False,
                )
            score = (
                nll_cost
                + rule_weight * rule_cost
                + harmony_weight * harmony_cost
                + temporal_weight * temporal_cost
                + seventh_weight * seventh_cost
            )
            if score < best_score:
                best_score = score
                best_row = candidate_row
        for voice_idx in voices_to_fill:
            if not np.isnan(best_row[voice_idx]):
                reranked[t, voice_idx] = tokenizer.midi_to_token(int(round(best_row[voice_idx])))
        midi[t] = best_row
    return reranked


def apply_rule_guided_decoding(tokens: np.ndarray, tokenizer: ScoreTokenizer, length: int | None = None) -> np.ndarray:
    """Apply lightweight symbolic repairs after neural decoding.

    This is intentionally conservative: it repairs range, crossing, and adjacent
    spacing issues in the produced score. It is not a substitute for a complete
    constraint solver, and the evaluation report still counts any remaining
    violations.
    """
    repaired = tokenizer.sanitize_for_export(tokens, length=length)
    if length is None:
        length = repaired.shape[0]
    length = min(int(length), repaired.shape[0])
    midi = tokenizer.expand_holds(repaired, length=length)

    for t in range(length):
        row = midi[t].copy()
        if np.isnan(row[0]):
            continue

        for voice_idx, voice_name in enumerate(VOICE_NAMES):
            if np.isnan(row[voice_idx]):
                continue
            low, high = VOICE_RANGES[voice_name]
            row[voice_idx] = float(np.clip(row[voice_idx], low, high))

        row = _repair_crossing(row)
        row = _repair_spacing(row)

        for voice_idx, pitch in enumerate(row):
            token = int(repaired[t, voice_idx])
            if token == tokenizer.HOLD or np.isnan(pitch):
                continue
            repaired[t, voice_idx] = tokenizer.midi_to_token(int(round(pitch)))

    return repaired


def top_pitch_candidates(logits: np.ndarray, tokenizer: ScoreTokenizer, top_k: int = 4) -> list[tuple[int, int, float]]:
    logits = np.asarray(logits, dtype=np.float64)
    order = np.argsort(logits)[::-1]
    candidates: list[tuple[int, int, float]] = []
    normalizer = float(np.max(logits))
    log_probs = logits - normalizer - np.log(np.exp(logits - normalizer).sum())
    for token in order:
        midi = tokenizer.token_to_midi(int(token))
        if midi is None:
            continue
        candidates.append((int(token), int(midi), float(-log_probs[int(token)])))
        if len(candidates) >= max(1, int(top_k)):
            break
    return candidates


def local_rule_cost(row: np.ndarray) -> float:
    cost = 0.0
    for voice_idx, voice_name in enumerate(VOICE_NAMES):
        pitch = row[voice_idx]
        if np.isnan(pitch):
            continue
        low, high = VOICE_RANGES[voice_name]
        if pitch < low:
            cost += (low - pitch) / 6.0 + 2.0
        if pitch > high:
            cost += (pitch - high) / 6.0 + 2.0
    for upper, lower in ((0, 1), (1, 2), (2, 3)):
        if np.isnan(row[upper]) or np.isnan(row[lower]):
            continue
        interval = row[upper] - row[lower]
        if interval < 0:
            cost += 8.0 + abs(interval)
    spacing_limits = {(0, 1): 12, (1, 2): 12, (2, 3): 19}
    for (upper, lower), limit in spacing_limits.items():
        if np.isnan(row[upper]) or np.isnan(row[lower]):
            continue
        interval = row[upper] - row[lower]
        if interval > limit:
            cost += 2.0 + (interval - limit) / 6.0
    return float(cost)


def local_harmony_cost(row: np.ndarray, chord_root: int, is_seventh: bool, is_dominant: bool) -> float:
    pitches = [int(p) for p in row if not np.isnan(p)]
    if len(pitches) < 3 or chord_root < 0:
        return 0.0
    pcs = {pitch % 12 for pitch in pitches}
    root = chord_root % 12
    cost = 0.0
    if root not in pcs:
        cost += 1.5
    third_options = {(root + 3) % 12, (root + 4) % 12}
    fifth = (root + 7) % 12
    if not (pcs & third_options):
        cost += 0.75
    if fifth not in pcs:
        cost += 0.35
    if is_seventh and (root + 10) % 12 not in pcs and (root + 11) % 12 not in pcs:
        cost += 0.75
    if is_dominant and fifth not in pcs:
        cost += 0.5
    return float(cost)


def temporal_voice_leading_cost(
    previous_row: np.ndarray | None,
    current_row: np.ndarray,
    next_row: np.ndarray | None = None,
    key_tonic_pc: int | None = None,
) -> float:
    """Score temporal motion that cannot be seen from a single vertical sonority."""
    cost = 0.0
    if previous_row is not None:
        for upper, lower in _voice_pairs():
            if _has_pitch(previous_row, upper, lower) and _has_pitch(current_row, upper, lower):
                previous_interval = int(abs(previous_row[upper] - previous_row[lower])) % 12
                current_interval = int(abs(current_row[upper] - current_row[lower])) % 12
                upper_motion = current_row[upper] - previous_row[upper]
                lower_motion = current_row[lower] - previous_row[lower]
                same_direction = _sign(upper_motion) == _sign(lower_motion) and _sign(upper_motion) != 0
                if same_direction and current_interval in {0, 7}:
                    if previous_interval == current_interval:
                        cost += 7.0 if current_interval == 0 else 5.0
                    elif (upper, lower) == (0, 3) and abs(upper_motion) > 2:
                        cost += 2.5 if current_interval == 0 else 1.75

        for voice_idx in range(4):
            if not _has_pitch(previous_row, voice_idx) or not _has_pitch(current_row, voice_idx):
                continue
            leap = float(current_row[voice_idx] - previous_row[voice_idx])
            if abs(leap) <= 7:
                continue
            if next_row is not None and _has_pitch(next_row, voice_idx):
                recovery = float(next_row[voice_idx] - current_row[voice_idx])
                if not (_sign(recovery) == -_sign(leap) and 0 < abs(recovery) <= 2):
                    cost += 1.5 + (abs(leap) - 7.0) / 6.0
            else:
                cost += 0.35 + (abs(leap) - 7.0) / 12.0

        if key_tonic_pc is not None:
            leading_pc = (int(key_tonic_pc) - 1) % 12
            tonic_pc = int(key_tonic_pc) % 12
            for voice_idx in range(4):
                if not _has_pitch(previous_row, voice_idx) or not _has_pitch(current_row, voice_idx):
                    continue
                if int(previous_row[voice_idx]) % 12 == leading_pc and int(current_row[voice_idx]) % 12 != tonic_pc:
                    cost += 1.75

    if key_tonic_pc is not None and next_row is not None:
        leading_pc = (int(key_tonic_pc) - 1) % 12
        tonic_pc = int(key_tonic_pc) % 12
        for voice_idx in range(4):
            if not _has_pitch(current_row, voice_idx) or not _has_pitch(next_row, voice_idx):
                continue
            if int(current_row[voice_idx]) % 12 == leading_pc and int(next_row[voice_idx]) % 12 != tonic_pc:
                cost += 0.75
    return float(cost)


def seventh_resolution_transition_cost(
    previous_row: np.ndarray | None,
    current_row: np.ndarray,
    next_row: np.ndarray | None = None,
    previous_chord_root: int = -1,
    current_chord_root: int = -1,
    previous_is_seventh: bool = False,
    current_is_seventh: bool = False,
) -> float:
    """Score only confident chordal-seventh resolution evidence.

    The detector intentionally requires an available seventh-chord label and a
    root pitch class. Unknown harmonic labels produce no penalty.
    """
    cost = 0.0
    if previous_row is not None and previous_is_seventh and previous_chord_root >= 0:
        cost += _seventh_resolution_cost_between(previous_row, current_row, previous_chord_root, strong=True)
    if next_row is not None and current_is_seventh and current_chord_root >= 0:
        cost += _seventh_resolution_cost_between(current_row, next_row, current_chord_root, strong=False)
    return float(cost)


def _seventh_resolution_cost_between(
    chord_row: np.ndarray,
    resolution_row: np.ndarray,
    chord_root: int,
    strong: bool,
) -> float:
    seventh_pcs = {((int(chord_root) + 10) % 12), ((int(chord_root) + 11) % 12)}
    cost = 0.0
    for voice_idx in range(4):
        if not _has_pitch(chord_row, voice_idx) or not _has_pitch(resolution_row, voice_idx):
            continue
        if int(chord_row[voice_idx]) % 12 not in seventh_pcs:
            continue
        motion = int(round(resolution_row[voice_idx] - chord_row[voice_idx]))
        if motion not in {-1, -2}:
            cost += 4.0 if strong else 1.25
    return float(cost)


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


def _safe_pc(value: object) -> int | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value)
        if arr.ndim > 0:
            value = arr.reshape(-1)[0]
        pc = int(value) % 12
    except (TypeError, ValueError, OverflowError):
        return None
    return pc


def _repair_crossing(row: np.ndarray) -> np.ndarray:
    fixed = row.copy()
    for upper, lower in ((0, 1), (1, 2), (2, 3)):
        if np.isnan(fixed[upper]) or np.isnan(fixed[lower]):
            continue
        if fixed[upper] < fixed[lower]:
            fixed[lower] = fixed[upper] - 3
    return fixed


def _repair_spacing(row: np.ndarray) -> np.ndarray:
    fixed = row.copy()
    limits = {(0, 1): 12, (1, 2): 12, (2, 3): 19}
    for (upper, lower), limit in limits.items():
        if np.isnan(fixed[upper]) or np.isnan(fixed[lower]):
            continue
        if fixed[upper] - fixed[lower] > limit:
            fixed[lower] = fixed[upper] - limit
    for voice_idx, voice_name in enumerate(VOICE_NAMES):
        if np.isnan(fixed[voice_idx]):
            continue
        low, high = VOICE_RANGES[voice_name]
        fixed[voice_idx] = float(np.clip(fixed[voice_idx], low, high))
    return fixed
