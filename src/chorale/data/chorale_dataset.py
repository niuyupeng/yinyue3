from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
from torch.utils.data import Dataset

from chorale.data.score_tokenizer import ScoreTokenizer


class ChoraleDataset(Dataset):
    def __init__(
        self,
        processed_path: str | Path,
        split: str = "train",
        task: str = "soprano_to_satb",
        mask_prob: float = 0.45,
        seed: int = 1234,
    ) -> None:
        self.processed_path = Path(processed_path)
        self.data = np.load(self.processed_path, allow_pickle=False)
        self.tokenizer = ScoreTokenizer.from_npz_metadata(self.data)
        all_splits = self.data["splits"].astype(str)
        self.indices = np.where(all_splits == split)[0]
        if len(self.indices) == 0 and split != "train":
            self.indices = np.where(all_splits == "train")[0]
        if len(self.indices) == 0:
            raise RuntimeError(f"No examples found for split={split}")
        self.split = split
        self.task = task
        self.mask_prob = float(mask_prob)
        self.seed = int(seed)

    def __len__(self) -> int:
        return int(len(self.indices))

    def __getitem__(self, idx: int) -> dict[str, torch.Tensor | str]:
        source_idx = int(self.indices[idx])
        tokens = self.data["tokens"][source_idx].astype(np.int64)
        length = int(self.data["lengths"][source_idx])
        beat_positions = self.data["beat_positions"][source_idx].astype(np.int64)
        measure_indices = self.data["measure_indices"][source_idx].astype(np.int64)
        name = str(self.data["names"][source_idx])
        key_tonic_pc = self._array_or_default("key_tonic_pcs", source_idx, np.array(0, dtype=np.int64))
        chord_roots = self._array_or_default("chord_roots", source_idx, np.full(tokens.shape[0], -1, dtype=np.int64))
        is_seventh_chord = self._array_or_default("is_seventh_chord", source_idx, np.zeros(tokens.shape[0], dtype=bool))
        is_dominant_function = self._array_or_default("is_dominant_function", source_idx, np.zeros(tokens.shape[0], dtype=bool))
        is_phrase_end = self._array_or_default("is_phrase_end", source_idx, np.zeros(tokens.shape[0], dtype=bool))
        chord_label_known = self._array_or_default("chord_label_known", source_idx, np.zeros(tokens.shape[0], dtype=bool))
        roman_numeral_known = self._array_or_default("roman_numeral_known", source_idx, np.zeros(tokens.shape[0], dtype=bool))

        valid = np.zeros_like(tokens, dtype=bool)
        valid[:length, :] = tokens[:length, :] != self.tokenizer.PAD
        known = np.zeros_like(tokens, dtype=bool)
        target = np.zeros_like(tokens, dtype=bool)

        if self.task == "soprano_to_satb":
            known[:length, 0] = True
            target[:length, 1:] = True
        elif self.task == "bass_to_satb":
            known[:length, 3] = True
            target[:length, :3] = True
        elif self.task == "masked_infill":
            rng = np.random.default_rng(self.seed + source_idx)
            random_visible = rng.random(tokens.shape) > self.mask_prob
            known = random_visible & valid
            target = (~known) & valid
        else:
            raise ValueError(f"Unknown task: {self.task}")

        input_tokens = tokens.copy()
        input_tokens[target] = self.tokenizer.MASK
        input_tokens[~valid] = self.tokenizer.PAD
        target = target & valid

        return {
            "tokens": torch.from_numpy(tokens).long(),
            "input_tokens": torch.from_numpy(input_tokens).long(),
            "known_mask": torch.from_numpy(known).bool(),
            "target_mask": torch.from_numpy(target).bool(),
            "valid_mask": torch.from_numpy(valid).bool(),
            "beat_positions": torch.from_numpy(beat_positions).long(),
            "measure_indices": torch.from_numpy(measure_indices).long(),
            "key_tonic_pc": torch.tensor(int(key_tonic_pc), dtype=torch.long),
            "chord_roots": torch.from_numpy(np.asarray(chord_roots, dtype=np.int64)).long(),
            "is_seventh_chord": torch.from_numpy(np.asarray(is_seventh_chord, dtype=bool)).bool(),
            "is_dominant_function": torch.from_numpy(np.asarray(is_dominant_function, dtype=bool)).bool(),
            "is_phrase_end": torch.from_numpy(np.asarray(is_phrase_end, dtype=bool)).bool(),
            "chord_label_known": torch.from_numpy(np.asarray(chord_label_known, dtype=bool)).bool(),
            "roman_numeral_known": torch.from_numpy(np.asarray(roman_numeral_known, dtype=bool)).bool(),
            "length": torch.tensor(length, dtype=torch.long),
            "source_index": torch.tensor(source_idx, dtype=torch.long),
            "name": name,
        }

    def _array_or_default(self, key: str, source_idx: int, default: np.ndarray) -> np.ndarray:
        if key in self.data.files:
            return self.data[key][source_idx]
        return default

    def get_harmonic_labels(self, source_idx: int, length: int | None = None) -> dict:
        tokens = self.data["tokens"][source_idx]
        max_seq_len = tokens.shape[0]
        if length is None:
            length = int(self.data["lengths"][source_idx])
        key_label = str(self.data["key_labels"][source_idx]) if "key_labels" in self.data.files else "UNKNOWN"
        key_tonic_pc = int(self.data["key_tonic_pcs"][source_idx]) if "key_tonic_pcs" in self.data.files else 0
        return {
            "key_label": key_label,
            "key_tonic_pc": np.int64(key_tonic_pc),
            "chord_roots": self._array_or_default("chord_roots", source_idx, np.full(max_seq_len, -1, dtype=np.int64)),
            "chord_qualities": self._array_or_default("chord_qualities", source_idx, np.full(max_seq_len, "UNKNOWN", dtype="<U32")),
            "roman_numerals": self._array_or_default("roman_numerals", source_idx, np.full(max_seq_len, "UNKNOWN", dtype="<U32")),
            "is_seventh_chord": self._array_or_default("is_seventh_chord", source_idx, np.zeros(max_seq_len, dtype=bool)),
            "is_dominant_function": self._array_or_default("is_dominant_function", source_idx, np.zeros(max_seq_len, dtype=bool)),
            "is_phrase_end": self._array_or_default("is_phrase_end", source_idx, np.zeros(max_seq_len, dtype=bool)),
            "chord_label_known": self._array_or_default("chord_label_known", source_idx, np.zeros(max_seq_len, dtype=bool)),
            "roman_numeral_known": self._array_or_default("roman_numeral_known", source_idx, np.zeros(max_seq_len, dtype=bool)),
            "length": np.int64(length),
        }


def dataset_metadata(processed_path: str | Path) -> dict[str, int | float]:
    with np.load(processed_path, allow_pickle=False) as data:
        tokenizer = ScoreTokenizer.from_npz_metadata(data)
        return {
            **tokenizer.metadata(),
            "num_examples": int(data["tokens"].shape[0]),
            "has_harmonic_labels": bool("roman_numerals" in data.files and "chord_roots" in data.files),
        }
