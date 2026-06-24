from __future__ import annotations

import argparse
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
from chorale.models.transformer import ChoraleTransformer, NeuralSymbolicChoraleTransformer
from chorale.utils import append_csv_row, ensure_dir, get_device, load_config, safe_torch_load, save_config, set_seed, write_json


def build_model(config: dict, vocab_size: int) -> torch.nn.Module:
    model_cfg = dict(config["model"])
    model_type = model_cfg.pop("type", "transformer")
    if model_type == "transformer":
        return ChoraleTransformer(vocab_size=vocab_size, **model_cfg)
    if model_type in {"neural_symbolic_transformer", "ns_transformer", "relative_harmony_transformer"}:
        return NeuralSymbolicChoraleTransformer(vocab_size=vocab_size, **model_cfg)
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
    set_seed(int(config.get("seed", 1234)))
    data_path = Path(config["data"]["processed_path"])
    if not data_path.exists():
        build_dataset_from_config(config)

    run_dir = Path(run_dir_override or config["run"]["output_dir"])
    ensure_dir(run_dir)
    save_config(config, run_dir / "config.yaml")

    train_cfg = config["train"]
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
        batch_size=int(train_cfg.get("batch_size", 8)),
        shuffle=True,
        num_workers=int(train_cfg.get("num_workers", 0)),
    )
    val_loader = DataLoader(
        val_ds,
        batch_size=int(train_cfg.get("batch_size", 8)),
        shuffle=False,
        num_workers=int(train_cfg.get("num_workers", 0)),
    )
    device = get_device()
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

    accumulation = max(1, int(train_cfg.get("gradient_accumulation", 1)))

    for epoch in range(1, epochs + 1):
        model.train()
        start = time.time()
        train_losses = []
        train_accs = []
        progress = tqdm(train_loader, desc=f"epoch {epoch}", leave=False)
        optimizer.zero_grad(set_to_none=True)
        for batch_idx, batch in enumerate(progress):
            if max_batches is not None and batch_idx >= max_batches:
                break
            batch = batch_to_device(batch, device)
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

        val_max = max_batches if fast_dev_run else None
        val_metrics = evaluate_loss(model, val_loader, device, max_batches=val_max)
        row = {
            "epoch": epoch,
            "train_loss": sum(train_losses) / max(1, len(train_losses)),
            "train_accuracy": sum(train_accs) / max(1, len(train_accs)) if train_accs else 0.0,
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
            "seconds": round(time.time() - start, 3),
            "device": str(device),
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

    return {
        "run_dir": str(run_dir),
        "best_val_loss": best_val,
        "best_epoch": best_epoch,
        "device": str(device),
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
