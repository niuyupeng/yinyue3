from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIGS = [
    ROOT / "configs" / "cih_s2s_4060ti_16gb.yaml",
    ROOT / "configs" / "cih_s2s_4060_8gb.yaml",
    ROOT / "configs" / "cih_s2s_cpu_smoke.yaml",
]


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_torch() -> Any | None:
    try:
        import torch

        return torch
    except Exception:
        return None


def detect_hardware() -> dict[str, Any]:
    torch = load_torch()
    runtime: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "torch_imported": torch is not None,
        "cuda_available": False,
        "cuda_device_count": 0,
        "devices": [],
    }
    if torch is None:
        return runtime

    runtime["torch_version"] = getattr(torch, "__version__", "unknown")
    runtime["cuda_built"] = getattr(torch.version, "cuda", None)
    runtime["cuda_available"] = bool(torch.cuda.is_available())
    if not torch.cuda.is_available():
        return runtime

    runtime["cuda_device_count"] = int(torch.cuda.device_count())
    for index in range(torch.cuda.device_count()):
        props = torch.cuda.get_device_properties(index)
        free_bytes, total_bytes = torch.cuda.mem_get_info(index)
        runtime["devices"].append(
            {
                "index": index,
                "name": torch.cuda.get_device_name(index),
                "capability": f"{props.major}.{props.minor}",
                "total_memory_gb": round(total_bytes / (1024**3), 3),
                "free_memory_gb": round(free_bytes / (1024**3), 3),
            }
        )
    return runtime


def get_nested(config: dict[str, Any], section: str, key: str, default: Any = None) -> Any:
    value = config.get(section, {})
    return value.get(key, default) if isinstance(value, dict) else default


def summarize_config(path: Path) -> dict[str, Any]:
    config = load_yaml(path)
    train = config.get("train", {}) or {}
    model = config.get("model", {}) or {}
    decoder = config.get("constraint_decoder", {}) or {}
    data = config.get("data", {}) or {}
    batch_size = int(train.get("batch_size", 1))
    accumulation = int(train.get("gradient_accumulation", train.get("grad_accum", 1)))
    num_workers = int(train.get("num_workers", 0))
    summary = {
        "path": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "exists": path.exists(),
        "profile": get_nested(config, "hardware", "profile", ""),
        "target_gpu": get_nested(config, "hardware", "target_gpu", ""),
        "device": config.get("device", "auto"),
        "seed": config.get("seed"),
        "seq_len": data.get("seq_len", data.get("max_seq_len", model.get("max_seq_len"))),
        "model_max_seq_len": model.get("max_seq_len"),
        "hidden_size": model.get("hidden_size"),
        "encoder_layers": model.get("encoder_layers", model.get("layers")),
        "local_layers": model.get("local_layers"),
        "plan_layers": model.get("plan_layers"),
        "decoder_layers": model.get("decoder_layers"),
        "heads": model.get("heads"),
        "batch_size": batch_size,
        "gradient_accumulation": accumulation,
        "effective_batch_size": batch_size * accumulation,
        "mixed_precision": bool(train.get("mixed_precision", False)),
        "gradient_checkpointing": bool(model.get("use_gradient_checkpointing", model.get("gradient_checkpointing", False))),
        "num_workers": num_workers,
        "early_stopping": bool(train.get("early_stopping", True)),
        "early_stopping_patience": train.get("early_stopping_patience"),
        "beam_size": decoder.get("beam_size"),
        "top_k": decoder.get("top_k"),
        "oom_fallback_enabled": bool(get_nested(config, "hardware", "oom_fallback", {}).get("enabled", False))
        if isinstance(get_nested(config, "hardware", "oom_fallback", {}), dict)
        else False,
        "warnings": [],
    }
    if summary["seq_len"] != summary["model_max_seq_len"]:
        summary["warnings"].append("data seq_len and model max_seq_len differ")
    if num_workers != 0 and platform.system().lower() == "windows":
        summary["warnings"].append("Windows profile should use num_workers=0")
    if batch_size < 1 or accumulation < 1:
        summary["warnings"].append("batch_size and gradient_accumulation must be positive")
    if int(model.get("hidden_size", 0) or 0) % int(model.get("heads", 1) or 1) != 0:
        summary["warnings"].append("hidden_size is not divisible by heads")
    if bool(train.get("mixed_precision", False)) and summary["profile"] == "cpu_smoke":
        summary["warnings"].append("CPU smoke requests AMP but train.py disables AMP without CUDA")
    return summary


def recommend_profile(runtime: dict[str, Any]) -> str:
    if not runtime.get("cuda_available"):
        return "cpu_smoke"
    device = max(runtime.get("devices", []), key=lambda item: item.get("total_memory_gb", 0), default={})
    total_gb = float(device.get("total_memory_gb", 0.0))
    name = str(device.get("name", "")).lower()
    if total_gb >= 15.0 and "4060" in name:
        return "4060ti_16gb"
    if total_gb >= 7.0 and "4060" in name:
        return "4060_8gb"
    if total_gb >= 15.0:
        return "main_16gb"
    if total_gb >= 7.0:
        return "low_vram_8gb"
    return "cpu_smoke"


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect SATB CIH-S2S hardware and config compatibility.")
    parser.add_argument("--config", action="append", default=None, help="YAML config to audit. Can be passed multiple times.")
    parser.add_argument("--out", default=str(ROOT / "results" / "hardware_check_latest.json"))
    parser.add_argument("--require-cuda", action="store_true", help="Exit non-zero when CUDA is not available.")
    args = parser.parse_args()

    config_paths = [Path(item).resolve() for item in args.config] if args.config else DEFAULT_CONFIGS
    runtime = detect_hardware()
    configs = [summarize_config(path) for path in config_paths if path.exists()]
    report = {
        "runtime": runtime,
        "recommended_profile": recommend_profile(runtime),
        "configs": configs,
        "claim_boundary": "Hardware check reports environment and YAML compatibility only; it is not a training benchmark.",
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

    if args.require_cuda and not runtime.get("cuda_available"):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
