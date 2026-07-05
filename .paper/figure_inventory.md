# Figure Inventory

| Figure | Panels | What It Shows | Key Numbers | Source Script/Data | Status |
|---|---|---|---|---|---|
| Figure 1 / `project1_method_figure` | workflow schematic | SATB score-token pipeline, harmonic context, neural-symbolic Transformer, rule-guided decoding, MusicXML/report output | n/a | `src/chorale/plot_results.py`; `paper/figures/project1_method_figure.*` | regenerated |
| Figure 2 / `project1_metrics_summary` | a-d | prediction trade-off, ablation CE penalty, targeted rule changes, additional rule changes | proposed acc 0.8233; proposed CE 0.5942; vanilla acc 0.7682; vanilla CE 0.8707 | `results/project1_metrics.csv`; `results/project1_rule_violations.csv`; `src/chorale/plot_results.py` | regenerated and visually checked |
| Figure 3 / `project1_rule_violations_bar` | a-b | rule counts per 100 score positions and proposed-vs-vanilla direction | proposed P5 0.0000; proposed P8 0.0791; vanilla P5 2.7939; vanilla P8 2.4117 | `results/project1_rule_violations.csv`; `src/chorale/plot_results.py` | regenerated and visually checked |
| Figure 4 / `project1_training_curves` | a-b | selected validation loss and validation accuracy histories | single logged run per selected configuration | selected `runs/*/metrics.csv`; `src/chorale/plot_results.py` | regenerated |

## Notes

- Source data live in `paper/figures/source_data/*.csv`.
- Figures report one logged seed and no confidence intervals.
- Rule labels use score-level SATB terminology; MIDI numbers appear only as internal pitch tokens elsewhere in the project.
