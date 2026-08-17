from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

from chorale.train import build_model, get_gradient_accumulation, make_oom_fallback_config


ROOT = Path(__file__).resolve().parents[1]


def load_config(name: str) -> dict:
    with (ROOT / "configs" / name).open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def test_4060ti_16gb_profile_values() -> None:
    config = load_config("cih_s2s_4060ti_16gb.yaml")
    assert config["data"]["seq_len"] == 256
    assert config["model"]["hidden_size"] == 384
    assert config["model"]["encoder_layers"] == 4
    assert config["model"]["decoder_layers"] == 4
    assert config["train"]["batch_size"] == 4
    assert get_gradient_accumulation(config["train"]) == 2
    assert config["constraint_decoder"]["beam_size"] == 8
    assert config["constraint_decoder"]["top_k"] == 12
    assert config["train"]["num_workers"] == 0


def test_4060_8gb_profile_uses_low_memory_settings() -> None:
    config = load_config("cih_s2s_4060_8gb.yaml")
    assert config["model"]["hidden_size"] == 256
    assert config["model"]["encoder_layers"] == 3
    assert config["model"]["decoder_layers"] == 3
    assert config["model"]["use_gradient_checkpointing"] is True
    assert config["train"]["batch_size"] == 2
    assert get_gradient_accumulation(config["train"]) == 4
    assert config["constraint_decoder"]["beam_size"] == 4
    assert config["constraint_decoder"]["top_k"] == 8
    assert config["train"]["num_workers"] == 0


def test_cpu_smoke_profile_is_small() -> None:
    config = load_config("cih_s2s_cpu_smoke.yaml")
    assert config["data"]["max_chorales"] == 20
    assert config["train"]["epochs"] == 1
    assert config["model"]["hidden_size"] == 128
    assert config["model"]["encoder_layers"] == 2
    assert config["model"]["decoder_layers"] == 2
    assert config["constraint_decoder"]["beam_size"] == 2
    assert config["constraint_decoder"]["top_k"] == 4
    assert config["train"]["num_workers"] == 0


def test_cih_model_accepts_hardware_aliases() -> None:
    config = {
        "model": {
            "type": "cih_s2s_transformer",
            "hidden_size": 64,
            "layers": 2,
            "decoder_layers": 2,
            "heads": 4,
            "max_seq_len": 16,
            "max_measure": 16,
            "gradient_checkpointing": True,
        }
    }
    model = build_model(config, vocab_size=64)
    assert getattr(model, "use_gradient_checkpointing") is True
    assert len(model.local_blocks) == 1
    assert model.harmonic_plan is not None


def test_oom_fallback_reduces_memory_pressure() -> None:
    config = {
        "train": {"batch_size": 4, "gradient_accumulation": 2},
        "model": {"use_gradient_checkpointing": False},
        "constraint_decoder": {"beam_size": 8, "top_k": 12},
    }
    fallback = {
        "enabled": True,
        "min_batch_size": 1,
        "max_gradient_accumulation": 8,
        "preserve_effective_batch_size": True,
        "enable_gradient_checkpointing": True,
        "reduce_decoder_search": True,
        "min_beam_size": 4,
        "min_top_k": 8,
    }
    next_config, record = make_oom_fallback_config(config, fallback, "CUDA out of memory")
    assert record["changed"] is True
    assert next_config["train"]["batch_size"] == 2
    assert next_config["train"]["gradient_accumulation"] == 4
    assert next_config["model"]["use_gradient_checkpointing"] is True
    assert next_config["constraint_decoder"]["beam_size"] == 4
    assert next_config["constraint_decoder"]["top_k"] == 8


def test_check_hardware_script_summarizes_configs() -> None:
    script = ROOT / "scripts" / "check_hardware.py"
    spec = importlib.util.spec_from_file_location("check_hardware", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    summary = module.summarize_config(ROOT / "configs" / "cih_s2s_4060ti_16gb.yaml")
    assert summary["effective_batch_size"] == 8
    assert summary["mixed_precision"] is True
    assert summary["num_workers"] == 0
