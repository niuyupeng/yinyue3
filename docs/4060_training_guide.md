# RTX 4060 / 4060 Ti Training Guide

This project is a score-level symbolic SATB harmonization system. The CIH-S2S profiles below target MusicXML/SATB token generation, not audio synthesis.

## Profiles

| Profile | Config | Intended hardware | Notes |
|---|---|---|---|
| Main 16GB | `configs/cih_s2s_4060ti_16gb.yaml` | RTX 4060 Ti 16GB | `seq_len=256`, `hidden_size=384`, encoder/decoder layers `4/4`, batch `4`, gradient accumulation `2`, AMP on, constrained beam `8`, top-k `12`. |
| Low VRAM 8GB | `configs/cih_s2s_4060_8gb.yaml` | RTX 4060 8GB | `hidden_size=256`, encoder/decoder layers `3/3`, batch `2`, gradient accumulation `4`, checkpointing on, AMP on, constrained beam `4`, top-k `8`. |
| CPU smoke | `configs/cih_s2s_cpu_smoke.yaml` | CPU or any GPU | `device=cpu`, `max_chorales=20`, one epoch, small model, beam `2`, top-k `4`. This verifies data flow only. |

## Hardware Check

Run:

```powershell
.\.venv\Scripts\python.exe scripts\check_hardware.py
```

The script writes `results/hardware_check_latest.json` and reports CUDA availability, GPU name, total/free memory, and YAML compatibility. It is not a benchmark and does not establish publishable runtime or robustness claims.

## Training

Main RTX 4060 Ti 16GB run:

```powershell
.\scripts\train_cih_s2s.ps1
```

Low-memory RTX 4060 8GB run:

```powershell
.\scripts\train_cih_s2s.ps1 -Config configs\cih_s2s_4060_8gb.yaml
```

CPU smoke:

```powershell
.\scripts\run_cih_s2s_smoke.ps1
```

## Logged Fields

`runs/*/metrics.csv`, `runs/*/hardware_summary.json`, and `runs/*/training_summary.json` record:

- seed;
- batch size;
- gradient accumulation;
- effective batch size;
- requested mixed precision and actual AMP status;
- gradient checkpointing status;
- device;
- GPU memory allocated/reserved and peak values when CUDA is available;
- epoch runtime;
- early stopping patience and trigger status;
- OOM fallback attempt index.

## OOM Fallback

CUDA out-of-memory fallback is configured under `hardware.oom_fallback`. When enabled, `train.py` retries after reducing batch size, preserving effective batch size when possible through gradient accumulation, enabling gradient checkpointing, and reducing constrained-decoder search width. The fallback only handles CUDA OOM exceptions; ordinary code errors are not suppressed.

## Windows Notes

All 4060 profiles set `num_workers: 0` for Windows-safe DataLoader behavior. Increase this only after confirming the local music21/data-loading path is stable.

## Claim Boundary

The CPU smoke profile is a software check for train/evaluate/export/figure-generation plumbing. Full experimental claims require real multi-seed training on the target hardware and metrics read from generated CSV/JSON artifacts.
