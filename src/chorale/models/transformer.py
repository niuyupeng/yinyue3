from __future__ import annotations

import torch
from torch import nn


class ChoraleTransformer(nn.Module):
    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 384,
        layers: int = 6,
        heads: int = 6,
        dropout: float = 0.1,
        max_seq_len: int = 256,
        max_measure: int = 256,
    ) -> None:
        super().__init__()
        self.vocab_size = int(vocab_size)
        self.hidden_size = int(hidden_size)
        self.max_seq_len = int(max_seq_len)
        self.pitch_embedding = nn.Embedding(vocab_size, hidden_size)
        self.voice_embedding = nn.Embedding(4, hidden_size)
        self.known_embedding = nn.Embedding(2, hidden_size)
        self.position_embedding = nn.Embedding(max_seq_len, hidden_size)
        self.beat_embedding = nn.Embedding(32, hidden_size)
        self.measure_embedding = nn.Embedding(max_measure + 1, hidden_size)
        self.input_projection = nn.Linear(hidden_size * 4, hidden_size)
        layer = nn.TransformerEncoderLayer(
            d_model=hidden_size,
            nhead=heads,
            dim_feedforward=hidden_size * 4,
            dropout=dropout,
            activation="gelu",
            batch_first=True,
            norm_first=True,
        )
        self.encoder = nn.TransformerEncoder(layer, num_layers=layers)
        self.dropout = nn.Dropout(dropout)
        self.output = nn.Linear(hidden_size, 4 * vocab_size)

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
        if voices != 4:
            raise ValueError("Expected four voices")
        input_tokens = input_tokens.clamp(0, self.vocab_size - 1)
        token_emb = self.pitch_embedding(input_tokens)
        voice_ids = torch.arange(4, device=input_tokens.device).view(1, 1, 4)
        voice_emb = self.voice_embedding(voice_ids)
        known_emb = self.known_embedding(known_mask.long().clamp(0, 1))
        x = token_emb + voice_emb + known_emb
        x = x.reshape(batch, seq_len, voices * self.hidden_size)
        x = self.input_projection(x)

        positions = torch.arange(seq_len, device=input_tokens.device).view(1, seq_len)
        positions = positions.clamp(0, self.max_seq_len - 1)
        x = x + self.position_embedding(positions)
        if beat_positions is not None:
            x = x + self.beat_embedding(beat_positions.clamp(0, 31))
        if measure_indices is not None:
            x = x + self.measure_embedding(measure_indices.clamp(0, self.measure_embedding.num_embeddings - 1))

        key_padding_mask = None
        if valid_mask is not None:
            key_padding_mask = ~valid_mask.any(dim=-1)
        x = self.dropout(x)
        encoded = self.encoder(x, src_key_padding_mask=key_padding_mask)
        logits = self.output(encoded).view(batch, seq_len, 4, self.vocab_size)
        return logits


class RelativePositionBias(nn.Module):
    """Learned bidirectional relative-position bias for compact chorale sequences."""

    def __init__(self, num_heads: int, max_distance: int = 64) -> None:
        super().__init__()
        self.num_heads = int(num_heads)
        self.max_distance = int(max_distance)
        self.embedding = nn.Embedding(2 * self.max_distance + 1, self.num_heads)

    def forward(self, seq_len: int, device: torch.device) -> torch.Tensor:
        positions = torch.arange(seq_len, device=device)
        relative = positions[None, :] - positions[:, None]
        relative = relative.clamp(-self.max_distance, self.max_distance) + self.max_distance
        bias = self.embedding(relative)
        return bias.permute(2, 0, 1).contiguous()


