# Project1 External Dataset Pilot Summary

Status: `pilot_complete`
Source: Choral Public Domain Library (CPDL) (None)
Selected MusicXML files: 40
Intake ready: True
Parsed / encoded: 40 / 30
Dataset shape: `[30, 128, 4]`
Split counts: `{'test': 3, 'train': 24, 'val': 3}`

## Metrics

| Label | Pitch accuracy | Cross entropy | Rule flags / 100 | Parallel octaves / 100 | MusicXML export | Evaluated |
|---|---:|---:|---:|---:|---:|---:|
| pilot_transformer | 0.8446 | 0.7309 | 12.5000 | 0.0000 | 1.0000 | 3 |
| rule_baseline | 0.8003 | n/a | 7.0312 | 5.2083 | 1.0000 | 3 |

## Claim Boundary

- This is a CPDL score-level SATB MusicXML/MXL candidate-source pilot using a small automatically selected subset.
- It supports that the pipeline can ingest, train, evaluate, baseline, and export MusicXML on the selected CPDL files.
- It must not be cited as representative CPDL coverage, final external-corpus robustness, expert preference, or license-cleared publication evidence without additional curation and review.
