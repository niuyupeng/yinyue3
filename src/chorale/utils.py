from __future__ import annotations

import csv
import json
import os
import random
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import yaml


def ensure_dir(path: str | Path) -> Path:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_config(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_config(config: Mapping[str, Any], path: str | Path) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(dict(config), f, sort_keys=False)


def set_seed(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True


def get_device(preferred: str | None = None) -> torch.device:
    import torch

    requested = (preferred or os.environ.get("CHORALE_DEVICE") or "auto").strip().lower()
    if requested in {"auto", ""}:
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    if requested.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was requested but torch.cuda.is_available() is false")
        return torch.device(requested)
    if requested == "cpu":
        return torch.device("cpu")
    raise ValueError(f"Unknown device preference: {preferred}")


def write_json(data: Mapping[str, Any], path: str | Path) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as f:
        json.dump(json_safe(data), f, indent=2, ensure_ascii=False, allow_nan=False)


def json_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, np.generic):
        return json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def append_csv_row(path: str | Path, row: Mapping[str, Any]) -> None:
    path = Path(path)
    ensure_dir(path.parent)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(row.keys()))
        if write_header:
            writer.writeheader()
        writer.writerow(row)


def safe_torch_load(path: str | Path, map_location: str | torch.device = "cpu") -> Any:
    import torch

    try:
        return torch.load(path, map_location=map_location, weights_only=False)
    except TypeError:
        return torch.load(path, map_location=map_location)


def finite_or_none(value: float | int | None) -> float | int | None:
    if value is None:
        return None
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def project_root() -> Path:
    return Path(os.getcwd()).resolve()
