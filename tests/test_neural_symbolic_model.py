from __future__ import annotations

import torch

from chorale.models.transformer import NeuralSymbolicChoraleTransformer


def test_neural_symbolic_transformer_forward_with_harmony_labels() -> None:
    model = NeuralSymbolicChoraleTransformer(
        vocab_size=32,
        hidden_size=24,
        layers=1,
        heads=4,
        dropout=0.0,
        max_seq_len=8,
        max_relative_distance=4,
    )
    batch = 2
    seq_len = 8
    tokens = torch.randint(0, 32, (batch, seq_len, 4))
    known = torch.zeros(batch, seq_len, 4, dtype=torch.bool)
    logits = model(
        tokens,
        known,
        beat_positions=torch.arange(seq_len).view(1, seq_len).repeat(batch, 1),
        measure_indices=torch.zeros(batch, seq_len, dtype=torch.long),
        valid_mask=torch.ones(batch, seq_len, 4, dtype=torch.bool),
        key_tonic_pc=torch.tensor([0, 7]),
        chord_roots=torch.zeros(batch, seq_len, dtype=torch.long),
        is_seventh_chord=torch.zeros(batch, seq_len, dtype=torch.bool),
        is_dominant_function=torch.zeros(batch, seq_len, dtype=torch.bool),
        is_phrase_end=torch.zeros(batch, seq_len, dtype=torch.bool),
        chord_label_known=torch.ones(batch, seq_len, dtype=torch.bool),
        roman_numeral_known=torch.ones(batch, seq_len, dtype=torch.bool),
    )
    assert logits.shape == (batch, seq_len, 4, 32)


def test_neural_symbolic_transformer_forward_with_voice_relation_attention() -> None:
    model = NeuralSymbolicChoraleTransformer(
        vocab_size=32,
        hidden_size=24,
        layers=1,
        heads=4,
        dropout=0.0,
        max_seq_len=8,
        max_relative_distance=4,
        use_voice_relation_attention=True,
        voice_relation_heads=2,
    )
    tokens = torch.randint(0, 32, (1, 8, 4))
    known = torch.zeros(1, 8, 4, dtype=torch.bool)

    logits = model(tokens, known, valid_mask=torch.ones(1, 8, 4, dtype=torch.bool))

    assert logits.shape == (1, 8, 4, 32)
