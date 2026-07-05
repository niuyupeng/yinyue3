# Style Overrides

## Domain Vocabulary

- Use MusicXML, SATB, soprano-to-SATB, masked SATB infilling, chorale harmonization, Roman numeral, chord label, cadence evidence, and score-level rule diagnostics.
- Do not reframe the work as pop MIDI production, accompaniment generation, drum generation, or DAW production.
- MIDI numbers may appear only as internal symbolic pitch tokens.
- Prefer "automatic rule flags" or "automatic diagnostics" over "musical quality" unless expert ratings support the claim.
- Prefer "suggests" or "indicates" for one-seed experimental patterns.
- Use "reports" for values directly printed in tables or CSV outputs.

## Claim Boundaries

- Do not call the product or model world-class in the SCI manuscript without benchmark evidence across datasets and expert review.
- Do not claim expert preference, singability, pedagogy usefulness, or cadence quality until ratings are completed.
- Do not describe the local repair decoder as a complete symbolic constraint solver.
- Keep product audio rendering separate from the SCI paper's score-level evaluation.

## Figure And Table Naming

- Main metrics must use the current enhanced row `proposed_neural_symbolic_rule_guided_enhanced`, not older `rerankfix` or `tuned` exploratory rows.
- Expert-evaluation content must use `project1_expert_eval_template.tex` until completed expert results are available.
