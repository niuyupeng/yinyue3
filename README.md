# Explainable Neural-Symbolic Choral Harmonization

Chinese title: 融合传统和声与对位约束的可解释神经符号合唱和声化方法

This repository implements a runnable research codebase for score-level SATB choral harmonization with neural models, symbolic rule checking, MusicXML export, reproducible logging, and an SCI-style LaTeX paper skeleton.

The project is about common-practice four-part chorale writing. It is not a pop accompaniment, beat, bass, drum, or audio-generation project. MIDI numbers are used internally only as pitch tokens; the expected output is MusicXML SATB notation.

## What It Does

- Builds a default dataset from the built-in `music21` Bach chorales.
- Quantizes SATB scores to a fixed grid, default `quarterLength = 0.25`.
- Stores approximate automatic harmonic labels when music21 can derive them.
- Trains LSTM and vanilla Transformer baselines plus a proposed neural-symbolic Transformer for soprano-to-SATB or masked infilling.
- Checks common-practice voice leading, seventh resolution, and conservative cadence heuristics.
- Exports generated and ground-truth scores as MusicXML.
- Logs metrics to CSV and JSON without fabricating results.
- Provides a LaTeX paper skeleton with placeholders for real experiments.

## Proposed Model Improvements

The proposed model is not the LSTM baseline. The LSTM remains a comparison system only. The main model improves over the vanilla Transformer in three implemented, ablatable ways:

- Relative-position SATB attention: learned bidirectional relative attention biases model local and medium-range contrapuntal relations.
- Automatic harmonic conditioning: estimated key, chord root, seventh-chord evidence, dominant-function evidence, phrase-end flags, and harmonic-label coverage indicators are injected into the timestep representation.
- Iterative masked refinement plus rule-guided decoding: missing voices are rewritten over multiple masked passes, then conservative common-practice repairs and explanation reports are applied at the score level.

Ablation configs are provided for these components:

```powershell
configs\chorale_ablation_no_harmony.yaml
configs\chorale_ablation_no_iterative_refinement.yaml
configs\chorale_ablation_no_rule_guided_decoding.yaml
```

## Environment

Target local hardware:

- Windows 11 Professional 64-bit
- Python 3.10 or 3.11
- NVIDIA GeForce RTX 4060 Ti 16GB VRAM for local full training
- Intel i5-12400F, 16GB RAM
- CPU-only operation for tests and smoke experiments

Basic CPU setup:

```powershell
.\scripts\setup_windows.ps1
```

CUDA setup for the full RTX experiment:

```powershell
.\scripts\setup_windows_cuda.ps1
.\scripts\check_cuda.ps1 -RequireCuda
```

The CUDA setup uses the PyTorch CUDA wheel index and then verifies `torch.cuda.is_available()`. Use the official selector at https://pytorch.org/get-started/locally/ if you need to adjust the CUDA wheel version.

## CPU Smoke Test

```powershell
.\scripts\smoke_project1.ps1
```

The smoke script builds a tiny dataset from at most 20 Bach chorales, runs tests, trains for one epoch, evaluates, generates MusicXML, and writes smoke-only metrics. Smoke results validate software behavior only.

## Full Local Training

```powershell
.\scripts\run_project1_full_local.ps1
```

This script requires CUDA. If CUDA is unavailable, it stops with a clear message instead of silently running a full CPU experiment. Use `.\scripts\smoke_project1.ps1` for CPU validation. A `-CpuDebug` flag exists only for explicit debugging and must not be reported as a full RTX experiment.

The full script builds the default Bach dataset with automatic harmonic labels, trains the LSTM baseline, trains the Transformer no-constraints baseline, trains the proposed rule-guided Transformer, trains masked-infilling and soprano-to-SATB variants, evaluates each checkpoint, generates at least 10 MusicXML examples in a timestamped folder, prepares an expert-evaluation package in a timestamped folder, creates `results/project1_metrics.csv`, creates rule-violation and harmonic-label summary CSVs, and updates `paper/tables/`.

For an RTX 4060 Ti 16GB, start with batch size 8 and `gradient_accumulation: 1`. If memory is comfortable, try batch size 16. If CUDA memory is tight, keep batch size 8 and set `gradient_accumulation: 2`.

