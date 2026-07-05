# SCI Readiness Audit - 2026-07-05

## Status

The ordinary SCI experiment chain is runnable and has logged non-smoke results, regenerated tables/figures, and a compiling manuscript PDF at `paper/main.pdf`.

This is not yet submission-ready. Remaining blockers are author metadata, completed expert ratings, multi-seed or external-corpus validation, and a final claim/format audit for the target journal.

## Evidence Now Aligned

- Dataset artifact: `data/processed/chorale_main.npz`, 371 music21 Bach chorales.
- Primary logged rows: LSTM baseline, vanilla/no-constraints Transformer, proposed rule-guided Transformer, masked infilling, and separately logged soprano-to-SATB.
- Main comparison now uses `proposed_neural_symbolic_rule_guided_enhanced`: pitch accuracy 0.8233, cross entropy 0.5942, rule flags 3.7823 per 100 score positions.
- Vanilla/no-constraints baseline: pitch accuracy 0.7682, cross entropy 0.8707, rule flags 14.9051 per 100 score positions.
- Expert evaluation is explicitly marked pending; the manuscript now inputs `project1_expert_eval_template.tex`.
- Roman-numeral and chord-label limitations remain explicit; ambiguous labels are `UNKNOWN`.

## Fixes Applied

- `src/chorale/evaluate.py`: removed stale rule rows before rewriting a model/task group's rule diagnostics.
- `src/chorale/make_tables.py`: changed row preference to favor enhanced full reruns over exploratory reranking sweeps; reduced the rule table to selected primary and ablation rows.
- `src/chorale/plot_results.py`: added canonical model selection for enhanced rows, fixed stale rule fallback, updated training-curve run selection, fixed extreme bar-label placement, and restricted figure source data to actually plotted rows.
- `paper/sections/*.tex`: updated abstract, results, discussion, limitations, and conclusion to current logged metrics and bounded claims.
- `paper/main.tex`: cleaned the duplicated mojibake title block and kept author metadata pending.
- `.paper/`: added a minimal paper context packet, figure inventory, claim-evidence ledger, journal-format placeholder, style overrides, reviewer-comments file, and submissions log.
- `paper/tables/project1_expert_eval_results.tex`: replaced stale partial expert numbers with an explicit expert-pending table so it cannot be mistaken for completed ratings.
- `tests/test_paper_result_consistency.py`: added regression checks that the main table uses the current enhanced primary row, expert results are not reported, the rule CSV matches primary metric totals, and figure source data excludes historical reranking rows.

## Commands Run And Outcomes

- `Import-Csv results/project1_metrics.csv ...`: inspected current logged primary metrics.
- `Import-Csv results/project1_rule_violations.csv ...`: found stale rule rows that survived when current counts were zero.
- Python CSV rebuild from `results/*metrics.json`: rebuilt `results/project1_rule_violations.csv`; replaced 16 model/task groups while preserving other historical rows.
- `.\.venv\Scripts\python.exe -m chorale.make_tables ...`: regenerated paper tables successfully.
- `.\.venv\Scripts\python.exe -m chorale.plot_results ...`: regenerated figures successfully.
- Visual inspection of `paper/figures/project1_metrics_summary.png` and `paper/figures/project1_rule_violations_bar.png`: confirmed nonblank figures and corrected stale-row/label issues.
- `xelatex -interaction=nonstopmode -halt-on-error main.tex`: compiled successfully.
- `bibtex main`: bibliography built successfully.
- Two additional `xelatex -interaction=nonstopmode -halt-on-error main.tex` runs: final PDF built successfully, 11 pages.
- `Select-String paper/main.log -Pattern 'Warning|Overfull|Underfull|Undefined|Rerun|Error'`: no substantive LaTeX warnings or overfull/underfull boxes found.
- `.\.venv\Scripts\python.exe -m pytest tests\test_evaluate_outputs.py tests\test_harmonize_user_musicxml.py tests\test_batch_harmonize.py tests\test_playback_render.py tests\test_score_audio_correspondence.py`: `14 passed in 18.17s`.
- `.\.venv\Scripts\python.exe -m chorale.plot_results --metrics-csv results\project1_metrics.csv --output-dir paper\figures --runs-dir runs --rule-csv results\project1_rule_violations.csv`: regenerated figures and source data after restricting source-data rows to plotted current rows.
- `rg -n "rerankfix|proposed_neural_symbolic_rule_guided_enhanced" paper\figures\source_data\project1_metrics_source_data.csv paper\figures\source_data\project1_rule_source_data.csv`: confirmed current enhanced rows are present and historical rerank rows are absent from current figure source data.
- `.\.venv\Scripts\python.exe -m pytest tests\test_paper_result_consistency.py tests\test_evaluate_outputs.py tests\test_harmonize_user_musicxml.py tests\test_batch_harmonize.py tests\test_playback_render.py tests\test_score_audio_correspondence.py`: `18 passed in 12.16s`.
- `xelatex -interaction=nonstopmode -halt-on-error main.tex`: rebuilt `paper/main.pdf` successfully after Introduction/Experiments edits.

## Remaining SCI Blockers

- `paper/main.tex` still has `PENDING AUTHOR INFORMATION`.
- Expert ratings are not completed; no stylistic preference, singability, cadence-quality, or pedagogy claims should be made.
- Results are one deterministic split and one logged seed; no confidence intervals or significance tests are available.
- The vanilla Transformer and "Transformer without constraints" rows refer to the same no-constraints checkpoint and should not be described as independent baselines.
- Product audio rendering is validated as a product playback path, not as an audio-synthesis endpoint in the SCI manuscript.
- The product preflight still flags long single-line inputs above `max_seq_len=256`; this remains a product limitation.
