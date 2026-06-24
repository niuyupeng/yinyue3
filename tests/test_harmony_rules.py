from __future__ import annotations

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.theory.harmony_rules import check_cadence_correctness, check_seventh_resolution


def matrix_from_midis(rows: list[list[int]], tokenizer: ScoreTokenizer) -> np.ndarray:
    return np.array([[tokenizer.midi_to_token(m) for m in row] for row in rows], dtype=np.int64)


def labels(
    roman: list[str],
    roots: list[int],
    seventh: list[bool] | None = None,
    qualities: list[str] | None = None,
    phrase_end: list[bool] | None = None,
    key_tonic_pc: int = 0,
    beat_positions: list[int] | None = None,
    active_counts: list[int] | None = None,
    pc_counts: list[int] | None = None,
    dominant_function: list[bool] | None = None,
) -> dict:
    n = len(roman)
    return {
        "key_label": "C major",
        "key_tonic_pc": np.int64(key_tonic_pc),
        "beat_positions": np.array(beat_positions if beat_positions is not None else [-1] * n, dtype=np.int64),
        "roman_numerals": np.array(roman, dtype="<U32"),
        "chord_roots": np.array(roots, dtype=np.int64),
        "is_seventh_chord": np.array(seventh if seventh is not None else [False] * n, dtype=bool),
        "chord_qualities": np.array(qualities if qualities is not None else ["UNKNOWN"] * n, dtype="<U32"),
        "is_phrase_end": np.array(phrase_end if phrase_end is not None else [False] * n, dtype=bool),
        "chord_label_known": np.array([root >= 0 for root in roots], dtype=bool),
        "roman_numeral_known": np.array([item != "UNKNOWN" for item in roman], dtype=bool),
        "active_voice_counts": np.array(active_counts if active_counts is not None else [4] * n, dtype=np.int64),
        "distinct_pitch_class_counts": np.array(pc_counts if pc_counts is not None else [3] * n, dtype=np.int64),
        "is_dominant_function": np.array(
            dominant_function if dominant_function is not None else [False] * n,
            dtype=bool,
        ),
    }


def test_correct_seventh_resolution() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 70, 64, 48], [72, 69, 65, 53]], tokenizer)
    report = check_seventh_resolution(
        tokens,
        tokenizer,
        harmonic_labels=labels(["V7", "I"], [0, 5], [True, False], ["dominant-seventh", "major"]),
        length=2,
    )
    assert report["total_violations"] == 0
    assert report["confident_checks"] == 1


def test_unresolved_seventh_violation() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 70, 64, 48], [72, 72, 65, 53]], tokenizer)
    report = check_seventh_resolution(
        tokens,
        tokenizer,
        harmonic_labels=labels(["V7", "I"], [0, 5], [True, False], ["dominant-seventh", "major"]),
        length=2,
    )
    assert report["total_violations"] == 1
    assert "chordal seventh in alto" in report["explanations"][0]


def test_unknown_chord_label_seventh_case() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 70, 64, 48], [72, 72, 65, 53]], tokenizer)
    report = check_seventh_resolution(
        tokens,
        tokenizer,
        harmonic_labels=labels(["UNKNOWN", "UNKNOWN"], [-1, -1], [False, False]),
        length=2,
    )
    assert report["total_violations"] == 0
    assert report["confident_checks"] == 0


def test_offbeat_automatic_seventh_is_not_treated_as_confident_harmony() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 70, 64, 48], [72, 72, 65, 53]], tokenizer)
    report = check_seventh_resolution(
        tokens,
        tokenizer,
        harmonic_labels=labels(
            ["V7", "I"],
            [0, 5],
            [True, False],
            ["dominant-seventh", "major"],
            beat_positions=[1, 4],
        ),
        length=2,
    )

    assert report["total_violations"] == 0
    assert report["confident_checks"] == 0


def test_authentic_like_cadence() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[71, 67, 62, 43], [72, 64, 60, 48]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(["V", "I"], [7, 0], phrase_end=[False, True]),
        length=2,
    )
    assert report["cadence_type"] == "authentic_cadence_like"
    assert report["total_violations"] == 0


def test_half_cadence_like_case() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 64, 60, 48], [71, 67, 62, 43]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(["I", "V"], [0, 7], phrase_end=[False, True]),
        length=2,
    )
    assert report["cadence_type"] == "half_cadence_like"


def test_unknown_cadence_case() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 64, 60, 48], [74, 65, 62, 50]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(["UNKNOWN", "UNKNOWN"], [-1, -1], phrase_end=[False, True]),
        length=2,
    )
    assert report["cadence_type"] == "UNKNOWN"
    assert report["cadence_unknown_rate"] == 1.0


def test_tonic_closure_like_cadence_when_final_is_tonic_without_clear_dominant() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 64, 60, 48], [72, 67, 64, 48]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(["ii", "I"], [2, 0], phrase_end=[False, True]),
        length=2,
    )
    assert report["cadence_type"] == "tonic_closure_like"
    assert report["cadence_unknown_rate"] == 0.0


def test_cadence_ignores_sparse_tail_after_complete_tonic_closure() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[72, 67, 64, 48], [72, 67, 64, 48]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(
            ["I", "V"],
            [0, 7],
            phrase_end=[True, True],
            active_counts=[4, 1],
            pc_counts=[3, 1],
        ),
        length=2,
    )
    assert report["cadence_type"] == "tonic_closure_like"
    assert report["final_timestep"] == 0


def test_authentic_like_cadence_can_use_root_fallback_when_roman_is_noisy() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[74, 69, 61, 57], [72, 64, 60, 48]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(["ii6", "I"], [7, 0], phrase_end=[False, True]),
        length=2,
    )
    assert report["cadence_type"] == "authentic_cadence_like"


def test_authentic_like_cadence_can_use_dominant_function_fallback() -> None:
    tokenizer = ScoreTokenizer()
    tokens = matrix_from_midis([[74, 69, 61, 57], [72, 64, 60, 48]], tokenizer)
    report = check_cadence_correctness(
        tokens,
        tokenizer,
        harmonic_labels=labels(
            ["UNKNOWN", "I"],
            [-1, 0],
            phrase_end=[False, True],
            dominant_function=[True, False],
        ),
        length=2,
    )
    assert report["cadence_type"] == "authentic_cadence_like"