## Generate MusicXML

After training:

```powershell
python -m chorale.generate --config configs/chorale_rule_guided_decoding.yaml --checkpoint runs/chorale_rule_guided_decoding/best.pt --output-dir generated_scores/project1_manual --num-samples 10
```

The generator masks alto, tenor, and bass for a test chorale, preserves the soprano, predicts the missing voices, exports MusicXML, and writes a rule explanation report.

## Harmonize Your Own Score

For practical use, pass a user MusicXML file containing a soprano melody, bass line, or partial SATB score. The command writes a complete score-level SATB MusicXML file, a condition score, and a rule explanation report. If no checkpoint is supplied, the tool uses an explicit deterministic rule fallback and records that engine in the summary JSON.

Preflight-check a user MusicXML before harmonization:

```powershell
.\scripts\check_project1_score_input.ps1 -InputMusicXml path\to\soprano.musicxml -Task soprano_to_satb -InputRole soprano -OutputJson results\user_score_preflight.json
```

The preflight report checks parseability, part count, note count, estimated key, fixed-grid compatibility, likely known voice, normal SATB range, polyphonic melody/bass problems, and whether the score would be truncated by `max_seq_len`. It returns `pass`, `needs_review`, or `failed`. Harmonization automatically embeds the same preflight report in `*_harmonization_summary.json`; failed inputs stop before generation, while `needs_review` inputs can still generate but will be marked for manual review by the quality gate.

Soprano melody to SATB:

```powershell
.\scripts\harmonize_project1_score.ps1 -InputMusicXml path\to\soprano.musicxml -Task soprano_to_satb -InputRole soprano -OutputDir generated_scores\user_harmonizations
```

Bass line to SATB:

```powershell
.\scripts\harmonize_project1_score.ps1 -InputMusicXml path\to\bass.musicxml -Task bass_to_satb -InputRole bass -OutputDir generated_scores\user_harmonizations
```

With a trained checkpoint and optional score-derived playback:

```powershell
.\scripts\harmonize_project1_score.ps1 -InputMusicXml path\to\soprano.musicxml -Task soprano_to_satb -Checkpoint runs\chorale_soprano_to_satb\best.pt -RenderAudio
```

The harmonizer runs conservative rule-guided decoding, a symbolic postprocess, and a final tonic-closure repair by default. The postprocess preserves the known input voices, tries local generated-voice edits, accepts only edits that reduce the rule-report penalty, and records the repair summary in `*_harmonization_summary.json`. The final cadence repair is conservative: it only edits generated voices in the final known pitch event and refuses to apply if a known final pitch is not compatible with the tonic triad. The practical scripts use `12` repair passes by default because this reduced rule violations in local score-level smoke checks while still preserving the known input voice. To inspect the raw neural output, disable it:

```powershell
.\scripts\harmonize_project1_score.ps1 -InputMusicXml path\to\soprano.musicxml -Task soprano_to_satb -Checkpoint runs\chorale_soprano_to_satb\best.pt -NoSymbolicRepair
```

Playback audio is rendered from the exported MusicXML and is only a listening aid; the core deliverable remains SATB notation.

Batch harmonization for a folder of user scores:

```powershell
.\scripts\batch_harmonize_project1_scores.ps1 -InputDir path\to\musicxml_folder -Checkpoint runs\chorale_soprano_to_satb\best.pt -OutputDir generated_scores\batch_user_harmonizations
```

The batch command writes one subfolder per input score plus:

- `batch_harmonization_summary.json`
- `batch_harmonization_summary.csv`
- `batch_harmonization_summary.md`
- `batch_review_queue.csv`
- `batch_review_queue.md`

Every generated score is also passed through a practical quality gate. The gate labels a score as `pass`, `needs_review`, or `failed` using the exported MusicXML path, rule-report path, MusicXML parse validation, known-voice preservation check, violation rate, total violations, total rule penalty, and seventh-resolution count. This is an engineering/music-rule screen, not a guarantee of artistic perfection. Scores marked `needs_review` should be inspected or edited before polished delivery; failed rows usually indicate malformed input, missing output files, non-SATB MusicXML export, or a known input voice that was not preserved. Bad input files are recorded as failed rows in the summary so one malformed MusicXML file does not silently remove the rest of the batch.

