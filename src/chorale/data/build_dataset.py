from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

import numpy as np
from music21 import converter, corpus, stream

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.theory.roman_numeral import annotate_score_harmony
from chorale.utils import ensure_dir, load_config


def iter_external_scores(folder: str | Path | None) -> Iterable[tuple[str, stream.Score]]:
    if not folder:
        return
    folder = Path(folder)
    if not folder.exists():
        raise FileNotFoundError(f"External MusicXML folder not found: {folder}")
    patterns = ("*.musicxml", "*.xml", "*.mxl")
    for pattern in patterns:
        for path in sorted(folder.rglob(pattern)):
            parsed = converter.parse(str(path))
            if isinstance(parsed, stream.Score):
                yield path.stem, parsed


def iter_builtin_bach_scores(max_chorales: int | None = None) -> Iterable[tuple[str, stream.Score]]:
    count = 0
    iterator = corpus.chorales.Iterator(numberingSystem="riemenschneider")
    for item in iterator:
        if max_chorales is not None and count >= max_chorales:
            break
        try:
            score = item if isinstance(item, stream.Score) else corpus.parse(item)
            title = score.metadata.title if score.metadata and score.metadata.title else f"bach_{count:03d}"
            yield str(title), score
            count += 1
        except Exception:
            continue


def deterministic_splits(
    n_items: int,
    seed: int,
    train_fraction: float,
    val_fraction: float,
    test_fraction: float,
) -> np.ndarray:
    if n_items <= 0:
        raise ValueError("Cannot split an empty dataset")
    fractions = np.array([train_fraction, val_fraction, test_fraction], dtype=np.float64)
    fractions = fractions / fractions.sum()
    rng = np.random.default_rng(seed)
    order = rng.permutation(n_items)
    splits = np.empty(n_items, dtype="<U5")
    if n_items < 3:
        splits[:] = "train"
        return splits
    n_train = max(1, int(round(fractions[0] * n_items)))
    n_val = max(1, int(round(fractions[1] * n_items)))
    if n_train + n_val >= n_items:
        n_train = max(1, n_items - 2)
        n_val = 1
    splits[order[:n_train]] = "train"
    splits[order[n_train : n_train + n_val]] = "val"
    splits[order[n_train + n_val :]] = "test"
    return splits


def build_dataset_from_scores(
    scores: Iterable[tuple[str, stream.Score]],
    output_path: str | Path,
    tokenizer: ScoreTokenizer,
    seed: int = 1234,
    train_fraction: float = 0.8,
    val_fraction: float = 0.1,
    test_fraction: float = 0.1,
) -> dict[str, int | str]:
    encoded = []
    skipped = []
    for name, score in scores:
        try:
            item = tokenizer.encode_score(score, name=name)
            harmony = annotate_score_harmony(
                score=score,
                tokenizer=tokenizer,
                tokens=item["tokens"],
                length=int(item["length"]),
                measure_indices=item["measure_indices"],
                beat_positions=item["beat_positions"],
            )
            item.update(harmony)
            encoded.append(item)
        except Exception as exc:
            skipped.append((name, str(exc)))

    if not encoded:
        raise RuntimeError("No SATB scores could be encoded")

    tokens = np.stack([item["tokens"] for item in encoded]).astype(np.int64)
    lengths = np.array([item["length"] for item in encoded], dtype=np.int64)
    names = np.array([str(item["name"]) for item in encoded], dtype="<U256")
    beat_positions = np.stack([item["beat_positions"] for item in encoded]).astype(np.int64)
    measure_indices = np.stack([item["measure_indices"] for item in encoded]).astype(np.int64)
    key_labels = np.array([str(item["key_label"]) for item in encoded], dtype="<U64")
    key_tonic_pcs = np.array([item["key_tonic_pc"] for item in encoded], dtype=np.int64)
    chord_roots = np.stack([item["chord_roots"] for item in encoded]).astype(np.int64)
    chord_qualities = np.stack([item["chord_qualities"] for item in encoded]).astype("<U32")
    roman_numerals = np.stack([item["roman_numerals"] for item in encoded]).astype("<U32")
    is_seventh_chord = np.stack([item["is_seventh_chord"] for item in encoded]).astype(bool)
    is_dominant_function = np.stack([item["is_dominant_function"] for item in encoded]).astype(bool)
    is_phrase_end = np.stack([item["is_phrase_end"] for item in encoded]).astype(bool)
    chord_label_known = np.stack([item["chord_label_known"] for item in encoded]).astype(bool)
    roman_numeral_known = np.stack([item["roman_numeral_known"] for item in encoded]).astype(bool)
    splits = deterministic_splits(
        len(encoded),
        seed=seed,
        train_fraction=train_fraction,
        val_fraction=val_fraction,
        test_fraction=test_fraction,
    )

    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    np.savez_compressed(
        output_path,
        tokens=tokens,
        lengths=lengths,
        names=names,
        splits=splits,
        beat_positions=beat_positions,
        measure_indices=measure_indices,
        key_labels=key_labels,
        key_tonic_pcs=key_tonic_pcs,
        chord_roots=chord_roots,
        chord_qualities=chord_qualities,
        roman_numerals=roman_numerals,
        is_seventh_chord=is_seventh_chord,
        is_dominant_function=is_dominant_function,
        is_phrase_end=is_phrase_end,
        chord_label_known=chord_label_known,
        roman_numeral_known=roman_numeral_known,
        grid_quarter_length=np.array(tokenizer.grid_quarter_length),
        min_midi=np.array(tokenizer.min_midi),
        max_midi=np.array(tokenizer.max_midi),
        max_seq_len=np.array(tokenizer.max_seq_len),
        vocab_size=np.array(tokenizer.vocab_size),
    )
    return {
        "output_path": str(output_path),
        "encoded_scores": len(encoded),
        "skipped_scores": len(skipped),
    }


def build_dataset_from_config(config: dict, max_chorales_override: int | None = None) -> dict[str, int | str]:
    data_cfg = config["data"]
    max_chorales = max_chorales_override
    if max_chorales is None:
        max_chorales = data_cfg.get("max_chorales")
    seq_len = data_cfg.get("max_seq_len", data_cfg.get("seq_len", config.get("seq_len", 256)))
    tokenizer = ScoreTokenizer(
        grid_quarter_length=data_cfg.get("grid_quarter_length", 0.25),
        min_midi=data_cfg.get("min_midi", 36),
        max_midi=data_cfg.get("max_midi", 84),
        max_seq_len=int(seq_len),
    )

    external = data_cfg.get("external_xml_dir")
    scores = list(iter_external_scores(external)) if external else []
    remaining = None if max_chorales is None else max(0, int(max_chorales) - len(scores))
    scores.extend(list(iter_builtin_bach_scores(remaining)))
    if max_chorales is not None:
        scores = scores[: int(max_chorales)]

    return build_dataset_from_scores(
        scores=scores,
        output_path=data_cfg["processed_path"],
        tokenizer=tokenizer,
        seed=int(config.get("seed", 1234)),
        train_fraction=float(data_cfg.get("train_fraction", 0.8)),
        val_fraction=float(data_cfg.get("val_fraction", 0.1)),
        test_fraction=float(data_cfg.get("test_fraction", 0.1)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a fixed-grid SATB chorale dataset.")
    parser.add_argument("--config", required=True, help="Path to YAML config.")
    parser.add_argument("--max-chorales", type=int, default=None, help="Override maximum number of chorales.")
    args = parser.parse_args()
    config = load_config(args.config)
    summary = build_dataset_from_config(config, max_chorales_override=args.max_chorales)
    print(summary)


if __name__ == "__main__":
    main()
