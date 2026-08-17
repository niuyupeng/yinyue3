from __future__ import annotations

import argparse
import copy
import gc
import inspect
import math
import time
from pathlib import Path

import torch
import torch.nn.functional as F
from torch.utils.data import DataLoader
from tqdm import tqdm

from chorale.data.build_dataset import build_dataset_from_config
from chorale.data.chorale_dataset import ChoraleDataset
from chorale.models.lstm_baseline import LSTMBaseline
from chorale.models.cih_s2s_transformer import CIHS2STransformer
from chorale.models.transformer import ChoraleTransformer, HierarchicalScoreTransformer, NeuralSymbolicChoraleTransformer
from chorale.utils import append_csv_row, ensure_dir, get_device, load_config, safe_torch_load, save_config, set_seed, write_json


def build_model(config: dict, vocab_size: int) -> torch.nn.Module:
    model_cfg = dict(config["model"])
    model_type = model_cfg.pop("type", "transformer")
    checkpoint_alias = model_cfg.pop("gradient_checkpointing", None)
    checkpoint_aware_models = {
        "hierarchical_score_transformer",
        "constraint_integrated_hierarchical_transformer",
        "cih_s2s_transformer",
        "constraint_integrated_hierarchical_s2s_transformer",
    }
    if checkpoint_alias is not None and model_type in checkpoint_aware_models and "use_gradient_checkpointing" not in model_cfg:
        model_cfg["use_gradient_checkpointing"] = bool(checkpoint_alias)
    if model_type == "transformer":
        return ChoraleTransformer(vocab_size=vocab_size, **model_cfg)
    if model_type in {"neural_symbolic_transformer", "ns_transformer", "relative_harmony_transformer"}:
        return NeuralSymbolicChoraleTransformer(vocab_size=vocab_size, **model_cfg)
    if model_type in {"hierarchical_score_transformer", "constraint_integrated_hierarchical_transformer"}:
        return HierarchicalScoreTransformer(vocab_size=vocab_size, **model_cfg)
    if model_type in {"cih_s2s_transformer", "constraint_integrated_hierarchical_s2s_transformer"}:
        return CIHS2STransformer(vocab_size=vocab_size, **model_cfg)
    if model_type == "lstm":
        return LSTMBaseline(vocab_size=vocab_size, **model_cfg)
    raise ValueError(f"Unknown model type: {model_type}")


def batch_to_device(batch: dict, device: torch.device) -> dict:
    out = {}
    for key, value in batch.items():
        out[key] = value.to(device) if torch.is_tensor(value) else value
    return out


def model_forward(model: torch.nn.Module, batch: dict) -> torch.Tensor:
    signature = inspect.signature(model.forward)
    optional_keys = (
        "key_tonic_pc",
        "chord_roots",
        "is_seventh_chord",
        "is_dominant_function",
        "is_phrase_end",
        "chord_label_known",
        "roman_numeral_known",
        "chord_quality_ids",
        "roman_numeral_ids",
    )
    extra = {key: batch[key] for key in optional_keys if key in batch and key in signature.parameters}
    return model(
        batch["input_tokens"],
        batch["known_mask"],
        batch.get("beat_positions"),
        batch.get("measure_indices"),
        batch.get("valid_mask"),
        **extra,
    )


def masked_cross_entropy(logits: torch.Tensor, targets: torch.Tensor, target_mask: torch.Tensor) -> tuple[torch.Tensor, float]:
    active = target_mask & (targets != 0)
    if not active.any():
        return logits.sum() * 0.0, float("nan")
    flat_logits = logits[active]
    flat_targets = targets[active]
    loss = F.cross_entropy(flat_logits, flat_targets)
    accuracy = (flat_logits.argmax(dim=-1) == flat_targets).float().mean().item()
    return loss, accuracy


