# Claim Evidence Ledger

| Claim | Section | Evidence | Certainty Allowed | Missing Check | Revision Status |
|---|---|---|---|---|---|
| The dataset contains 371 music21 Bach chorales with 297/37/37 train/validation/test split. | Experiment setup; reproducibility | `data/processed/chorale_main.npz`; `paper/sections/experiment_setup.tex`; `paper/sections/reproducibility_statement.tex` | reports | none | supported |
| The proposed rule-guided Transformer improves pitch accuracy over the vanilla/no-constraints Transformer from 0.7682 to 0.8233. | Abstract; Results; Conclusion | `results/project1_metrics.csv`; `paper/tables/project1_main_results.tex`; `paper/figures/source_data/project1_metrics_source_data.csv` | reports / indicates | multi-seed variance missing | supported for single split/seed |
| The proposed rule-guided Transformer reduces cross entropy from 0.8707 to 0.5942 relative to the vanilla/no-constraints Transformer. | Abstract; Results; Conclusion | `results/project1_metrics.csv`; `paper/tables/project1_main_results.tex` | reports / indicates | multi-seed variance missing | supported for single split/seed |
| Aggregate automatic rule flags decrease from 14.9051 to 3.7823 per 100 score positions in the main comparison. | Abstract; Results; Discussion | `results/project1_metrics.csv`; `paper/tables/project1_main_results.tex`; `paper/figures/project1_metrics_summary.*` | reports / indicates | rule diagnostics are automatic, not expert judgment | supported with limitation |
| Parallel-octave flags decrease from 2.4117 to 0.0791 per 100 score positions in the main comparison. | Abstract; Results; Figure captions | `results/project1_metrics.csv`; `results/project1_rule_violations.csv`; `paper/tables/project1_rule_violations.tex` | reports / indicates | rule diagnostics are automatic | supported with limitation |
| Removing harmonic conditioning reduces pitch accuracy to 0.7716 and increases cross entropy to 0.8469. | Results | `results/project1_metrics.csv`; `paper/tables/project1_ablation_results.tex` | reports / suggests | ablation is one logged run | supported for logged ablation |
| Removing iterative refinement keeps accuracy similar but increases parallel-octave diagnostics to 8.3158 per 100 score positions. | Results | `results/project1_metrics.csv`; `paper/tables/project1_ablation_results.tex`; `paper/tables/project1_rule_violations.tex` | reports / suggests | ablation is one logged run | supported for logged ablation |
| Removing rule-guided decoding keeps pitch accuracy similar but increases total automatic rule flags to 32.6173 per 100 score positions. | Results | `results/project1_metrics.csv`; `paper/tables/project1_ablation_results.tex` | reports / suggests | ablation is one logged run | supported for logged ablation |
| Generated-score harmonic coverage ranges from 0.9844 to 0.9942 in the logged primary rows. | Results | `paper/tables/project1_harmony_label_coverage.tex`; `results/project1_metrics.csv` | reports | labels are automatic and approximate | supported with limitation |
| Expert evaluation remains pending. | Abstract; Results; Limitations | `paper/tables/project1_expert_eval_template.tex`; absence of `results/project1_expert_eval_summary.csv` | reports absence | completed expert ratings missing | gap by design |
| The work does not establish multi-seed robustness, complete constraint solving, or human musical preference. | Discussion; Limitations; Conclusion | one seed in `paper/sections/reproducibility_statement.tex`; pending expert template | limitation statement | more experiments and ratings missing | supported as limitation |

## Audit Rules

- Do not cite `paper/tables/project1_expert_eval_results.tex` as evidence unless completed expert-rating inputs are present and regenerated.
- Treat smoke experiments as software checks only.
- If Roman numeral or chord labels are unavailable, mark the limitation explicitly instead of substituting invented labels.
- If a future rerun changes `results/project1_metrics.csv`, regenerate tables/figures and update this ledger before revising Abstract, Results, or Conclusion.
