# Expert Evaluation Protocol

This protocol prepares blind human evaluation materials for Project1 SATB harmonization. It is not evidence of completed expert ratings.

## Conditions

The blinded set should include ground truth, vanilla Transformer, current rule-guided Transformer, and CIH-S2S Transformer. If a condition has only smoke-level outputs, mark it as smoke-only and do not use it for formal paper claims.

## Rating Dimensions

Raters score each anonymized score from 1 to 5 for harmonic correctness, voice-leading correctness, seventh-resolution correctness, cadence quality, singability, stylistic consistency, usefulness for composition pedagogy, and overall preference.

## Blindness

The expert-facing packet contains only anonymized IDs. The condition key is stored in `internal_key_do_not_send.csv` and must not be sent to raters.

## Analysis Plan

After at least three completed expert rating forms from distinct raters are returned, compute per-dimension means and paired comparisons where the same source excerpt is rated across conditions. Until then, report the status as `expert evaluation pending`.

## Claim Boundary

Do not write that experts preferred a model, that CIH-S2S is more musical, or that human evaluation is complete until returned forms are validated and summarized.
