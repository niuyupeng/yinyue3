# Project1 External Dataset Pilot Summary

Status: `pilot_complete`
Source: Bach Chorales Figured Bass (BCFB) dataset (10.5281/zenodo.5084914)
Selected MusicXML files: 143
Intake ready: True
Parsed / encoded: 143 / 143
Dataset shape: `[143, 128, 4]`
Split counts: `{'test': 15, 'train': 114, 'val': 14}`

## Metrics

| Label | Pitch accuracy | Cross entropy | Rule flags / 100 | Parallel octaves / 100 | MusicXML export | Evaluated |
|---|---:|---:|---:|---:|---:|---:|
| pilot_transformer | 0.7634 | 0.8965 | 6.8750 | 0.0521 | 1.0000 | 15 |
| rule_baseline | 0.7476 | n/a | 15.6771 | 9.3229 | 1.0000 | 15 |

## Claim Boundary

- This is a BCFB external MusicXML source pilot using Bach chorale material.
- It supports that the pipeline can ingest, train, evaluate, baseline, and export MusicXML on this selected external source.
- It must not be cited as external-repertory generalization, expert preference, or final SCI robustness evidence.