@torch.no_grad()
def evaluate_loss(model: torch.nn.Module, loader: DataLoader, device: torch.device, max_batches: int | None = None) -> dict:
    model.eval()
    losses = []
    accuracies = []
    for batch_idx, batch in enumerate(loader):
        if max_batches is not None and batch_idx >= max_batches:
            break
        batch = batch_to_device(batch, device)
        logits = model_forward(model, batch)
        loss, acc = masked_cross_entropy(logits, batch["tokens"], batch["target_mask"])
        losses.append(float(loss.item()))
        if not math.isnan(acc):
            accuracies.append(acc)
    return {
        "loss": float(sum(losses) / max(1, len(losses))),
        "accuracy": float(sum(accuracies) / max(1, len(accuracies))) if accuracies else 0.0,
    }


def train(config_path: str | Path, fast_dev_run: bool = False, run_dir_override: str | None = None) -> dict:
    config = load_config(config_path)
    fallback_cfg = config.get("hardware", {}).get("oom_fallback", {})
    fallback_enabled = bool(fallback_cfg.get("enabled", False))
    max_retries = int(fallback_cfg.get("max_retries", 0)) if fallback_enabled else 0
    attempts = []
    active_config = copy.deepcopy(config)

    for attempt_idx in range(max_retries + 1):
        try:
            summary = _train_once(
                active_config,
                config_path=config_path,
                fast_dev_run=fast_dev_run,
                run_dir_override=run_dir_override,
                oom_fallback_attempt=attempt_idx,
                previous_oom_attempts=attempts,
            )
            if attempts:
                summary["oom_fallback_attempts"] = attempts
            return summary
        except RuntimeError as exc:
            if not is_cuda_oom(exc) or attempt_idx >= max_retries:
                raise
            next_config, record = make_oom_fallback_config(active_config, fallback_cfg, str(exc))
            if not record.get("changed"):
                raise
            attempts.append(record)
            clear_cuda_cache()
            active_config = next_config

    raise RuntimeError("Training exited without returning a summary")


