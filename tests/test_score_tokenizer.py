from __future__ import annotations

import numpy as np
from music21 import duration, note, stream

from chorale.data.score_tokenizer import ScoreTokenizer, extract_satb_parts, token_events


def tiny_satb_score() -> stream.Score:
    score = stream.Score()
    pitches = {
        "Soprano": ["C5", "D5", "E5", "F5"],
        "Alto": ["G4", "A4", "G4", "A4"],
        "Tenor": ["E3", "F3", "G3", "A3"],
        "Bass": ["C3", "D3", "C3", "F2"],
    }
    for part_name, names in pitches.items():
        part = stream.Part(id=part_name)
        part.partName = part_name
        for pitch_name in names:
            n = note.Note(pitch_name)
            n.duration = duration.Duration(1.0)
            part.append(n)
        score.append(part)
    return score


def test_parser_returns_four_voices() -> None:
    parts = extract_satb_parts(tiny_satb_score())
    assert len(parts) == 4
    assert [p.partName for p in parts] == ["Soprano", "Alto", "Tenor", "Bass"]


def test_parser_prefers_generic_voice_parts_over_instruments() -> None:
    score = stream.Score()
    for part_name in ["Horn in G", "Timpani", "Flute"]:
        part = stream.Part(id=part_name)
        part.partName = part_name
        n = note.Note("C4")
        n.duration = duration.Duration(1.0)
        part.append(n)
        score.append(part)
    for idx, pitch_name in enumerate(["C5", "G4", "E3", "C3"], start=1):
        part = stream.Part(id=f"Voice{idx}")
        part.partName = "Voice"
        n = note.Note(pitch_name)
        n.duration = duration.Duration(1.0)
        part.append(n)
        score.append(part)
    continuo = stream.Part(id="Continuo")
    continuo.partName = "Continuo"
    continuo.append(note.Note("C2"))
    score.append(continuo)

    parts = extract_satb_parts(score)

    assert [part.id for part in parts] == ["Voice1", "Voice2", "Voice3", "Voice4"]
    encoded = ScoreTokenizer(max_seq_len=8).encode_score(score, name="orchestrated")
    assert ScoreTokenizer(max_seq_len=8).token_to_midi(encoded["tokens"][0, 0]) == 72


def test_tokenizer_roundtrip_tiny_satb() -> None:
    tokenizer = ScoreTokenizer(max_seq_len=32)
    encoded = tokenizer.encode_score(tiny_satb_score(), name="tiny")
    tokens = encoded["tokens"]
    assert tokens.shape == (32, 4)
    assert encoded["length"] == 16
    assert tokenizer.token_to_midi(tokens[0, 0]) == 72
    assert tokens[1, 0] == tokenizer.HOLD
    events = token_events(tokens[: int(encoded["length"]), 0], tokenizer)
    assert events[0] == ("note", 72, 4)
