from __future__ import annotations

import numpy as np
import torch

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.theory.rule_guided_decoding import apply_constrained_beam_search


def test_constrained_beam_search_can_reject_crossing_argmax() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=2)
    length = 1
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

    # Alto argmax would cross above soprano. A slightly lower-scoring candidate
    # is musically legal and should win once soft constraints are included.
    logits[0, 1, tokenizer.midi_to_token(72)] = 5.0
    logits[0, 1, tokenizer.midi_to_token(55)] = 4.8
    logits[0, 2, tokenizer.midi_to_token(52)] = 5.0
    logits[0, 3, tokenizer.midi_to_token(48)] = 5.0

    decoded = apply_constrained_beam_search(
        tokens,
        logits,
        target_mask,
        tokenizer,
        length=length,
        beam_size=2,
        top_k=2,
        rule_weight=4.0,
        temporal_weight=0.0,
        harmony_weight=0.0,
        seventh_weight=0.0,
    )

    assert decoded[0, 1] == tokenizer.midi_to_token(55)
