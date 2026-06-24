from __future__ import annotations

import numpy as np
import torch

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.theory.rule_guided_decoding import apply_constraint_reranking
from chorale.theory.voice_leading_rules import (
    check_leading_tone_resolution,
    check_parallel_fifths,
    check_parallel_octaves,
    check_voice_crossing,
    check_voice_ranges,
)


def matrix_from_midis(rows: list[list[int]], tokenizer: ScoreTokenizer) -> np.ndarray:
    return np.array([[tokenizer.midi_to_token(m) for m in row] for row in rows], dtype=np.int64)


def test_voice_range_rule() -> None:
    tokenizer = ScoreTokenizer(max_midi=96)
    tokens = matrix_from_midis([[90, 64, 55, 48]], tokenizer)
    violations = check_voice_ranges(tokens, tokenizer, length=1)
    assert any(v.rule == "voice_range" and "soprano" in v.message for v in violations)


def test_voice_crossing_rule() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[60, 67, 55, 48]], tokenizer)
    violations = check_voice_crossing(tokens, tokenizer, length=1)
    assert any(v.rule == "voice_crossing" for v in violations)


def test_parallel_fifth_rule() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis(
        [
            [72, 64, 57, 53],
            [74, 66, 59, 55],
        ],
        tokenizer,
    )
    violations = check_parallel_fifths(tokens, tokenizer, length=2)
    assert any(v.rule == "parallel_fifth" for v in violations)


def test_parallel_octave_rule() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis(
        [
            [72, 64, 55, 48],
            [74, 66, 57, 50],
        ],
        tokenizer,
    )
    violations = check_parallel_octaves(tokens, tokenizer, length=2)
    assert any(v.rule == "parallel_octave" for v in violations)


def test_leading_tone_resolution_is_checked_once_after_held_note() -> None:
    tokenizer = ScoreTokenizer()
    tokens = np.full((8, 4), tokenizer.REST, dtype=np.int64)
    tokens[:, 0] = [
        tokenizer.midi_to_token(71),
        tokenizer.HOLD,
        tokenizer.HOLD,
        tokenizer.HOLD,
        tokenizer.midi_to_token(69),
        tokenizer.HOLD,
        tokenizer.HOLD,
        tokenizer.HOLD,
    ]

    violations = check_leading_tone_resolution(tokens, tokenizer, key_tonic_pc=0, length=8)

    assert len([v for v in violations if v.rule == "leading_tone_resolution"]) == 1


def test_constraint_reranking_prefers_valid_voice_range_candidate() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=4)
    tokens = np.full((4, 4), tokenizer.PAD, dtype=np.int64)
    tokens[0] = [
        tokenizer.midi_to_token(72),
        tokenizer.midi_to_token(64),
        tokenizer.MASK,
        tokenizer.midi_to_token(48),
    ]
    logits = torch.full((4, 4, tokenizer.vocab_size), -20.0)
    high_bad = tokenizer.midi_to_token(84)
    good_tenor = tokenizer.midi_to_token(55)
    logits[0, 2, high_bad] = 8.0
    logits[0, 2, good_tenor] = 7.8
    target_mask = np.zeros((4, 4), dtype=bool)
    target_mask[0, 2] = True

    reranked = apply_constraint_reranking(tokens, logits, target_mask, tokenizer, length=1, top_k=2)

    assert tokenizer.token_to_midi(int(reranked[0, 2])) == 55


def test_constraint_reranking_avoids_temporal_parallel_octave() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=4)
    tokens = matrix_from_midis(
        [
            [72, 64, 55, 48],
            [74, 66, 57, 50],
        ],
        tokenizer,
    )
    logits = torch.full((2, 4, tokenizer.vocab_size), -20.0)
    bad_parallel_bass = tokenizer.midi_to_token(50)
    good_bass = tokenizer.midi_to_token(49)
    logits[1, 3, bad_parallel_bass] = 8.0
    logits[1, 3, good_bass] = 7.9
    target_mask = np.zeros((2, 4), dtype=bool)
    target_mask[1, 3] = True

    reranked = apply_constraint_reranking(
        tokens,
        logits,
        target_mask,
        tokenizer,
        length=2,
        top_k=2,
        temporal_weight=2.0,
    )

    assert tokenizer.token_to_midi(int(reranked[1, 3])) == 49


def test_constraint_reranking_prefers_labeled_seventh_resolution() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=4)
    tokens = matrix_from_midis(
        [
            [74, 65, 59, 55],  # G7-like sonority: D-F-B-G, alto F is chordal seventh.
            [72, 65, 60, 48],
        ],
        tokenizer,
    )
    logits = torch.full((2, 4, tokenizer.vocab_size), -20.0)
    unresolved_alto = tokenizer.midi_to_token(65)
    resolved_alto = tokenizer.midi_to_token(64)
    logits[1, 1, unresolved_alto] = 8.0
    logits[1, 1, resolved_alto] = 7.9
    target_mask = np.zeros((2, 4), dtype=bool)
    target_mask[1, 1] = True
    harmonic_labels = {
        "chord_roots": np.array([7, 0]),
        "is_seventh_chord": np.array([True, False]),
        "is_dominant_function": np.array([True, False]),
        "key_tonic_pc": 0,
    }

    reranked = apply_constraint_reranking(
        tokens,
        logits,
        target_mask,
        tokenizer,
        length=2,
        harmonic_labels=harmonic_labels,
        top_k=2,
        harmony_weight=0.0,
        temporal_weight=0.0,
        seventh_weight=2.0,
    )

    assert tokenizer.token_to_midi(int(reranked[1, 1])) == 64