class RelativeTransformerBlock(nn.Module):
    def __init__(
        self,
        hidden_size: int,
        heads: int,
        dropout: float = 0.1,
        max_relative_distance: int = 64,
    ) -> None:
        super().__init__()
        self.heads = int(heads)
        self.norm1 = nn.LayerNorm(hidden_size)
        self.attention = nn.MultiheadAttention(hidden_size, heads, dropout=dropout, batch_first=True)
        self.relative_bias = RelativePositionBias(heads, max_distance=max_relative_distance)
        self.dropout = nn.Dropout(dropout)
        self.norm2 = nn.LayerNorm(hidden_size)
        self.ffn = nn.Sequential(
            nn.Linear(hidden_size, hidden_size * 4),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_size * 4, hidden_size),
            nn.Dropout(dropout),
        )

    def forward(self, x: torch.Tensor, key_padding_mask: torch.Tensor | None = None) -> torch.Tensor:
        batch, seq_len, _ = x.shape
        normed = self.norm1(x)
        attn_mask = self.relative_bias(seq_len, x.device).repeat(batch, 1, 1)
        padding_mask = None
        if key_padding_mask is not None:
            padding_mask = torch.zeros_like(key_padding_mask, dtype=x.dtype)
            padding_mask = padding_mask.masked_fill(key_padding_mask, float("-inf"))
        attended, _ = self.attention(
            normed,
            normed,
            normed,
            attn_mask=attn_mask,
            key_padding_mask=padding_mask,
            need_weights=False,
        )
        x = x + self.dropout(attended)
        return x + self.ffn(self.norm2(x))


class VoiceRelationMixer(nn.Module):
    """Explicit self-attention over the four SATB voices at each timestep."""

    def __init__(self, hidden_size: int, heads: int = 2, dropout: float = 0.1) -> None:
        super().__init__()
        voice_heads = max(1, min(int(heads), 4))
        while hidden_size % voice_heads != 0 and voice_heads > 1:
            voice_heads -= 1
        self.norm = nn.LayerNorm(hidden_size)
        self.attention = nn.MultiheadAttention(hidden_size, voice_heads, dropout=dropout, batch_first=True)
        self.dropout = nn.Dropout(dropout)
        self.gate = nn.Sequential(nn.Linear(hidden_size * 2, hidden_size), nn.Sigmoid())

    def forward(self, voice_states: torch.Tensor) -> torch.Tensor:
        batch, seq_len, voices, hidden = voice_states.shape
        flat = voice_states.reshape(batch * seq_len, voices, hidden)
        normed = self.norm(flat)
        mixed, _ = self.attention(normed, normed, normed, need_weights=False)
        gate = self.gate(torch.cat([flat, mixed], dim=-1))
        mixed = flat + gate * self.dropout(mixed)
        return mixed.reshape(batch, seq_len, voices, hidden)


