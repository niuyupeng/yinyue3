from __future__ import annotations

import torch

from chorale.data.chorale_dataset import stable_label_ids
from chorale.models.cih_s2s_transformer import CIHS2STransformer
from chorale.train import build_model


def test_cih_s2s_forward_accepts_full_harmonic_plan_inputs() -> None:
    model = CIHS2STransformer(
        vocab_size=32,
        hidden_size=24,
        local_layers=1,
        plan_layers=1,
        decoder_layers=2,
        heads=4,
        dropout=0.0,
        max_seq_len=8,
        max_measure=4,
        max_relative_distance=4,
        use_harmonic_plan_encoder=True,
        use_voice_relation_attention=True,
        use_bar_summary_attention=True,
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
        chord_quality_ids=torch.ones(batch, seq_len, dtype=torch.long),
        roman_numeral_ids=torch.ones(batch, seq_len, dtype=torch.long),
    )

    assert logits.shape == (batch, seq_len, 4, 32)


def test_build_model_registers_cih_s2s_transformer() -> None:
    model = build_model(
        {
            "model": {
                "type": "cih_s2s_transformer",
                "hidden_size": 24,
                "local_layers": 1,
                "plan_layers": 1,
                "decoder_layers": 2,
                "heads": 4,
                "max_seq_len": 8,
                "max_measure": 4,
                "max_relative_distance": 4,
            }
        },
        vocab_size=32,
    )

    assert isinstance(model, CIHS2STransformer)


def test_unknown_harmonic_labels_use_reserved_zero_id() -> None:
    ids = stable_label_ids(["UNKNOWN", "", "V7"], buckets=63)

    assert ids[0] == 0
    assert ids[1] == 0
    assert ids[2] > 0

