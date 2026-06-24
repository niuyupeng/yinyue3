from __future__ import annotations

import torch
from torch import nn


class LSTMBaseline(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 256,
        layers: int = 2,
        dropout: float = 0.1,
        bidirectional: bool = True,
        max_seq_len: int = 256,
    ) -> None:
        super().__init__()
        self.vocab_size = int(vocab_size)
        self.hidden_size = int(hidden_size)
        self.pitch_embedding = nn.Embedding(vocab_size, hidden_size)
        self.voice_embedding = nn.Embedding(4, hidden_size)
        self.known_embedding = nn.Embedding(2, hidden_size)
        self.input_projection = nn.Linear(hidden_size * 4, hidden_size)
        self.lstm = nn.LSTM(
            hidden_size,
            hidden_size,
            num_layers=layers,
            dropout=dropout if layers > 1 else 0.0,
            batch_first=True,
            bidirectional=bidirectional,
        )
        out_size = hidden_size * (2 if bidirectional else 1)
        self.output = nn.Linear(out_size, 4 * vocab_size)

    def forward(
        self,
        input_tokens: torch.Tensor,
        known_mask: torch.Tensor,
        beat_positions: torch.Tensor | None = None,
        measure_indices: torch.Tensor | None = None,
        valid_mask: torch.Tensor | None = None,
        **_: torch.Tensor,
    ) -> torch.Tensor:
        batch, seq_len, voices = input_tokens.shape
        input_tokens = input_tokens.clamp(0, self.vocab_size - 1)
        token_emb = self.pitch_embedding(input_tokens)
        voice_ids = torch.arange(4, device=input_tokens.device).view(1, 1, 4)
        x = token_emb + self.voice_embedding(voice_ids) + self.known_embedding(known_mask.long().clamp(0, 1))
        x = self.input_projection(x.reshape(batch, seq_len, voices * self.hidden_size))
        encoded, _ = self.lstm(x)
        return self.output(encoded).view(batch, seq_len, 4, self.vocab_size)