class NeuralSymbolicChoraleTransformer(nn.Module):
    """SATB Transformer with harmonic conditioning and relative attention.

    This is the proposed model family for the project. It keeps the same
    score-level SATB token interface as the simple Transformer baseline, but
    adds automatically extracted harmonic cues and a relative-position attention
    bias inspired by recent chorale/choir Transformer work.
    """

    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 384,
        layers: int = 6,
        heads: int = 6,
        dropout: float = 0.1,
        max_seq_len: int = 256,
        max_measure: int = 256,
        max_relative_distance: int = 64,
        use_harmony_conditioning: bool = True,
        use_voice_relation_attention: bool = False,
        voice_relation_heads: int = 2,
    ) -> None:
        super().__init__()
        self.vocab_size = int(vocab_size)
        self.hidden_size = int(hidden_size)
        self.max_seq_len = int(max_seq_len)
        self.use_harmony_conditioning = bool(use_harmony_conditioning)
        self.use_voice_relation_attention = bool(use_voice_relation_attention)

        self.pitch_embedding = nn.Embedding(vocab_size, hidden_size)
        self.voice_embedding = nn.Embedding(4, hidden_size)
        self.known_embedding = nn.Embedding(2, hidden_size)
        self.position_embedding = nn.Embedding(max_seq_len, hidden_size)
        self.beat_embedding = nn.Embedding(32, hidden_size)
        self.measure_embedding = nn.Embedding(max_measure + 1, hidden_size)
        self.voice_relation = (
            VoiceRelationMixer(hidden_size=hidden_size, heads=voice_relation_heads, dropout=dropout)
            if self.use_voice_relation_attention
            else nn.Identity()
        )
        self.input_projection = nn.Linear(hidden_size * 4, hidden_size)

        self.key_embedding = nn.Embedding(12, hidden_size)
        self.chord_root_embedding = nn.Embedding(13, hidden_size)
        self.seventh_embedding = nn.Embedding(2, hidden_size)
        self.dominant_embedding = nn.Embedding(2, hidden_size)
        self.phrase_end_embedding = nn.Embedding(2, hidden_size)
        self.chord_known_embedding = nn.Embedding(2, hidden_size)
        self.roman_known_embedding = nn.Embedding(2, hidden_size)
        self.harmony_scale = nn.Parameter(torch.tensor(0.25))

        self.blocks = nn.ModuleList(
            [
                RelativeTransformerBlock(
                    hidden_size=hidden_size,
                    heads=heads,
                    dropout=dropout,
                    max_relative_distance=max_relative_distance,
                )
                for _ in range(layers)
            ]
        )
        self.norm = nn.LayerNorm(hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.voice_heads = nn.ModuleList([nn.Linear(hidden_size, vocab_size) for _ in range(4)])

    def forward(
        self,
        input_tokens: torch.Tensor,
        known_mask: torch.Tensor,
        beat_positions: torch.Tensor | None = None,
        measure_indices: torch.Tensor | None = None,
        valid_mask: torch.Tensor | None = None,
        key_tonic_pc: torch.Tensor | None = None,
        chord_roots: torch.Tensor | None = None,
        is_seventh_chord: torch.Tensor | None = None,
        is_dominant_function: torch.Tensor | None = None,
        is_phrase_end: torch.Tensor | None = None,
        chord_label_known: torch.Tensor | None = None,
        roman_numeral_known: torch.Tensor | None = None,
    ) -> torch.Tensor:
        batch, seq_len, voices = input_tokens.shape
        if voices != 4:
            raise ValueError("Expected four voices")

        input_tokens = input_tokens.clamp(0, self.vocab_size - 1)
        token_emb = self.pitch_embedding(input_tokens)
        voice_ids = torch.arange(4, device=input_tokens.device).view(1, 1, 4)
        voice_states = token_emb + self.voice_embedding(voice_ids) + self.known_embedding(known_mask.long().clamp(0, 1))
        if self.use_voice_relation_attention:
            voice_states = self.voice_relation(voice_states)
        x = self.input_projection(voice_states.reshape(batch, seq_len, voices * self.hidden_size))

        positions = torch.arange(seq_len, device=input_tokens.device).view(1, seq_len)
        x = x + self.position_embedding(positions.clamp(0, self.max_seq_len - 1))
        if beat_positions is not None:
            x = x + self.beat_embedding(beat_positions.clamp(0, 31))
        if measure_indices is not None:
            x = x + self.measure_embedding(measure_indices.clamp(0, self.measure_embedding.num_embeddings - 1))

        if self.use_harmony_conditioning:
            harmony = torch.zeros_like(x)
            if key_tonic_pc is not None:
                key_ids = key_tonic_pc.long().clamp(0, 11).view(batch, 1).expand(batch, seq_len)
                harmony = harmony + self.key_embedding(key_ids)
            if chord_roots is not None:
                root_ids = chord_roots.long().clamp(-1, 11) + 1
                harmony = harmony + self.chord_root_embedding(root_ids)
            if is_seventh_chord is not None:
                harmony = harmony + self.seventh_embedding(is_seventh_chord.long().clamp(0, 1))
            if is_dominant_function is not None:
                harmony = harmony + self.dominant_embedding(is_dominant_function.long().clamp(0, 1))
            if is_phrase_end is not None:
                harmony = harmony + self.phrase_end_embedding(is_phrase_end.long().clamp(0, 1))
            if chord_label_known is not None:
                harmony = harmony + self.chord_known_embedding(chord_label_known.long().clamp(0, 1))
            if roman_numeral_known is not None:
                harmony = harmony + self.roman_known_embedding(roman_numeral_known.long().clamp(0, 1))
            x = x + self.harmony_scale * harmony

        key_padding_mask = None
        if valid_mask is not None:
            key_padding_mask = ~valid_mask.any(dim=-1)
        x = self.dropout(x)
        for block in self.blocks:
            x = block(x, key_padding_mask=key_padding_mask)
        x = self.norm(x)
        logits = torch.stack([head(x) for head in self.voice_heads], dim=2)
        return logits
