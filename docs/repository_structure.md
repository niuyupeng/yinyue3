# Publication repository structure

This repository separates reusable research code from local execution state and large delivery artifacts.

| Directory | Contents | Public-release rule |
|---|---|---|
| `src/chorale/` | Tokenization, models, decoding, harmony rules, MusicXML, evaluation, and audit code | Include source files; exclude `__pycache__` |
| `configs/` | Main, baseline, ablation, external-pilot, and CIH-S2S YAML configurations | Include configurations used by the manuscript and smoke checks |
| `scripts/` | Setup, training, evaluation, table, and figure entry points | Include source scripts; exclude generated logs |
| `tests/` | Unit and integration tests | Include tests that run without private delivery assets |
| `data/` | Dataset construction notes and compact processed artifacts | Do not redistribute raw third-party corpora without license review |
| `paper/` | One canonical manuscript source/PDF plus figures, captions, and figure source data | Include the canonical source and vector figures; exclude build intermediates and alternate drafts |
| `results/` | Canonical metrics, rule diagnostics, manifests, and status reports | Include traceable summaries; exclude duplicate runtime dumps |
| `docs/` | Reproduction, availability, release, and limitation documentation | Include final release documentation |

The following local directories are deliberately absent: `.venv/`, `.git/`, `.pytest_cache/`, `.omx/`, `runs/`, `logs/`, `generated_scores/`, `external_tools/`, raw external datasets, and expert playback/delivery packages. Only the blank expert-rating form is included under `expert_eval/`.
