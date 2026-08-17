# Constraint-Integrated Hierarchical Score-to-Score Transformer for Explainable SATB Harmonization

This repository contains reproducible research code, configurations, evaluation source data, and manuscript sources for score-level four-part SATB choral harmonization.

The system operates on symbolic scores. Its primary input and output format is MusicXML; MIDI, WAV, and MP3 files are optional score-derived listening aids and are not model outputs.

## Repository scope

The public research repository is intentionally limited to source code, configurations, reproducible scripts, tests, manuscript sources, figures, tables, source-data files, and compact traceable result summaries. Local virtual environments, caches, checkpoints, training logs, generated audio packages, expert-delivery bundles, and raw third-party corpora are excluded from this release tree.

## Reproduction entry points

Use Python 3.10 or 3.11 with the dependencies in `pyproject.toml`.

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

CPU software smoke check:

```powershell
.\scripts\smoke_project1.ps1
```

Hierarchical CIH-S2S smoke check:

```powershell
.\scripts\run_cih_s2s_smoke.ps1
```

Smoke experiments validate software wiring only and must not be reported as publishable scientific results.

## Manuscript

- Canonical submitted English manuscript: `paper/main_submission.tex`
- Figures, captions, and figure source data: `paper/figures/`
- The canonical English manuscript is intentionally a single self-contained entry point: `paper/main_submission.tex`.

The manuscript reports score-level automatic evaluation and does not claim human preference, broad external-repertory robustness, CP-SAT/ILP optimality, or commercial audio quality.

## Data and code availability

Canonical repository: <https://github.com/niuyupeng/yinyue3>.

The processed split metadata, aggregated evaluation tables, figure source data, benchmark manifests, and example MusicXML outputs are included where redistribution is appropriate. Source corpora remain subject to their original distribution and licensing terms. Before final publication, the exact public repository URL, release tag or commit, license, and any archival DOI must be recorded in the manuscript and submission metadata.

## Citation

Complete `CITATION.cff.template` with author-approved names, affiliations, ORCID identifiers, version, and release date before creating a final public release.

## Current release status

This is the pre-publication research release for the manuscript. It is not a claim of journal acceptance, publication, or completed expert evaluation. The release must be finalized with author metadata, a software license, and an archival tag or DOI before publication.