Default quality thresholds are intentionally conservative for practical batch use:

- rule violations per 100 timesteps <= `12.0`
- total violations <= `24`
- total rule penalty <= `20.0`
- seventh-resolution violations <= `12`

You can tighten or relax them from PowerShell:

```powershell
.\scripts\batch_harmonize_project1_scores.ps1 -InputDir path\to\musicxml_folder -Checkpoint runs\chorale_soprano_to_satb\best.pt -OutputDir generated_scores\batch_user_harmonizations -MaxViolationsPer100 8 -MaxTotalViolations 16 -MaxTotalPenalty 12
```

## Optional Expert Playback Audio

The project remains a score-level SATB harmonization system. MP3/WAV files are optional listening aids for expert reviewers, rendered from MusicXML notation. They are not audio-generation model outputs and should not be evaluated for production quality, vocal realism, mixing, or timbre.

For higher-quality local playback rendering on Windows, install the open-source FluidSynth backend and use a SoundFont:

```powershell
.\scripts\setup_playback_tools.ps1 -DownloadMuseScoreGeneral
. .\external_tools\playback_env.ps1
.\.venv\Scripts\python.exe -m chorale.prepare_expert_playback_package --source-package expert_eval\project1\formal_blind_eval_20260616_083300\SEND_TO_EXPERTS_project1_formal_blind_eval --audio-backend fluidsynth
```

`setup_playback_tools.ps1` downloads FluidSynth when it is missing, downloads a project-local MuseScore General SoundFont when `-DownloadMuseScoreGeneral` is used, checks FFmpeg/ffprobe, and writes `external_tools/playback_env.ps1`. Use `--audio-backend auto` to try MuseScore export, then FluidSynth, then the internal deterministic renderer. The generated playback manifest records the backend, duration, RMS, and peak level for each file so silent exports can be caught before sending materials to experts. `SCORE_AUDIO_CORRESPONDENCE.csv` records the PDF/MusicXML/MIDI/WAV/MP3 mapping and four-part MusicXML validation.

## Commercial Playback Delivery

The commercial delivery workflow separates the full local master package from the smaller expert/customer sharing package.

- Full master package: contains WAV, MP3, MIDI, render MusicXML, source MusicXML, PDFs, forms, and strict commercial playback QC.
- MP3-only delivery package: contains MP3, MIDI, render MusicXML, source MusicXML, PDFs, Chinese/English forms, a local `score_audio_player.html`, third-party playback notices, and delivery audit reports. WAV references are intentionally removed from its manifest so the package does not point to files it does not include.

Build a shareable MP3-only delivery package from the QC-passed master:

```powershell
.\scripts\make_project1_commercial_delivery.ps1 -MasterPackage expert_eval\project1\pro_playback_aligned_full_20260624_eventsync
```

Audit the latest final delivery ZIP recorded in `results/project1_delivery_release_manifest_latest.json`:

```powershell
.\scripts\audit_project1_commercial_delivery.ps1 -Mode mp3_only
.\scripts\audit_project1_recipient_usability.ps1
```

The latest verified final ZIP in this checkout is:

```text
expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.zip
```

## Practical Music Functionality Audit

The project keeps a separate 100-point audit for practical music functionality. This is narrower than final commercial-release approval: it checks whether the software can accept score input, generate score-level SATB output, preserve the known input voice, export parseable MusicXML, write rule reports, produce score-derived MP3/MIDI playback assets, verify score-audio correspondence, and open a reviewer/player package with real browser QA.

Run the audit:

```powershell
.\scripts\audit_project1_music_functionality.ps1 -Strict
```

The latest local audit in this checkout writes:

```text
results\project1_music_functionality_audit_latest.json
results\project1_music_functionality_audit_latest.md
```

Current evidence status: `100/100`, with all eight gates passing. This means the music-function workflow is engineering-validated from SATB MusicXML generation through score-derived playback review. It does not claim human expert preference, legal/commercial signoff, vocal realism, or world-leading musical quality.

