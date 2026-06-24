from __future__ import annotations

import torch

from chorale.train import model_forward


@torch.no_grad()
def decode_predictions(
    model: torch.nn.Module,
    batch: dict,
    mask_token: int,
    refinement_steps: int = 1,
    refinement_strategy: str = "confidence",
    remask_fraction: float = 0.35,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Decode masked SATB positions with optional iterative refinement.

    The first pass predicts all missing positions. Additional passes mask a
    deterministic checkerboard subset of target positions and rewrite it while
    conditioning on the remaining generated voices. This keeps the procedure
    lightweight enough for an RTX 4060 Ti while avoiding a purely left-to-right
    generation assumption.
    """
    refinement_steps = max(1, int(refinement_steps))
    logits = model_forward(model, batch)
    pred = logits.argmax(dim=-1)
    if refinement_steps <= 1:
        return pred, logits

    target_mask = batch["target_mask"].bool()
    working_input = batch["input_tokens"].clone()
    working_known = batch["known_mask"].clone()
    working_input[target_mask] = pred[target_mask]
    working_known[target_mask] = True

    _, seq_len, voices = working_input.shape
    time_ids = torch.arange(seq_len, device=working_input.device).view(1, seq_len, 1)
    voice_ids = torch.arange(voices, device=working_input.device).view(1, 1, voices)
    confidence = logits.softmax(dim=-1).amax(dim=-1)

    for step in range(1, refinement_steps):
        if refinement_strategy == "confidence":
            refresh_mask = low_confidence_remask(target_mask, confidence, remask_fraction)
            if step % 2 == 0:
                refresh_mask = refresh_mask | (target_mask & (((time_ids + voice_ids + step) % 4) == 0))
        else:
            refresh_mask = target_mask & (((time_ids + voice_ids + step) % 2) == 0)
        if not refresh_mask.any():
            refresh_mask = target_mask
        local_batch = dict(batch)
        local_batch["input_tokens"] = working_input.clone()
        local_batch["known_mask"] = working_known.clone()
        local_batch["input_tokens"][refresh_mask] = int(mask_token)
        local_batch["known_mask"][refresh_mask] = False
        logits = model_forward(model, local_batch)
        step_pred = logits.argmax(dim=-1)
        confidence = logits.softmax(dim=-1).amax(dim=-1)
        pred[refresh_mask] = step_pred[refresh_mask]
        working_input[refresh_mask] = step_pred[refresh_mask]
        working_known[refresh_mask] = True

    return pred, logits


def low_confidence_remask(target_mask: torch.Tensor, confidence: torch.Tensor, fraction: float) -> torch.Tensor:
    fraction = float(max(0.05, min(0.95, fraction)))
    refresh = torch.zeros_like(target_mask, dtype=torch.bool)
    batch = target_mask.shape[0]
    for item_idx in range(batch):
        active = target_mask[item_idx]
        active_count = int(active.sum().item())
        if active_count == 0:
            continue
        k = max(1, int(round(active_count * fraction)))
        scores = confidence[item_idx][active]
        _, order = torch.topk(-scores, k=min(k, active_count))
        flat_indices = torch.nonzero(active.reshape(-1), as_tuple=False).flatten()
        selected = flat_indices[order]
        item_refresh = refresh[item_idx].reshape(-1)
        item_refresh[selected] = True
    return refresh
