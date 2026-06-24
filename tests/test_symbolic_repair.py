from __future__ import annotations

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.symbolic_repair import apply_final_authentic_cadence, apply_final_tonic_closure, optimize_symbolic_postprocess
from chorale.theory.explain_report import build_explanation_report


def matrix_from_midis(rows: list[list[int]], tokenizer: ScoreTokenizer) -> np.ndarray:
    return np.array([[tokenizer.midi_to_token(m) for m in row] for row in rows], dtype=np.int64)


def test_symbolic_repair_preserves_known_soprano_and_reduces_penalty() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=8)
    tokens = matrix_from_midis(
        [
            [72, 64, 55, 48],
            [74, 66, 57, 50],
        ],
        tokenizer,
    )
    known = np.zeros_like(tokens, dtype=bool)
    known[:, 0] = True
    before = build_explanation_report(tokens, tokenizer, length=2, key_tonic_pc=0)

    repaired = optimize_symbolic_postprocess(tokens, known, tokenizer, length=2, key_tonic_pc=0, max_passes=3)
    after = build_explanation_report(repaired.tokens, tokenizer, length=2, key_tonic_pc=0)

    assert repaired.tokens[:, 0].tolist() == tokens[:, 0].tolist()
    assert repaired.summary["accepted_repairs"] >= 1
    assert after["total_penalty"] < before["total_penalty"]


def test_final_tonic_closure_fills_generated_final_voices() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=8)
    tokens = np.full((8, 4), tokenizer.PAD, dtype=np.int64)
    tokens[:6, :] = tokenizer.REST
    tokens[0, 0] = tokenizer.midi_to_token(64)
    tokens[1:4, 0] = tokenizer.HOLD
    tokens[4:6, 1:] = tokenizer.midi_to_token(67)
    known = np.zeros_like(tokens, dtype=bool)
    known[:6, 0] = True

    repaired = apply_final_tonic_closure(tokens, known, tokenizer, length=6, key_tonic_pc=0, key_label="C major")
    midi = tokenizer.expand_holds(repaired.tokens, length=6)

    assert repaired.summary["applied"] is True
    assert repaired.tokens[:4, 0].tolist() == tokens[:4, 0].tolist()
    assert not np.isnan(midi[0]).any()
    assert int(midi[0, 3]) % 12 == 0
    assert {int(p) % 12 for p in midi[0]} <= {0, 4, 7}
    assert repaired.tokens[4:6, 1:].tolist() == [[tokenizer.REST, tokenizer.REST, tokenizer.REST]] * 2


def test_final_tonic_closure_skips_non_tonic_known_final_pitch() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=8)
    tokens = np.full((8, 4), tokenizer.PAD, dtype=np.int64)
    tokens[:4, :] = tokenizer.REST
    tokens[0, 0] = tokenizer.midi_to_token(74)
    tokens[1:4, 0] = tokenizer.HOLD
    known = np.zeros_like(tokens, dtype=bool)
    known[:4, 0] = True

    repaired = apply_final_tonic_closure(tokens, known, tokenizer, length=4, key_tonic_pc=0, key_label="C major")

    assert repaired.summary["applied"] is False
    assert "not in tonic triad" in repaired.summary["reason"]
    assert repaired.tokens[:4].tolist() == tokens[:4].tolist()


def test_final_authentic_cadence_repairs_dominant_preparation_when_melody_allows() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=12)
    tokens = np.full((12, 4), tokenizer.PAD, dtype=np.int64)
    tokens[:8, :] = tokenizer.REST
    tokens[0, 0] = tokenizer.midi_to_token(74)  # D in C major: dominant chord member.
    tokens[1:4, 0] = tokenizer.HOLD
    tokens[4, 0] = tokenizer.midi_to_token(72)  # Final tonic soprano.
    tokens[5:8, 0] = tokenizer.HOLD
    known = np.zeros_like(tokens, dtype=bool)
    known[:8, 0] = True

    repaired = apply_final_authentic_cadence(tokens, known, tokenizer, length=8, key_tonic_pc=0, key_label="C major")
    midi = tokenizer.expand_holds(repaired.tokens, length=8)

    assert repaired.summary["applied"] is True
    assert "dominant-to-tonic" in repaired.summary["reason"]
    assert repaired.tokens[:8, 0].tolist() == tokens[:8, 0].tolist()
    assert {int(p) % 12 for p in midi[0]} <= {2, 7, 11}
    assert int(midi[0, 3]) % 12 == 7
    assert {int(p) % 12 for p in midi[4]} <= {0, 4, 7}
    assert int(midi[4, 3]) % 12 == 0


def test_final_authentic_cadence_skips_when_previous_melody_is_not_dominant() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=12)
    tokens = np.full((12, 4), tokenizer.PAD, dtype=np.int64)
    tokens[:8, :] = tokenizer.REST
    tokens[0, 0] = tokenizer.midi_to_token(64)
    tokens[1:4, 0] = tokenizer.HOLD
    tokens[4, 0] = tokenizer.midi_to_token(72)
    tokens[5:8, 0] = tokenizer.HOLD
    known = np.zeros_like(tokens, dtype=bool)
    known[:8, 0] = True

    repaired = apply_final_authentic_cadence(tokens, known, tokenizer, length=8, key_tonic_pc=0, key_label="C major")

    assert repaired.summary["applied"] is False
    assert "not compatible with dominant" in repaired.summary["reason"]