Its current delivery audit is `100/100`: 40 scores, 240 MP3 files, 240 MIDI files, 240 manifest rows, clean Chinese XLSX/CSV rating forms, clean Chinese delivery documentation, third-party playback notices, self-verification manifests, a standalone recipient verifier, a higher-level recipient package self-test, a reviewer issue-report template, offline player QA, MP3/manifest duration checks, MIDI parse checks, MusicXML/MIDI pitch-conformance checks, MP3 audible-signal checks, and no delivery-blocking issues. Its recipient-usability audit is also `100/100`: the ZIP contains a readable Chinese start page, the Chinese expert workbook has the required sheets and headers, the reviewer issue template has the expected columns, and the top-level `SCORE_AUDIO_CORRESPONDENCE.csv` contains 240 valid score/audio rows with six playback variants per score. These scores prove file/package integrity and score-derived playback traceability, not live human preference or vocal-timbre realism.

The delivery folder and ZIP include:

- `DELIVERY_FILE_MANIFEST.json`
- `DELIVERY_FILE_MANIFEST.sha256`
- `DELIVERY_INTEGRITY_REPORT.json`
- `DELIVERY_INTEGRITY_REPORT.md`
- `VERIFY_DELIVERY_INTEGRITY.ps1`
- `VERIFY_DELIVERY_INTEGRITY_README_CN.md`
- `OPEN_PROJECT1_REVIEW_PACKAGE.ps1`
- `PROJECT1_PACKAGE_SELF_TEST.ps1`
- `PROJECT1_PACKAGE_SELF_TEST_README_CN.md`
- `RECIPIENT_USABILITY_AUDIT.json`
- `RECIPIENT_USABILITY_AUDIT.md`
- `REVIEW_ISSUE_REPORT_TEMPLATE.csv`
- `REVIEW_ISSUE_REPORT_GUIDE_CN.md`

The recipient-side verifier does not require Python or this source repository. After extracting the ZIP, a recipient can run:

```powershell
powershell -ExecutionPolicy Bypass -File .\VERIFY_DELIVERY_INTEGRITY.ps1
```

For the easiest recipient workflow, run the one-step opener after extraction:

```powershell
powershell -ExecutionPolicy Bypass -File .\OPEN_PROJECT1_REVIEW_PACKAGE.ps1
```

It first runs the recipient package self-test when available, falls back to the integrity verifier for older packages, then opens `START_HERE_CN.html` or `score_audio_player.html`.

To run the higher-level recipient self-test directly:

```powershell
powershell -ExecutionPolicy Bypass -File .\PROJECT1_PACKAGE_SELF_TEST.ps1
```

The latest generated package was tested with these embedded scripts and passed `852/852` manifest file checks plus a 240-row package self-test.

The ZIP archive currently contains 856 regular files. The 852-file integrity count intentionally excludes self-referential files such as `DELIVERY_FILE_MANIFEST.json`, its SHA256 sidecar, generated integrity reports, recipient/open reports, and package self-test reports, because those files cannot include their own final hashes without a circular manifest. The release manifest records the ZIP file count, while the recipient verifier records the hash-checked manifest count.

The release ZIP also has adjacent release manifest files that can be sent with the ZIP:

```text
expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.release.json
expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.release.md
expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.release.sha256
```

The current ZIP SHA256 is:

```text
260d18cda1a0df4cd14bc2266ea8a07b9064c3d1bed1458738ce1a36765cf422
```

To verify that a received/unzipped package has not lost, gained, or changed files:

```powershell
.\scripts\verify_project1_delivery_integrity.ps1 -PackageDir expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322
```

To verify the ZIP archive directly before extraction:

```powershell
.\scripts\verify_project1_delivery_integrity.ps1 -ZipFile expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.zip -OutJson results\project1_delivery_zip_integrity_report_latest.json
```

The latest local folder verification report is `results/project1_delivery_integrity_report_latest.json`; the latest ZIP verification report is `results/project1_delivery_zip_integrity_report_latest.json`. Both currently check `852/852` manifest files with no missing, changed, or extra files.

