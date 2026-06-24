from __future__ import annotations

import numpy as np

from chorale.data.build_dataset import build_dataset_from_scores
from chorale.data.score_tokenizer import ScoreTokenizer
from tests.test_score_tokenizer import tiny_satb_score


def test_dataset_build_from_artificial_score(tmp_path) -> None:
    output = tmp_path / "tiny_dataset.npz"
    tokenizer = ScoreTokenizer(max_seq_len=32)
    summary = build_dataset_from_scores(
        [("tiny1", tiny_satb_score()), ("tiny2", tiny_satb_score()), ("tiny3", tiny_satb_score())],
        output,
        tokenizer,
        seed=1,
    )
    assert summary["encoded_scores"] == 3
    data = np.load(output)
    assert data["tokens"].shape == (3, 32, 4)
    assert set(data["splits"].astype(str)) == {"train", "val", "test"}
    assert "roman_numerals" in data.files
    assert "is_seventh_chord" in data.files
    assert data["chord_roots"].shape == (3, 32)
