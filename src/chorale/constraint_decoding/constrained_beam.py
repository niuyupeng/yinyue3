from __future__ import annotations

from itertools import product

import numpy as np
import torch

from chorale.constraint_decoding.constraint_costs import ConstraintWeights, score_candidate_transition
from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.theory.rule_guided_decoding import top_pitch_candidates


def apply_cih_constrained_beam_search(
    tokens: np.ndarray,
    logits: torch.Tensor | np.ndarray,
    target_mask: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    harmonic_labels: dict | None = None,
    beam_size: int = 8,
    top_k: int = 12,
    max_row_candidates: int = 96,
    lambda_rule: float = 1.0,
    hard_constraints: list[str] | None = None,
    soft_constraint_weights: dict | None = None,
    hard_violation_cost: float = 1_000_000.0,
) -> np.ndarray:
    """CIH-S2S constrained beam search.

    Objective: neural negative log likelihood + lambda_rule * symbolic cost.
    Hard constraints are filtered by assigning a prohibitive cost and skipping
    the candidate when at least one valid alternative exists.
    """
    decoded = tokenizer.sanitize_for_export(tokens, length=length)
    if length is None:
        length = decoded.shape[0]
    length = min(int(length), decoded.shape[0])
    logits_np = logits.detach().cpu().numpy() if torch.is_tensor(logits) else np.asarray(logits)
    if logits_np.ndim == 4:
        logits_np = logits_np[0]
    target_mask = np.asarray(target_mask, dtype=bool)
    if target_mask.ndim == 3:
        target_mask = target_mask[0]

    beam_size = max(1, int(beam_size))
    top_k = max(1, int(top_k))
    max_row_candidates = max(1, int(max_row_candidates))
    weights = ConstraintWeights.from_config(soft_constraint_weights)

    seed_midi = tokenizer.expand_holds(decoded, length=length)
    chord_roots, is_seventh, is_phrase_end, key_tonic_pc = _extract_harmony(harmonic_labels, length)
    beam: list[tuple[float, np.ndarray, np.ndarray | None]] = [(0.0, decoded.copy(), None)]
    for t in range(length):
        voices_to_fill = [voice for voice in range(4) if target_mask[t, voice]]
        next_beam: list[tuple[float, np.ndarray, np.ndarray]] = []
        fallback_beam: list[tuple[float, np.ndarray, np.ndarray]] = []
        for prefix_score, prefix_tokens, previous_row in beam:
            row_candidates = cih_row_candidates(
                seed_midi[t],
                logits_np[t],
                voices_to_fill,
                tokenizer,
                top_k=top_k,
                max_row_candidates=max_row_candidates,
            )
            for row_tokens, candidate_row, nll_cost in row_candidates:
                next_row = seed_midi[t + 1] if t + 1 < length else None
                feasible, symbolic_cost, _ = score_candidate_transition(
                    previous_row,
                    candidate_row,
                    next_row,
                    key_tonic_pc=key_tonic_pc,
                    chord_root=int(chord_roots[t]) if chord_roots is not None else -1,
                    is_seventh_chord=bool(is_seventh[t]) if is_seventh is not None else False,
                    is_phrase_end=bool(is_phrase_end[t]) if is_phrase_end is not None else False,
                    hard_constraints=hard_constraints,
                    weights=weights,
                    hard_violation_cost=hard_violation_cost,
                )
                candidate_tokens = prefix_tokens.copy()
                for voice_idx, token in row_tokens.items():
                    candidate_tokens[t, voice_idx] = token
                score = prefix_score + float(nll_cost) + float(lambda_rule) * float(symbolic_cost)
                candidate = (score, candidate_tokens, candidate_row)
                if feasible:
                    next_beam.append(candidate)
                else:
                    fallback_beam.append(candidate)
        if not next_beam:
            next_beam = fallback_beam
        next_beam.sort(key=lambda item: item[0])
        beam = next_beam[:beam_size]
        if not beam:
            return decoded
    return beam[0][1]


def cih_row_candidates(
    seed_row: np.ndarray,
    row_logits: np.ndarray,
    voices_to_fill: list[int],
    tokenizer: ScoreTokenizer,
    top_k: int,
    max_row_candidates: int,
) -> list[tuple[dict[int, int], np.ndarray, float]]:
    if not voices_to_fill:
        return [({}, seed_row.copy(), 0.0)]
    candidate_lists = [top_pitch_candidates(row_logits[voice_idx], tokenizer, top_k=top_k) for voice_idx in voices_to_fill]
    if not all(candidate_lists):
        return [({}, seed_row.copy(), 0.0)]
    rows: list[tuple[dict[int, int], np.ndarray, float]] = []
    for combo in product(*candidate_lists):
        candidate_row = seed_row.copy()
        row_tokens: dict[int, int] = {}
        nll_cost = 0.0
        for voice_idx, (token, midi_pitch, nll) in zip(voices_to_fill, combo):
            row_tokens[int(voice_idx)] = int(token)
            candidate_row[int(voice_idx)] = float(midi_pitch)
            nll_cost += float(nll)
        rows.append((row_tokens, candidate_row, nll_cost))
    rows.sort(key=lambda item: item[2])
    return rows[:max_row_candidates]


def _extract_harmony(
    harmonic_labels: dict | None,
    length: int,
) -> tuple[np.ndarray | None, np.ndarray | None, np.ndarray | None, int | None]:
    if not harmonic_labels:
        return None, None, None, None
    chord_roots = np.asarray(harmonic_labels.get("chord_roots", np.full(length, -1)))[:length]
    is_seventh = np.asarray(harmonic_labels.get("is_seventh_chord", np.zeros(length, dtype=bool)))[:length]
    is_phrase_end = np.asarray(harmonic_labels.get("is_phrase_end", np.zeros(length, dtype=bool)))[:length]
    key_tonic_pc = _safe_pc(harmonic_labels.get("key_tonic_pc"))
    return chord_roots, is_seventh, is_phrase_end, key_tonic_pc


def _safe_pc(value: object) -> int | None:
    if value is None:
        return None
    try:
        arr = np.asarray(value)
        if arr.ndim > 0:
            value = arr.reshape(-1)[0]
        return int(value) % 12
    except (TypeError, ValueError, OverflowError):
        return None

