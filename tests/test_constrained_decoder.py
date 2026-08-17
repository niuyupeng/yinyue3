from __future__ import annotations

import numpy as np
import torch

from chorale.constraint_decoding.constrained_beam import apply_cih_constrained_beam_search
from chorale.constraint_decoding.constraint_costs import ConstraintWeights, score_candidate_transition
from chorale.data.score_tokenizer import ScoreTokenizer


def test_cih_constrained_beam_filters_voice_crossing_argmax() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=2)
    tokens = np.full((2, 4), tokenizer.PAD, dtype=np.int64)
    tokens[0] = [
        tokenizer.midi_to_token(60),
        tokenizer.MASK,
        tokenizer.MASK,
        tokenizer.MASK,
    ]
    target_mask = np.zeros((2, 4), dtype=bool)
    target_mask[0, 1:] = True
    logits = torch.full((2, 4, tokenizer.vocab_size), -12.0)
    logits[0, 1, tokenizer.midi_to_token(72)] = 5.0
    logits[0, 1, tokenizer.midi_to_token(55)] = 4.5
    logits[0, 2, tokenizer.midi_to_token(52)] = 5.0
    logits[0, 3, tokenizer.midi_to_token(48)] = 5.0

    decoded = apply_cih_constrained_beam_search(
        tokens,
        logits,
        target_mask,
        tokenizer,
        length=1,
        beam_size=2,
        top_k=2,
        hard_constraints=["voice_crossing"],
        soft_constraint_weights={},
    )

    assert decoded[0, 1] == tokenizer.midi_to_token(55)


def test_constraint_costs_report_hard_and_soft_parts() -> None:
    previous = np.array([62.0, 57.0, 53.0, 48.0])
    current = np.array([64.0, 60.0, 55.0, 50.0])

    feasible, cost, violations = score_candidate_transition(
        previous,
        current,
        hard_constraints=["voice_crossing"],
        weights=ConstraintWeights(melodic_smoothness=1.0),
    )

    assert feasible
    assert cost >= 0.0
    assert violations == []

