# Paper Context

## Working Title

Explainable Neural-Symbolic Choral Harmonization with Common-Practice Harmony and Counterpoint Constraints

## One-Sentence Contribution

The paper reports a reproducible score-level SATB harmonization pipeline that combines a Transformer with automatic harmonic context, iterative masked refinement, rule-guided decoding, MusicXML export, and automatic common-practice diagnostics.

## Research Questions

- Does harmonic conditioning improve soprano-to-SATB pitch prediction relative to a no-constraints Transformer baseline?
- Does rule-guided decoding reduce selected score-level voice-leading diagnostics without treating the decoder as a complete symbolic constraint solver?
- Can the pipeline produce traceable MusicXML outputs, tables, figures, and blind expert-evaluation materials from logged local runs?

## Method Summary

The system uses the music21 Bach chorale corpus, builds deterministic train/validation/test splits, encodes SATB scores on a fixed symbolic grid, trains LSTM and Transformer baselines plus neural-symbolic variants, evaluates generated SATB MusicXML with automatic rule checks, and regenerates manuscript tables and figures from CSV/JSON result files.

## Main Findings

- The current primary comparison uses one deterministic split and one logged seed.
- The proposed rule-guided Transformer improves pitch accuracy and cross entropy relative to the vanilla/no-constraints Transformer.
- Main automatic rule flags decrease in the proposed row, but leading-tone and cadence evidence remain dependent on automatic harmonic labels.
- Expert ratings are not completed and must not be reported as evidence.

## Key Terms And Definitions

- SATB: soprano, alto, tenor, and bass score-level texture.
- MusicXML: the manuscript's external notation format.
- Rule-guided decoding: a local score-level repair and diagnostic layer, not an exhaustive constraint solver.
- Roman numeral and chord labels: automatic music21/local heuristic annotations; ambiguous labels are `UNKNOWN`.

## Current Manuscript State

- `paper/main.pdf` compiles with XeLaTeX/BibTeX.
- Tables and figures have been regenerated from logged non-smoke result files.
- The manuscript explicitly marks expert evaluation, multi-seed evidence, external-corpus validation, and target-journal formatting as incomplete.

## Known Risks Or Open Issues

- `paper/main.tex` still has `PENDING AUTHOR INFORMATION`.
- Target SCI journal is unspecified, so journal-specific formatting and declarations are not checked.
- The primary evidence is one split and one seed.
- The vanilla Transformer and "Transformer without constraints" rows refer to the same no-constraints checkpoint.
- Product playback validation is separate from the scientific claim; audio synthesis quality is not evaluated in the paper.