def _train_once(
    config: dict,
    config_path: str | Path,
    fast_dev_run: bool = False,
    run_dir_override: str | None = None,
    oom_fallback_attempt: int = 0,
    previous_oom_attempts: list[dict] | None = None,
) -> dict:
    set_seed(int(config.get("seed", 1234)))
    data_path = Path(config["data"]["processed_path"])
    if not data_path.exists():
        build_dataset_from_config(config)

    run_dir = Path(run_dir_override or config["run"]["output_dir"])
    ensure_dir(run_dir)
    save_config(config, run_dir / "config.yaml")

    train_cfg = config["train"]
    batch_size = int(train_cfg.get("batch_size", 8))
    accumulation = get_gradient_accumulation(train_cfg)
    effective_batch_size = batch_size * accumulation
    task_cfg = config.get("task", {})
    train_ds = ChoraleDataset(
        data_path,
        split="train",
        task=task_cfg.get("name", "soprano_to_satb"),
        mask_prob=task_cfg.get("mask_prob", 0.45),
        seed=int(config.get("seed", 1234)),
    )
    val_ds = ChoraleDataset(
        data_path,
        split="val",
        task=task_cfg.get("name", "soprano_to_satb"),
        mask_prob=task_cfg.get("mask_prob", 0.45),
        seed=int(config.get("seed", 1234)) + 1,
    )
    train_loader = DataLoader(
        train_ds,
        batch_size=batch_size,
        shuffle=True,
        num_workers=int(train_cfg.get("num_workers", 0)),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=batch_size,
        shuffle=False,
        num_workers=int(train_cfg.get("num_workers", 0)),
    )
    device = get_device(config.get("device"))
    model = build_model(config, vocab_size=train_ds.tokenizer.vocab_size).to(device)
    optimizer = torch.optim.AdamW(
        model.parameters(),
        lr=float(train_cfg.get("learning_rate", 3e-4)),
        weight_decay=float(train_cfg.get("weight_decay", 0.0)),
    )
    use_amp = bool(train_cfg.get("mixed_precision", True)) and device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    epochs = 1 if fast_dev_run else int(train_cfg.get("epochs", 1))
    max_batches = train_cfg.get("fast_dev_batches") if fast_dev_run else None
    if max_batches is not None:
        max_batches = int(max_batches)

    best_val = float("inf")
    best_epoch = -1
    patience = int(train_cfg.get("early_stopping_patience", 10))
    history = []
    gradient_checkpointing = bool(
        config.get("model", {}).get("use_gradient_checkpointing", config.get("model", {}).get("gradient_checkpointing", False))
    )
    hardware_summary = build_training_hardware_summary(
        config=config,
        config_path=config_path,
        device=device,
        batch_size=batch_size,
        accumulation=accumulation,
        effective_batch_size=effective_batch_size,
        use_amp=use_amp,
        gradient_checkpointing=gradient_checkpointing,
        oom_fallback_attempt=oom_fallback_attempt,
        previous_oom_attempts=previous_oom_attempts or [],
    )
    write_json(hardware_summary, run_dir / "hardware_summary.json")

    for epoch in range(1, epochs + 1):
        model.train()
        start = time.time()
        reset_cuda_peak_memory(device)
        train_losses = []
        train_accs = []
        progress = tqdm(train_loader, desc=f"epoch {epoch}", leave=False)
        optimizer.zero_grad(set_to_none=True)
        for batch_idx, batch in enumerate(progress):
            if max_batches is not None and batch_idx >= max_batches:
                break
            batch = batch_to_device(batch, device)
            try:
                with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=use_amp):
                    logits = model_forward(model, batch)
                    loss, acc = masked_cross_entropy(logits, batch["tokens"], batch["target_mask"])
                    scaled_loss = loss / accumulation
                scaler.scale(scaled_loss).backward()
                should_step = ((batch_idx + 1) % accumulation == 0) or (
                    max_batches is not None and batch_idx + 1 >= max_batches
                ) or (batch_idx + 1 == len(train_loader))
                if should_step:
                    scaler.unscale_(optimizer)
                    torch.nn.utils.clip_grad_norm_(model.parameters(), float(train_cfg.get("gradient_clip", 1.0)))
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad(set_to_none=True)
                train_losses.append(float(loss.item()))
                if not math.isnan(acc):
                    train_accs.append(acc)
                progress.set_postfix(loss=f"{loss.item():.4f}")
            except RuntimeError as exc:
                if is_cuda_oom(exc):
                    clear_cuda_cache()
                raise

        val_max = max_batches if fast_dev_run else None
        val_metrics = evaluate_loss(model, val_loader, device, max_batches=val_max)
        epoch_runtime = round(time.time() - start, 3)
        early_stopping_triggered = bool(best_epoch >= 0 and epoch - best_epoch >= patience)
        memory = cuda_memory_snapshot(device)
        row = {
            "seed": int(config.get("seed", 1234)),
            "epoch": epoch,
            "train_loss": sum(train_losses) / max(1, len(train_losses)),
            "train_accuracy": sum(train_accs) / max(1, len(train_accs)) if train_accs else 0.0,
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "seconds": epoch_runtime,
            "epoch_runtime_seconds": epoch_runtime,
            "device": str(device),
            "batch_size": batch_size,
            "gradient_accumulation": accumulation,
            "effective_batch_size": effective_batch_size,
            "mixed_precision_requested": bool(train_cfg.get("mixed_precision", True)),
            "amp_enabled": use_amp,
            "gradient_checkpointing": gradient_checkpointing,
            "early_stopping_patience": patience,
            "early_stopping_triggered": early_stopping_triggered,
            "oom_fallback_attempt": oom_fallback_attempt,
            **memory,
        }
        history.append(row)
        append_csv_row(run_dir / "metrics.csv", row)
        write_json({"history": history}, run_dir / "metrics.json")

        checkpoint = {
            "model_state": model.state_dict(),
            "config": config,
            "vocab_size": train_ds.tokenizer.vocab_size,
            "tokenizer": train_ds.tokenizer.metadata(),
            "epoch": epoch,
            "val_loss": val_metrics["loss"],
        }
        torch.save(checkpoint, run_dir / "last.pt")
        if val_metrics["loss"] < best_val:
            best_val = val_metrics["loss"]
            best_epoch = epoch
            torch.save(checkpoint, run_dir / "best.pt")
        elif epoch - best_epoch >= patience:
            break

    summary = {
        "run_dir": str(run_dir),
        "best_val_loss": best_val,
        "best_epoch": best_epoch,
        "device": str(device),
        "seed": int(config.get("seed", 1234)),
        "batch_size": batch_size,
        "gradient_accumulation": accumulation,
        "effective_batch_size": effective_batch_size,
        "mixed_precision_requested": bool(train_cfg.get("mixed_precision", True)),
        "amp_enabled": use_amp,
        "gradient_checkpointing": gradient_checkpointing,
        "early_stopping_patience": patience,
        "oom_fallback_attempt": oom_fallback_attempt,
        "oom_fallback_attempts": previous_oom_attempts or [],
        **cuda_memory_snapshot(device),
    }
    write_json(summary, run_dir / "training_summary.json")
    return summary


