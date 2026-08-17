from __future__ import annotations

import torch

from chorale.models.transformer import HierarchicalScoreTransformer, NeuralSymbolicChoraleTransformer
from chorale.train import build_model


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


def test_hierarchical_score_transformer_forward_with_harmonic_plan() -> None:
    model = HierarchicalScoreTransformer(
        vocab_size=32,
        hidden_size=24,
        local_layers=1,
        plan_layers=1,
        decoder_layers=1,
        heads=4,
        dropout=0.0,
        max_seq_len=8,
        max_measure=4,
        max_relative_distance=4,
        use_voice_relation_attention=True,
        voice_relation_heads=2,
    )
    batch = 2
    seq_len = 8
    tokens = torch.randint(0, 32, (batch, seq_len, 4))
    known = torch.zeros(batch, seq_len, 4, dtype=torch.bool)

    logits = model(
        tokens,
        known,
        beat_positions=torch.arange(seq_len).view(1, seq_len).repeat(batch, 1),
        measure_indices=torch.tensor([[1, 1, 1, 1, 2, 2, 2, 2]]).repeat(batch, 1),
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


def test_build_model_registers_hierarchical_score_transformer() -> None:
    model = build_model(
        {
            "model": {
                "type": "hierarchical_score_transformer",
                "hidden_size": 24,
                "local_layers": 1,
                "plan_layers": 1,
                "decoder_layers": 1,
                "heads": 4,
                "max_seq_len": 8,
                "max_measure": 4,
                "max_relative_distance": 4,
            }
        },
        vocab_size=32,
    )

    assert isinstance(model, HierarchicalScoreTransformer)
