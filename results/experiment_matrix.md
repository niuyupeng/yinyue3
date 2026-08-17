# Project1 Experiment Matrix

This matrix is a planning and evidence-status file. It does not convert pending experiments into results.

## Status Counts

- completed: 3
- completed_multiseed: 3
- completed_multiseed_same_as_vanilla: 1
- completed_single_checkpoint: 2
- completed_single_seed: 4
- covered_by_masked_infill_protocol_pending_formal_split: 1
- pending: 1
- planned: 1
- planned_config_pending: 4
- protocol_pending_completed_ratings: 1
- protocol_pending_curation: 1
- todo_not_implemented: 2
- todo_protocol_only: 1

## Rows

| ID | Section | Task | Component | Status | Evidence |
|---|---|---|---|---|---|
| baseline_rule_only_bach_s2s | matched_baseline | soprano_to_satb | Rule-only baseline | pending | results/rule_only_bach_metrics.json |
| baseline_lstm_bach_s2s | matched_baseline | soprano_to_satb | LSTM baseline | completed | results/lstm_metrics.json |
| baseline_vanilla_transformer_bach_s2s | matched_baseline | soprano_to_satb | Vanilla Transformer | completed_multiseed | results/vanilla_transformer_robustness_summary.json |
| baseline_transformer_without_constraints_bach_s2s | matched_baseline | soprano_to_satb | Transformer without constraints | completed_multiseed_same_as_vanilla | results/vanilla_transformer_robustness_summary.json |
| baseline_current_rule_guided_bach_s2s | matched_baseline | soprano_to_satb | Current rule-guided Transformer | completed_multiseed | results/project1_robustness_summary.json |
| baseline_cih_s2s_bach_s2s | matched_baseline | soprano_to_satb | CIH-S2S Transformer | completed_multiseed | results/cih_s2s_robustness_summary.json |
| baseline_deepbach_style_pseudogibbs | matched_baseline | masked_infill | DeepBach-style pseudo-Gibbs baseline | todo_not_implemented |  |
| baseline_coconet_style_infilling | matched_baseline | masked_infill | Coconet-style infilling baseline | todo_not_implemented |  |
| task_masked_satb_infilling | task | masked_infill | Masked SATB infilling | completed_single_seed | results/masked_infilling_metrics.json |
| task_bass_to_satb | task | bass_to_satb | Bass-to-SATB | todo_protocol_only |  |
| task_partial_score_completion | task | partial_score_completion | Partial-score completion | covered_by_masked_infill_protocol_pending_formal_split |  |
| ablation_no_harmonic_conditioning | component_ablation | soprano_to_satb | No harmonic conditioning | completed_single_seed | results/ablation_no_harmony_metrics.json |
| ablation_no_voice_relation_attention | component_ablation | soprano_to_satb | No voice-relation attention | completed_single_seed | results/ablation_no_voice_relation_enhanced_metrics.json |
| ablation_no_bar_level_attention_cih | component_ablation | soprano_to_satb | CIH no bar-level attention | planned_config_pending |  |
| ablation_no_iterative_refinement | component_ablation | soprano_to_satb | No iterative refinement | completed_single_seed | results/ablation_no_iterative_refinement_metrics.json |
| ablation_no_constrained_decoding_cih | constraint_decoding_analysis | soprano_to_satb | CIH no constrained decoding | planned_config_pending |  |
| ablation_local_repair_vs_constrained_beam | constraint_decoding_analysis | soprano_to_satb | Local rule repair vs constrained beam | completed_single_checkpoint | results/constraint_decoder_analysis_summary.csv |
| ablation_hard_constraints_only | constraint_decoding_analysis | soprano_to_satb | Hard constraints only | planned_config_pending |  |
| ablation_soft_constraints_only | constraint_decoding_analysis | soprano_to_satb | Soft constraints only | planned_config_pending |  |
| sensitivity_topk_beamsize | constraint_decoding_analysis | soprano_to_satb | Top-k / beam-size sensitivity | completed_single_checkpoint | results/constraint_decoder_analysis_summary.csv |
| sensitivity_hidden_depth_4060 | component_ablation | soprano_to_satb | Hidden-size/depth sensitivity | planned |  |
| external_bcfb_bach_related_pilot | external_source_protocol | soprano_to_satb | BCFB Bach-related external source | completed | results/project1_external_dataset_summary_latest.json |
| external_cpdl_candidate_pilot | external_source_protocol | soprano_to_satb | CPDL selected SATB candidates | completed | results/project1_cpdl_external_dataset_summary_expanded.json |
| external_curated_cpdl_benchmark | external_source_protocol | soprano_to_satb | Curated public-domain CPDL benchmark | protocol_pending_curation |  |
| expert_blind_evaluation_protocol | expert_evaluation_protocol | soprano_to_satb | Ground truth vs vanilla vs current rule-guided vs CIH-S2S | protocol_pending_completed_ratings | expert_eval/project1 |
