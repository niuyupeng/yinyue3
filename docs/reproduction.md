# Reproduction guide

## Environment

- Windows or Linux
- Python 3.10 or 3.11
- PyTorch 2.1 or later
- `music21` 9.1 or later
- NVIDIA CUDA is optional for tests and smoke checks

Install the project in editable mode:

```powershell
python -m pip install -e ".[dev]"
```

Run the full software test suite:

```powershell
python -m pytest
```

Build a small dataset and run a CPU smoke experiment:

```powershell
.\scripts\smoke_project1.ps1
```

Run the CIH-S2S software wiring check:

```powershell
.\scripts\run_cih_s2s_smoke.ps1
```

Formal experiments must use the configuration and command ledger associated with the release. Smoke outputs are engineering checks, not publishable evidence. Do not infer missing results from a configuration file or a smoke run.
