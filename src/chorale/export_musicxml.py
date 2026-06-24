from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer, tokens_to_score
from chorale.utils import ensure_dir


def export_tokens_to_musicxml(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    output_path: str | Path,
    length: int | None = None,
    title: str = "Generated SATB Chorale",
) -> Path:
    output_path = Path(output_path)
    ensure_dir(output_path.parent)
    clean = tokenizer.sanitize_for_export(tokens, length=length)
    score = tokens_to_score(clean, tokenizer=tokenizer, length=length, title=title)
    written = score.write("musicxml", fp=str(output_path))
    return Path(written)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export a token npy file to MusicXML.")
    parser.add_argument("--tokens", required=True, help="Path to .npy token matrix.")
    parser.add_argument("--output", required=True, help="Output .musicxml path.")
    parser.add_argument("--grid", type=float, default=0.25)
    parser.add_argument("--min-midi", type=int, default=36)
    parser.add_argument("--max-midi", type=int, default=84)
    args = parser.parse_args()
    tokenizer = ScoreTokenizer(args.grid, args.min_midi, args.max_midi)
    tokens = np.load(args.tokens)
    path = export_tokens_to_musicxml(tokens, tokenizer, args.output)
    print(path)


if __name__ == "__main__":
    main()
