from __future__ import annotations

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer, VOICE_RANGES


class RuleBaseline:
    """Small deterministic heuristic baseline for soprano-conditioned SATB."""

    def __init__(self, tokenizer: ScoreTokenizer, key_tonic_midi: int = 60) -> None:
        self.tokenizer = tokenizer
        self.key_tonic_pc = key_tonic_midi % 12

    def harmonize(self, input_tokens: np.ndarray, length: int | None = None) -> np.ndarray:
        matrix = np.asarray(input_tokens, dtype=np.int64)
        if length is None:
            length = matrix.shape[0]
        output = matrix.copy()
        last_notes = [64, 60, 55, 48]
        for t in range(length):
            soprano_midi = self.tokenizer.token_to_midi(int(matrix[t, 0]))
            if soprano_midi is None:
                if int(matrix[t, 0]) == self.tokenizer.HOLD:
                    output[t, 1:] = self.tokenizer.HOLD
                else:
                    output[t, 1:] = self.tokenizer.REST
                continue
            chord_tones = self._triad_for_soprano(soprano_midi)
            alto = nearest_below(chord_tones, soprano_midi - 3, VOICE_RANGES["alto"], last_notes[1])
            tenor = nearest_below(chord_tones, alto - 4, VOICE_RANGES["tenor"], last_notes[2])
            bass = nearest_below(chord_tones, tenor - 7, VOICE_RANGES["bass"], last_notes[3])
            for voice, midi in zip((1, 2, 3), (alto, tenor, bass)):
                output[t, voice] = self.tokenizer.midi_to_token(midi)
                last_notes[voice] = midi
        if length < output.shape[0]:
            output[length:] = self.tokenizer.PAD
        return output

    def _triad_for_soprano(self, soprano_midi: int) -> list[int]:
        pc = soprano_midi % 12
        major_tones = [self.key_tonic_pc, (self.key_tonic_pc + 4) % 12, (self.key_tonic_pc + 7) % 12]
        if pc in major_tones:
            pcs = major_tones
        else:
            pcs = [pc, (pc + 3) % 12, (pc + 7) % 12]
        candidates = []
        for octave in range(2, 6):
            for tone in pcs:
                candidates.append(12 * octave + tone)
        return sorted(set(candidates))


def nearest_below(candidates: list[int], target: int, midi_range: tuple[int, int], previous: int) -> int:
    low, high = midi_range
    valid = [m for m in candidates if low <= m <= high and m <= target]
    if not valid:
        valid = [m for m in candidates if low <= m <= high]
    if not valid:
        return int(np.clip(target, low, high))
    return min(valid, key=lambda m: (abs(m - target), abs(m - previous)))
