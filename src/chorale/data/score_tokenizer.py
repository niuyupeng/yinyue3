from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
from music21 import chord, clef, duration, instrument, metadata, meter, note, stream

VOICE_NAMES = ("soprano", "alto", "tenor", "bass")
VOICE_DISPLAY_NAMES = ("Soprano", "Alto", "Tenor", "Bass")
VOICE_RANGES = {
    "soprano": (60, 81),
    "alto": (55, 74),
    "tenor": (48, 69),
    "bass": (40, 64),
}


@dataclass(frozen=True)
class TokenizerMetadata:
    grid_quarter_length: float = 0.25
    min_midi: int = 36
    max_midi: int = 84
    max_seq_len: int = 256


class ScoreTokenizer:
    """Tokenizer for fixed-grid SATB chorale pitch matrices."""

    PAD = 0
    REST = 1
    HOLD = 2
    MASK = 3
    FIRST_MIDI_TOKEN = 4

    def __init__(
        self,
        grid_quarter_length: float = 0.25,
        min_midi: int = 36,
        max_midi: int = 84,
        max_seq_len: int = 256,
    ) -> None:
        self.grid_quarter_length = float(grid_quarter_length)
        self.min_midi = int(min_midi)
        self.max_midi = int(max_midi)
        self.max_seq_len = int(max_seq_len)
        if self.min_midi >= self.max_midi:
            raise ValueError("min_midi must be smaller than max_midi")

    @property
    def vocab_size(self) -> int:
        return self.FIRST_MIDI_TOKEN + (self.max_midi - self.min_midi + 1)

    def metadata(self) -> dict[str, int | float]:
        return {
            "grid_quarter_length": self.grid_quarter_length,
            "min_midi": self.min_midi,
            "max_midi": self.max_midi,
            "max_seq_len": self.max_seq_len,
            "vocab_size": self.vocab_size,
        }

    @classmethod
    def from_npz_metadata(cls, data: np.lib.npyio.NpzFile) -> "ScoreTokenizer":
        return cls(
            grid_quarter_length=float(data["grid_quarter_length"]),
            min_midi=int(data["min_midi"]),
            max_midi=int(data["max_midi"]),
            max_seq_len=int(data["max_seq_len"]),
        )

    def midi_to_token(self, midi: int) -> int:
        midi = int(np.clip(midi, self.min_midi, self.max_midi))
        return self.FIRST_MIDI_TOKEN + midi - self.min_midi

    def token_to_midi(self, token: int) -> int | None:
        token = int(token)
        if token < self.FIRST_MIDI_TOKEN:
            return None
        midi = self.min_midi + token - self.FIRST_MIDI_TOKEN
        if midi < self.min_midi or midi > self.max_midi:
            return None
        return midi

    def token_to_label(self, token: int) -> str:
        token = int(token)
        if token == self.PAD:
            return "PAD"
        if token == self.REST:
            return "REST"
        if token == self.HOLD:
            return "HOLD"
        if token == self.MASK:
            return "MASK"
        midi = self.token_to_midi(token)
        return f"MIDI_{midi}" if midi is not None else f"UNK_{token}"

    def encode_score(self, score: stream.Score, name: str = "") -> dict[str, np.ndarray | str | int]:
        parts = extract_satb_parts(score)
        if len(parts) != 4:
            raise ValueError(f"Expected four SATB parts, found {len(parts)} in {name or 'score'}")

        total_quarters = max(float(part.duration.quarterLength) for part in parts)
        steps = max(1, int(math.ceil(total_quarters / self.grid_quarter_length)))
        steps = min(steps, self.max_seq_len)
        tokens = np.full((self.max_seq_len, 4), self.PAD, dtype=np.int64)
        working = np.full((steps, 4), self.REST, dtype=np.int64)

        for voice_idx, part in enumerate(parts):
            for element in iter_notes_and_rests(part):
                start = quantize_offset(element_offset(element, part), self.grid_quarter_length)
                if start >= steps:
                    continue
                dur_steps = max(1, int(round(float(element.duration.quarterLength) / self.grid_quarter_length)))
                end = min(steps, start + dur_steps)
                start_token = self.element_to_token(element, voice_idx)
                working[start, voice_idx] = start_token
                if end > start + 1:
                    working[start + 1 : end, voice_idx] = self.HOLD

        tokens[:steps] = working
        beat_positions, measure_indices = make_time_features(
            self.max_seq_len,
            self.grid_quarter_length,
        )
        return {
            "tokens": tokens,
            "length": np.int64(steps),
            "beat_positions": beat_positions,
            "measure_indices": measure_indices,
            "name": name or score.metadata.title if score.metadata else name,
        }

    def element_to_token(self, element: note.Note | note.Rest | chord.Chord, voice_idx: int) -> int:
        if element.isRest:
            return self.REST
        if isinstance(element, chord.Chord):
            pitches = sorted(p.midi for p in element.pitches)
            midi = pitches[-1] if voice_idx <= 1 else pitches[0]
            return self.midi_to_token(midi)
        if hasattr(element, "pitch"):
            return self.midi_to_token(element.pitch.midi)
        return self.REST

    def expand_holds(self, tokens: np.ndarray, length: int | None = None) -> np.ndarray:
        matrix = np.asarray(tokens, dtype=np.int64)
        if matrix.ndim != 2 or matrix.shape[1] != 4:
            raise ValueError("Expected token matrix of shape (T, 4)")
        if length is None:
            length = matrix.shape[0]
        midi = np.full((length, 4), np.nan, dtype=np.float32)
        previous: list[float] = [np.nan, np.nan, np.nan, np.nan]
        for t in range(length):
            for v in range(4):
                token = int(matrix[t, v])
                if token in (self.PAD, self.MASK, self.REST):
                    previous[v] = np.nan
                    continue
                if token == self.HOLD:
                    midi[t, v] = previous[v]
                    continue
                pitch = self.token_to_midi(token)
                if pitch is not None:
                    midi[t, v] = pitch
                    previous[v] = float(pitch)
                else:
                    previous[v] = np.nan
        return midi

    def sanitize_for_export(self, tokens: np.ndarray, length: int | None = None) -> np.ndarray:
        clean = np.asarray(tokens, dtype=np.int64).copy()
        if length is None:
            length = clean.shape[0]
        clean[:length][clean[:length] == self.PAD] = self.REST
        clean[:length][clean[:length] == self.MASK] = self.REST
        for v, voice_name in enumerate(VOICE_NAMES):
            low, high = VOICE_RANGES[voice_name]
            for t in range(length):
                midi = self.token_to_midi(int(clean[t, v]))
                if midi is not None:
                    clean[t, v] = self.midi_to_token(int(np.clip(midi, low, high)))
        if length < clean.shape[0]:
            clean[length:] = self.PAD
        return clean