The latest offline player QA record may be either a real Chrome/Edge rendering pass or an explicit static fallback. A static fallback (`fallback_static_pass`) only proves that the HTML, embedded score index, manifest, and referenced PDF/MusicXML/MIDI/MP3 files are structurally complete; it is not a screenshot-based browser playback pass. Before sending a package to live reviewers or customers, run real browser QA without `-StaticOnly` and require `customer_review_ready = true` in the release-candidate audit. The static player audit confirmed that the embedded score JSON has 40 scores, 240 playback rows, zero missing PDF/MusicXML/MIDI/MP3 references, and zero detected mojibake text files. A media audit confirmed that all 240 MP3 files are parseable by ffprobe, all 240 MIDI files are parseable by music21, and manifest durations match the probed MP3 durations. A conformance audit confirmed that all 240 MP3 files have audible signal, all 240 MIDI/render MusicXML pitch checks pass, all 240 stem target-voice checks pass, and all 240 event-level onset/pitch/duration alignment checks pass; `min_event_recall`, `min_event_precision`, and `min_duration_similarity` are all `1.0`. The QA records are written to `results/project1_delivery_player_qa_latest.json`, `results/project1_delivery_player_static_audit_latest.json`, `results/project1_delivery_media_audit_latest.json`, and `results/project1_delivery_conformance_audit_latest.json`.

For reviewer/customer delivery, run:

```powershell
.\scripts\qa_project1_delivery_player_chrome.ps1 -ChromePath "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" -StrictBrowser
.\scripts\run_project1_release_candidate_audit.ps1 -UseExistingChromeQa -StrictEngineering -StrictCustomerReview
```

On Windows, Chrome headless can be unstable on some GPU/driver combinations. The recommended customer-review gate is therefore to run the real browser QA as a separate step, preferably with Microsoft Edge when available, then run the release-candidate audit with `-UseExistingChromeQa` so the long file-audit pipeline does not overwrite a valid screenshot-based browser pass with a static fallback.

For score-audio correspondence, run the pro playback traceability audit:

```powershell
.\scripts\audit_project1_pro_playback_traceability.ps1
```

The latest verified traceability report is `results/project1_pro_playback_traceability_audit_latest.json`. It checks 240 score-derived playback entries from the full master package: 40 scores times full choir, piano reference, and four isolated SATB voice stems. The audit parses source MusicXML, rendered variant MusicXML, and MIDI files; verifies that full/piano variants preserve all four score parts; verifies that each isolated stem keeps only the target voice while muting the other three voices; validates WAV non-silence in the master package; records SHA256 hashes; and confirms that all entries are mapped by the same score ID and variant. The current traceability audit is `100/100`.

To debug a specific reviewer complaint, ask for the score ID and playback variant, then run:

```powershell
.\scripts\debug_project1_delivery_item.ps1 -ScoreId P1S01 -Variant stem_alto
```

If the reviewer reports a playback timestamp, include it:

```powershell
.\scripts\debug_project1_delivery_item.ps1 -ScoreId P1S01 -Variant stem_alto -TimeSec 12.5
```

The report is written to `results/project1_delivery_item_debug_latest.json` and `.md`. It lists the exact source MusicXML, rendered MusicXML, MIDI, MP3, media-audit row, conformance-audit row, and, when `-TimeSec` is provided, an estimated score-time mapping with quarter offset, measure number, beat estimate, measure-relative offset, measure duration, time signature, and nearby source/rendered note events. The time mapping is a deterministic triage estimate based on rendered score duration and MP3 duration; final musical judgment should still compare the displayed score and playback.

To create a self-contained engineering evidence packet for one complaint:

```powershell
.\scripts\build_project1_issue_evidence_packet.ps1 -ScoreId P1S01 -Variant stem_alto -TimeSec 12.5
```

This writes a folder and ZIP under `results/project1_issue_packets/`. The packet contains `debug_report.json`, `debug_report.md`, one-row manifest/media/conformance CSV files, and copied PDF/MusicXML/MIDI/MP3 evidence for the requested score and playback variant.