def get_gradient_accumulation(train_cfg: dict) -> int:
    return max(1, int(train_cfg.get("gradient_accumulation", train_cfg.get("grad_accum", 1))))


def is_cuda_oom(exc: BaseException) -> bool:
    message = str(exc).lower()
    cuda_markers = ("cuda", "cublas", "cudnn")
    oom_markers = ("out of memory", "alloc_failed", "cuda error: out of memory")
    return any(marker in message for marker in cuda_markers) and any(marker in message for marker in oom_markers)


def clear_cuda_cache() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
        torch.cuda.ipc_collect()


def make_oom_fallback_config(config: dict, fallback_cfg: dict, error_message: str) -> tuple[dict, dict]:
    next_config = copy.deepcopy(config)
    train_cfg = next_config.setdefault("train", {})
    model_cfg = next_config.setdefault("model", {})
    decode_cfg = next_config.setdefault("constraint_decoder", {})

    batch_size = max(1, int(train_cfg.get("batch_size", 1)))
    accumulation = get_gradient_accumulation(train_cfg)
    beam_size = max(1, int(decode_cfg.get("beam_size", 1)))
    top_k = max(1, int(decode_cfg.get("top_k", 1)))

    min_batch_size = max(1, int(fallback_cfg.get("min_batch_size", 1)))
    max_accumulation = max(accumulation, int(fallback_cfg.get("max_gradient_accumulation", 8)))
    min_beam_size = max(1, int(fallback_cfg.get("min_beam_size", 2)))
    min_top_k = max(1, int(fallback_cfg.get("min_top_k", 4)))
    changed = False

    if batch_size > min_batch_size:
        next_batch_size = max(min_batch_size, math.ceil(batch_size / 2))
        train_cfg["batch_size"] = next_batch_size
        changed = changed or next_batch_size != batch_size
        if bool(fallback_cfg.get("preserve_effective_batch_size", True)):
            target_accumulation = min(max_accumulation, math.ceil((batch_size * accumulation) / next_batch_size))
            train_cfg["gradient_accumulation"] = max(accumulation, target_accumulation)
            train_cfg["grad_accum"] = train_cfg["gradient_accumulation"]
    elif accumulation < max_accumulation:
        train_cfg["gradient_accumulation"] = min(max_accumulation, accumulation * 2)
        train_cfg["grad_accum"] = train_cfg["gradient_accumulation"]
        changed = True

    if bool(fallback_cfg.get("enable_gradient_checkpointing", True)):
        if not bool(model_cfg.get("use_gradient_checkpointing", model_cfg.get("gradient_checkpointing", False))):
            model_cfg["use_gradient_checkpointing"] = True
            model_cfg["gradient_checkpointing"] = True
            changed = True

    if bool(fallback_cfg.get("reduce_decoder_search", True)):
        if beam_size > min_beam_size:
            decode_cfg["beam_size"] = max(min_beam_size, beam_size // 2)
            changed = True
        if top_k > min_top_k:
            decode_cfg["top_k"] = max(min_top_k, top_k // 2)
            changed = True

    record = {
        "changed": changed,
        "reason": "cuda_oom",
        "error": error_message[:500],
        "old_batch_size": batch_size,
        "new_batch_size": int(train_cfg.get("batch_size", batch_size)),
        "old_gradient_accumulation": accumulation,
        "new_gradient_accumulation": get_gradient_accumulation(train_cfg),
        "old_beam_size": beam_size,
        "new_beam_size": int(decode_cfg.get("beam_size", beam_size)),
        "old_top_k": top_k,
        "new_top_k": int(decode_cfg.get("top_k", top_k)),
        "gradient_checkpointing": bool(model_cfg.get("use_gradient_checkpointing", False)),
    }
    return next_config, record


def build_training_hardware_summary(
    config: dict,
    config_path: str | Path,
    device: torch.device,
    batch_size: int,
    accumulation: int,
    effective_batch_size: int,
    use_amp: bool,
    gradient_checkpointing: bool,
    oom_fallback_attempt: int,
    previous_oom_attempts: list[dict],
) -> dict:
    train_cfg = config.get("train", {})
    return {
        "config_path": str(config_path),
        "seed": int(config.get("seed", 1234)),
        "device": str(device),
        "device_summary": cuda_device_summary(device),
        "batch_size": batch_size,
        "gradient_accumulation": accumulation,
        "effective_batch_size": effective_batch_size,
        "mixed_precision_requested": bool(train_cfg.get("mixed_precision", True)),
        "amp_enabled": use_amp,
        "gradient_checkpointing": gradient_checkpointing,
        "num_workers": int(train_cfg.get("num_workers", 0)),
        "early_stopping_patience": int(train_cfg.get("early_stopping_patience", 10)),
        "oom_fallback_attempt": oom_fallback_attempt,
        "previous_oom_attempts": previous_oom_attempts,
    }


def cuda_device_summary(device: torch.device) -> dict:
    if device.type != "cuda" or not torch.cuda.is_available():
        return {"cuda_available": torch.cuda.is_available()}
    index = device.index if device.index is not None else torch.cuda.current_device()
    props = torch.cuda.get_device_properties(index)
    free_bytes, total_bytes = torch.cuda.mem_get_info(index)
    return {
        "cuda_available": True,
        "device_index": index,
        "device_name": torch.cuda.get_device_name(index),
        "total_memory_gb": round(total_bytes / (1024**3), 3),
        "free_memory_gb_at_start": round(free_bytes / (1024**3), 3),
        "capability": f"{props.major}.{props.minor}",
    }


def reset_cuda_peak_memory(device: torch.device) -> None:
    if device.type == "cuda" and torch.cuda.is_available():
        index = device.index if device.index is not None else torch.cuda.current_device()
        torch.cuda.reset_peak_memory_stats(index)


def cuda_memory_snapshot(device: torch.device) -> dict:
    if device.type != "cuda" or not torch.cuda.is_available():
        return {
            "gpu_memory_allocated_mb": 0.0,
            "gpu_memory_reserved_mb": 0.0,
            "gpu_peak_memory_allocated_mb": 0.0,
            "gpu_peak_memory_reserved_mb": 0.0,
        }
    index = device.index if device.index is not None else torch.cuda.current_device()
    scale = 1024**2
    return {
        "gpu_memory_allocated_mb": round(torch.cuda.memory_allocated(index) / scale, 3),
        "gpu_memory_reserved_mb": round(torch.cuda.memory_reserved(index) / scale, 3),
        "gpu_peak_memory_allocated_mb": round(torch.cuda.max_memory_allocated(index) / scale, 3),
        "gpu_peak_memory_reserved_mb": round(torch.cuda.max_memory_reserved(index) / scale, 3),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train a neural SATB chorale harmonizer.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--fast-dev-run", action="store_true")
    parser.add_argument("--run-dir", default=None)
    args = parser.parse_args()
    summary = train(args.config, fast_dev_run=args.fast_dev_run, run_dir_override=args.run_dir)
    print(summary)


if __name__ == "__main__":
    main()