def quantize_offset(offset: float, grid: float) -> int:
    return int(round(float(offset) / grid))


def make_time_features(max_seq_len: int, grid_quarter_length: float) -> tuple[np.ndarray, np.ndarray]:
    positions = np.arange(max_seq_len, dtype=np.float32) * float(grid_quarter_length)
    beat_positions = np.rint((positions % 4.0) / float(grid_quarter_length)).astype(np.int64)
    measure_indices = np.floor(positions / 4.0).astype(np.int64) + 1
    return beat_positions, measure_indices


def iter_notes_and_rests(part: stream.Part) -> Iterable[note.Note | note.Rest | chord.Chord]:
    return part.flatten().notesAndRests


def element_offset(element: note.Note | note.Rest | chord.Chord, part: stream.Part) -> float:
    try:
        return float(element.getOffsetInHierarchy(part))
    except Exception:
        return float(element.offset)


def extract_satb_parts(score: stream.Score) -> list[stream.Part]:
    parts = list(score.parts)
    if not parts and isinstance(score, stream.Part):
        parts = [score]

    normalized: dict[str, stream.Part] = {}
    for part in parts:
        label = " ".join(
            str(x or "")
            for x in (part.partName, part.partAbbreviation, part.id)
        ).lower()
        for voice in VOICE_NAMES:
            if voice in label and voice not in normalized:
                normalized[voice] = part

    if all(voice in normalized for voice in VOICE_NAMES):
        return [normalized[voice] for voice in VOICE_NAMES]

    if len(parts) >= 4:
        return parts[:4]

    raise ValueError("Could not identify four SATB parts")


def tokens_to_score(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int | None = None,
    title: str = "Generated SATB Chorale",
) -> stream.Score:
    matrix = np.asarray(tokens, dtype=np.int64)
    if matrix.ndim != 2 or matrix.shape[1] != 4:
        raise ValueError("Expected token matrix of shape (T, 4)")
    if length is None:
        pad_rows = np.where(np.all(matrix == tokenizer.PAD, axis=1))[0]
        length = int(pad_rows[0]) if len(pad_rows) else matrix.shape[0]
    length = max(1, min(int(length), matrix.shape[0]))

    score = stream.Score()
    score.metadata = metadata.Metadata()
    score.metadata.title = title

    for voice_idx, voice_name in enumerate(VOICE_DISPLAY_NAMES):
        part = stream.Part(id=voice_name)
        part.partName = voice_name
        part.insert(0, instrument.Vocalist())
        if voice_name in ("Soprano", "Alto"):
            part.insert(0, clef.TrebleClef())
        elif voice_name == "Tenor":
            part.insert(0, clef.Treble8vbClef())
        else:
            part.insert(0, clef.BassClef())
        part.append(meter.TimeSignature("4/4"))

        for kind, midi, steps in token_events(matrix[:length, voice_idx], tokenizer):
            ql = max(tokenizer.grid_quarter_length, steps * tokenizer.grid_quarter_length)
            dur = duration.Duration(ql)
            if kind == "note" and midi is not None:
                n = note.Note(int(midi))
                n.duration = dur
                part.append(n)
            else:
                r = note.Rest()
                r.duration = dur
                part.append(r)
        score.append(part)

    return score.makeMeasures()


def token_events(
    voice_tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
) -> list[tuple[str, int | None, int]]:
    events: list[tuple[str, int | None, int]] = []
    current_kind = "rest"
    current_midi: int | None = None
    current_steps = 0

    def flush() -> None:
        nonlocal current_steps
        if current_steps > 0:
            events.append((current_kind, current_midi, current_steps))
            current_steps = 0

    for raw_token in voice_tokens:
        token = int(raw_token)
        if token == tokenizer.PAD:
            break
        if token == tokenizer.HOLD and current_steps > 0:
            current_steps += 1
            continue
        if token == tokenizer.HOLD:
            token = tokenizer.REST

        if token in (tokenizer.REST, tokenizer.MASK):
            next_kind, next_midi = "rest", None
        else:
            midi = tokenizer.token_to_midi(token)
            if midi is None:
                next_kind, next_midi = "rest", None
            else:
                next_kind, next_midi = "note", midi

        if current_steps == 0:
            current_kind, current_midi, current_steps = next_kind, next_midi, 1
        elif next_kind == current_kind and next_midi == current_midi:
            current_steps += 1
        else:
            flush()
            current_kind, current_midi, current_steps = next_kind, next_midi, 1

    flush()
    if not events:
        events.append(("rest", None, 1))
    return events