The delivery ZIP also includes `REVIEW_ISSUE_REPORT_TEMPLATE.csv` and `REVIEW_ISSUE_REPORT_GUIDE_CN.md`. Ask reviewers to use that template when reporting playback or score-display problems; it captures score ID, material type, playback variant, timestamp, severity, and a free-text description so a complaint can be traced back to the corresponding MusicXML/MIDI/MP3 row.

Returned issue files can be batch-ingested after reviewers send them back:

```powershell
New-Item -ItemType Directory -Force expert_eval\project1\returned_issues
# Put returned REVIEW_ISSUE_REPORT_TEMPLATE.csv copies into that folder, then run:
powershell -ExecutionPolicy Bypass -File .\scripts\intake_project1_review_issues.ps1
```

This writes `results/project1_review_issue_intake_latest.json`, `.csv`, and `.md`. Each row is validated and matched against the current delivery manifest, media audit, and conformance audit so playback complaints can be triaged by score ID and playback variant instead of by screenshots or chat messages. If the returned row includes a timestamp, the intake report also includes an estimated measure/beat, measure-relative offset, and nearby source/rendered pitches for faster score-audio triage.

## Expert Rating Return Workflow

The delivery ZIP includes `forms/project1_expert_rating_forms_CN.xlsx`. Ask each expert to return one completed copy of that workbook. Put returned workbooks into:

```text
expert_eval\project1\returned_ratings
```

Then summarize all returned ratings without fabricating missing values:

```powershell
.\scripts\validate_project1_expert_returns.ps1 -RatingsDir expert_eval\project1\returned_ratings
.\scripts\summarize_project1_expert_ratings.ps1 -RatingsDir expert_eval\project1\returned_ratings -OutDir results
```

Formal summarization is intentionally blocked unless the intake report finds at least three valid workbooks from distinct `rater_id` values, with complete absolute score ratings and complete A/B paired-comparison rows. For an internal draft table only, run the same command with `-AllowPreliminary`; do not use that draft output as commercial or publication evidence.

The script writes:

- `results/project1_expert_return_intake_report_latest.json`
- `results/project1_expert_eval_summary.json`
- `results/project1_expert_eval_absolute_summary.csv`
- `results/project1_expert_eval_paired_summary.csv`
- `paper/tables/project1_expert_eval_results.tex`

If no completed expert forms are present, the table explicitly says `expert evaluation pending`.

## Commercial Readiness Audit

The delivery ZIP integrity audit is not the same as commercial-release readiness. Run the aggregate readiness gate before treating the system as a commercial deliverable:

```powershell
.\scripts\audit_project1_commercial_readiness.ps1
```

The audit writes:

- `results/project1_commercial_readiness_audit.json`
- `results/project1_commercial_readiness_audit.md`

For the exact 100/100 release checklist, see `docs/project1_100_point_release_checklist.md`.
Refresh that checklist from the current JSON evidence whenever the release ZIP or audits change:

```powershell
.\scripts\write_project1_release_checklist.ps1
```

To refresh the full release-candidate evidence chain in one command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_project1_release_candidate_audit.ps1
```

Use `-StrictEngineering` to block if the package is not even ready for expert/customer review, and `-StrictCommercial` to block unless the final commercial 100/100 gate is clear. For live reviewer/customer delivery, first run `.\scripts\qa_project1_delivery_player_chrome.ps1 -StrictBrowser` and then call `.\scripts\run_project1_release_candidate_audit.ps1 -UseExistingChromeQa -StrictCustomerReview`.

The release-candidate audit also runs a commercial-claims audit:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\audit_project1_commercial_claims.ps1
```

It scans public-facing README/docs/paper/package text and blocks unsupported claims such as final commercial release, world-leading music generation, human choir recording, or neural audio generation unless they appear in an explicit warning/negation context.

As of the latest verified local audit in this checkout, the aggregate commercial-readiness score is `75/100`. The passing gates are logged experiments, final MP3-only delivery package integrity, delivery-file integrity verification, ZIP release manifest, score-audio traceability, score-playback conformance, playback-license notices, offline-player structural QA, recipient-usability audit, LaTeX paper compile, expert-rating workflow, review-issue intake workflow, and issue-evidence packet workflow. The engineering release-candidate status is `ready_for_expert_or_customer_review`; after a real Edge browser QA pass for the current release package, `customer_review_ready = true`. Static fallback is not enough for that customer-review gate. The remaining final commercial-release blocking gates are:

- returned expert evaluation: at least three completed expert workbooks must be placed in `expert_eval/project1/returned_ratings` and summarized with `.\scripts\summarize_project1_expert_ratings.ps1`
- commercial/legal signoff: generate a prefilled draft with `.\scripts\write_project1_commercial_legal_signoff_draft.ps1`, then approve a final `results/project1_commercial_legal_signoff.json` only after a real manual review of redistribution rights, SoundFont/playback-tool licenses, privacy/human-subject requirements, and commercial claims

Do not change `approved_for_commercial_distribution` to `true` unless that review has actually happened. The audit is an engineering readiness gate and is not legal advice.

Before any external commercial release claim, run the final no-fabrication release gate:

```powershell
.\scripts\check_project1_commercial_release_gate.ps1
```

Use strict mode for release blocking in automation:

```powershell
.\scripts\check_project1_commercial_release_gate.ps1 -Strict
```

This gate recomputes the release ZIP SHA256 and requires all commercial readiness gates, at least three returned expert-rating workbooks, a release-ready acceptance report, and a fully completed `results/project1_commercial_legal_signoff.json` that binds to the current release ZIP path and SHA256. In the current checkout it is expected to block until real expert returns and legal/commercial signoff are present.

To prepare the manual legal/commercial review packet:

```powershell
.\scripts\write_project1_legal_review_packet.ps1
```

This writes `results/project1_commercial_legal_review_packet/`, including dependency-license metadata, playback-license evidence, delivery release manifest, commercial claims boundary, privacy note, review checklist, and a signoff template. The packet status is `manual review required`; it is preparation for review, not approval.

To create a release-bound but still unapproved signoff draft:

```powershell
.\scripts\write_project1_commercial_legal_signoff_draft.ps1
```

This writes `results/project1_commercial_legal_signoff_DRAFT.json` with the current `delivery_zip` and `delivery_zip_sha256` filled from `results/project1_delivery_release_manifest_latest.json`. The draft deliberately keeps `approved_for_commercial_distribution = false`; it is a review aid, not permission to release.

After a real reviewer completes the legal/commercial checks and writes the final signoff file, validate it:

```powershell
.\scripts\validate_project1_commercial_legal_signoff.ps1 -Strict
```

For a single human-readable commercial acceptance summary:

```powershell
.\scripts\write_project1_commercial_acceptance_report.ps1
```

This writes:

- `results/project1_commercial_acceptance_report_latest.json`
- `results/project1_commercial_acceptance_report_latest.md`

The current acceptance report says `engineering_acceptance = pass` and `commercial_release = pending_external_evidence`. This means the software/package evidence is currently accepted, while real expert-rating returns and legal/commercial signoff are still required before claiming full commercial release readiness.

## Reproduce Tables

```powershell
.\scripts\make_project1_tables.ps1
```

This script converts available logged metrics into LaTeX table rows. It does not invent missing numbers; unavailable values are marked as `not available`.

## Repository Layout

- `src/chorale/data`: dataset parser, tokenizer, PyTorch dataset
- `src/chorale/models`: Transformer, LSTM, rule baseline
- `src/chorale/theory`: harmonic labels, rule checkers, explanation reports
- `src/chorale/train.py`: training entry point
- `src/chorale/evaluate.py`: evaluation entry point
- `src/chorale/generate.py`: MusicXML generation entry point
- `tests`: unit tests and smokeable parser/export tests
- `paper`: SCI-style LaTeX skeleton

## Limitations

- Roman numeral labels are approximate automatic labels derived with `music21`; unavailable labels are stored as `UNKNOWN`.
- Seventh-resolution and cadence checks are conservative heuristics that run only when enough harmonic context is available.
- The default generator is a single-pass masked predictor, not an autoregressive composition engine.
- The smoke experiment is for code validation only and is not a scientific result.
- Full experiments must be run locally and reported with real logged metrics.
- Smoke metrics are marked as CPU smoke experiment only and must not be described as final results.
