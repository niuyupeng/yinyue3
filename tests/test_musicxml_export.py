from __future__ import annotations

from music21 import converter

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.export_musicxml import export_tokens_to_musicxml
from tests.test_score_tokenizer import tiny_satb_score


def test_musicxml_export_creates_valid_file(tmp_path) -> None:
    tokenizer = ScoreTokenizer(max_seq_len=32)
    encoded = tokenizer.encode_score(tiny_satb_score(), name="tiny")
    output = tmp_path / "tiny.musicxml"
    written = export_tokens_to_musicxml(
        encoded["tokens"],
        tokenizer,
        output,
        length=int(encoded["length"]),
        title="Tiny SATB",
    )
    assert written.exists()
    parsed = converter.parse(str(written))
    assert len(parsed.parts) == 4
