from __future__ import annotations

import torch
from torch import nn
from torch.utils.checkpoint import checkpoint as activation_checkpoint

from chorale.models.transformer import HarmonicPlanEncoder, RelativeTransformerBlock, VoiceRelationMixer


class BarSummaryAttention(nn.Module):
    """Small bar-level summary attention block for 4060-class memory budgets."""

    def __init__(self, hidden_size: int, heads: int, dropout: float = 0.1, max_measure: int = 256) -> None:
        super().__init__()
        self.max_measure = int(max_measure)
        self.summary_attention = nn.MultiheadAttention(hidden_size, heads, dropout=dropout, batch_first=True)
        self.norm = nn.LayerNorm(hidden_size)
        self.dropout = nn.Dropout(dropout)
        self.gate = nn.Sequential(nn.Linear(hidden_size * 2, hidden_size), nn.Sigmoid())

    def forward(
        self,
        x: torch.Tensor,
        measure_indices: torch.Tensor | None,
        valid_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        batch, seq_len, hidden = x.shape
        if measure_indices is None:
            measure_ids = torch.zeros(batch, seq_len, dtype=torch.long, device=x.device)
        else:
            measure_ids = measure_indices.long().clamp(0, self.max_measure)

        if valid_mask is None:
            step_mask = torch.ones(batch, seq_len, dtype=torch.bool, device=x.device)
        else:
            step_mask = valid_mask.any(dim=-1)

        pooled = torch.zeros(batch, self.max_measure + 1, hidden, device=x.device)
        counts = torch.zeros(batch, self.max_measure + 1, 1, device=x.device)
        measure_index = measure_ids.unsqueeze(-1).expand(-1, -1, hidden)
        pooled.scatter_add_(1, measure_index, x * step_mask.unsqueeze(-1).to(x.dtype))
        counts.scatter_add_(1, measure_ids.unsqueeze(-1), step_mask.unsqueeze(-1).to(x.dtype))
        pooled = pooled / counts.clamp_min(1.0)
        bar_padding_mask = counts.squeeze(-1).eq(0)

        summary, _ = self.summary_attention(
            self.norm(pooled),
            self.norm(pooled),
            self.norm(pooled),
            key_padding_mask=bar_padding_mask,
            need_weights=False,
        )
        gathered = summary.gather(1, measure_index)
        gate = self.gate(torch.cat([x, gathered], dim=-1))
        return x + gate * self.dropout(gathered)


class CIHS2STransformer(nn.Module):
    """Constraint-Integrated Hierarchical Score-to-Score Transformer.

    The public forward signature intentionally stays compatible with the
    repository training, evaluation, and MusicXML export pipeline:
    input/output tensors remain [batch, time, SATB voice].
    """

    def __init__(
        self,
        vocab_size: int,
        hidden_size: int = 384,
        local_layers: int = 2,
        plan_layers: int = 2,
        encoder_layers: int | None = None,
        layers: int | None = None,
        decoder_layers: int = 4,
        heads: int = 6,
        dropout: float = 0.1,
        max_seq_len: int = 256,
        max_measure: int = 256,
        max_relative_distance: int = 64,
        use_harmonic_plan_encoder: bool = True,
        use_voice_relation_attention: bool = True,
        use_bar_summary_attention: bool = True,
        use_bass_skeleton_head: bool = True,
        use_hierarchical_stage_fusion: bool = True,
        use_gradient_checkpointing: bool = False,
        gradient_checkpointing: bool | None = None,
        voice_relation_heads: int = 2,
    ) -> None:
        super().__init__()
        if encoder_layers is None and layers is not None:
            encoder_layers = int(layers)
        if encoder_layers is not None:
            encoder_layers = max(2, int(encoder_layers))
            local_layers = max(1, encoder_layers // 2)
            plan_layers = max(1, encoder_layers - local_layers)
        if gradient_checkpointing is not None:
            use_gradient_checkpointing = bool(gradient_checkpointing)

        self.vocab_size = int(vocab_size)
        self.hidden_size = int(hidden_size)
        self.max_seq_len = int(max_seq_len)
        self.use_harmonic_plan_encoder = bool(use_harmonic_plan_encoder)
        self.use_voice_relation_attention = bool(use_voice_relation_attention)
        self.use_bar_summary_attention = bool(use_bar_summary_attention)
        self.use_bass_skeleton_head = bool(use_bass_skeleton_head)
        self.use_hierarchical_stage_fusion = bool(use_hierarchical_stage_fusion)
        self.use_gradient_checkpointing = bool(use_gradient_checkpointing)

        self.pitch_embedding = nn.Embedding(vocab_size, hidden_size)
        self.voice_embedding = nn.Embedding(4, hidden_size)
        self.known_embedding = nn.Embedding(2, hidden_size)
        self.position_embedding = nn.Embedding(max_seq_len, hidden_size)
        self.beat_embedding = nn.Embedding(32, hidden_size)
        self.measure_embedding = nn.Embedding(max_measure + 1, hidden_size)
        self.chord_quality_embedding = nn.Embedding(64, hidden_size)
        self.roman_numeral_embedding = nn.Embedding(128, hidden_size)

        self.voice_relation = (
            VoiceRelationMixer(hidden_size=hidden_size, heads=voice_relation_heads, dropout=dropout)
            if self.use_voice_relation_attention
            else nn.Identity()
        )
        self.input_projection = nn.Linear(hidden_size * 4, hidden_size)
        self.local_blocks = nn.ModuleList(
            [
                RelativeTransformerBlock(
                    hidden_size=hidden_size,
                    heads=heads,
                    dropout=dropout,
                    max_relative_distance=max_relative_distance,
                )
                for _ in range(max(1, int(local_layers)))
            ]
        )
        self.harmonic_plan = (
            HarmonicPlanEncoder(
                hidden_size=hidden_size,
                heads=heads,
                layers=plan_layers,
                dropout=dropout,
                max_measure=max_measure,
            )
            if self.use_harmonic_plan_encoder
            else None
        )
        self.bar_summary = (
            BarSummaryAttention(hidden_size=hidden_size, heads=heads, dropout=dropout, max_measure=max_measure)
            if self.use_bar_summary_attention
            else None
        )
        self.plan_gate = nn.Sequential(nn.Linear(hidden_size * 2, hidden_size), nn.Sigmoid())
        self.plan_projection = nn.Linear(hidden_size, hidden_size)

        self.bass_skeleton_head = nn.Linear(hidden_size, vocab_size)
        self.bass_context_projection = nn.Linear(vocab_size, hidden_size)
        self.bass_decoder_blocks = nn.ModuleList(
            [
                RelativeTransformerBlock(
                    hidden_size=hidden_size,
                    heads=heads,
                    dropout=dropout,
                    max_relative_distance=max_relative_distance,
                )
                for _ in range(max(1, int(decoder_layers // 2)))
            ]
        )
        inner_layers = max(1, int(decoder_layers) - len(self.bass_decoder_blocks))
        self.inner_voice_blocks = nn.ModuleList(
            [
                RelativeTransformerBlock(
                    hidden_size=hidden_size,
                    heads=heads,
                    dropout=dropout,
                    max_relative_distance=max_relative_distance,
                )
                for _ in range(inner_layers)
            ]
        )
        self.refinement_gate = nn.Sequential(nn.Linear(hidden_size * 2, hidden_size), nn.Sigmoid())
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
        chord_quality_ids: torch.Tensor | None = None,
        roman_numeral_ids: torch.Tensor | None = None,
    ) -> torch.Tensor:
        batch, seq_len, voices = input_tokens.shape
        if voices != 4:
            raise ValueError("CIH-S2S expects four SATB voices")

        input_tokens = input_tokens.clamp(0, self.vocab_size - 1)
        token_emb = self.pitch_embedding(input_tokens)
        voice_ids = torch.arange(4, device=input_tokens.device).view(1, 1, 4)
        voice_states = token_emb + self.voice_embedding(voice_ids)
        voice_states = voice_states + self.known_embedding(known_mask.long().clamp(0, 1))
        if self.use_voice_relation_attention:
            voice_states = self.voice_relation(voice_states)

        x = self.input_projection(voice_states.reshape(batch, seq_len, voices * self.hidden_size))
        x = self.add_time_features(x, beat_positions, measure_indices)
        key_padding_mask = ~valid_mask.any(dim=-1) if valid_mask is not None else None

        for block in self.local_blocks:
            x = self.run_block(block, x, key_padding_mask)

        if self.harmonic_plan is not None:
            plan = self.harmonic_plan(
                batch_size=batch,
                seq_len=seq_len,
                device=input_tokens.device,
                valid_mask=valid_mask,
                measure_indices=measure_indices,
                key_tonic_pc=key_tonic_pc,
                chord_roots=chord_roots,
                is_seventh_chord=is_seventh_chord,
                is_dominant_function=is_dominant_function,
                is_phrase_end=is_phrase_end,
                chord_label_known=chord_label_known,
                roman_numeral_known=roman_numeral_known,
            )
            if chord_quality_ids is not None:
                plan = plan + self.chord_quality_embedding(chord_quality_ids.long().clamp(0, 63))
            if roman_numeral_ids is not None:
                plan = plan + self.roman_numeral_embedding(roman_numeral_ids.long().clamp(0, 127))
            gate = self.plan_gate(torch.cat([x, plan], dim=-1))
            x = x + gate * self.plan_projection(plan)

        if self.bar_summary is not None:
            x = self.bar_summary(x, measure_indices=measure_indices, valid_mask=valid_mask)

        bass_state = x
        for block in self.bass_decoder_blocks:
            bass_state = self.run_block(block, bass_state, key_padding_mask)

        if self.use_bass_skeleton_head and self.use_hierarchical_stage_fusion:
            bass_logits = self.bass_skeleton_head(self.norm(bass_state))
            bass_context = self.bass_context_projection(bass_logits.softmax(dim=-1))
            inner_state = bass_state + bass_context
        else:
            bass_logits = None
            inner_state = bass_state

        for block in self.inner_voice_blocks:
            inner_state = self.run_block(block, inner_state, key_padding_mask)

        if self.use_hierarchical_stage_fusion:
            gate = self.refinement_gate(torch.cat([x, inner_state], dim=-1))
            final_state = inner_state + gate * x
        else:
            final_state = inner_state
        final_state = self.norm(final_state)
        logits = torch.stack([head(final_state) for head in self.voice_heads], dim=2)
        if bass_logits is not None:
            logits[:, :, 3, :] = 0.5 * logits[:, :, 3, :] + 0.5 * bass_logits
        return logits

    def add_time_features(
        self,
        x: torch.Tensor,
        beat_positions: torch.Tensor | None,
        measure_indices: torch.Tensor | None,
    ) -> torch.Tensor:
        _, seq_len, _ = x.shape
        positions = torch.arange(seq_len, device=x.device).view(1, seq_len)
        x = x + self.position_embedding(positions.clamp(0, self.max_seq_len - 1))
        if beat_positions is not None:
            x = x + self.beat_embedding(beat_positions.clamp(0, 31))
        if measure_indices is not None:
            x = x + self.measure_embedding(measure_indices.clamp(0, self.measure_embedding.num_embeddings - 1))
        return self.dropout(x)

    def run_block(
        self,
        block: RelativeTransformerBlock,
        x: torch.Tensor,
        key_padding_mask: torch.Tensor | None,
    ) -> torch.Tensor:
        if self.use_gradient_checkpointing and self.training and x.requires_grad:
            return activation_checkpoint(lambda y: block(y, key_padding_mask=key_padding_mask), x, use_reentrant=False)
        return block(x, key_padding_mask=key_padding_mask)
