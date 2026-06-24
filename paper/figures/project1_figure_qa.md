# Project 1 Figure QA Note

Backend: Python/matplotlib only.
Figure archetypes: quantitative grid for result summaries; schematic-led workflow for the method figure.
Core conclusion: the proposed model improves pitch prediction and selected rule diagnostics, but it does not solve all common-practice constraints.
Source data: see paper/figures/source_data/*.csv.
Exports: PNG preview, PDF, SVG with editable text, and TIFF at 600 dpi when supported by the local Matplotlib/Pillow stack.
Integrity note: all plotted values are read from results/project1_metrics.csv, results/project1_rule_violations.csv, or selected runs/*/metrics.csv. Smoke rows are excluded from final figures.
Statistics note: the figures report one logged seed and do not show confidence intervals or significance tests.
Training-curve note: only selected comparable training histories are plotted; other run logs are listed in source_data/project1_training_curve_exclusions.csv.
Rule denominator note: legacy CSV columns say per_100_timesteps; figure labels use per 100 score positions for score-level clarity.
