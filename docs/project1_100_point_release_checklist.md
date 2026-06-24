# Project1 商用 100/100 发布清单

本清单由当前审计证据自动生成，用于判断 Project1 是否可以从工程交付候选进入正式商业发布。自动生成文件不能替代真实专家评分、真实法务/商业签核或人工验收。

## 当前状态

- 工程交付包：`100/100`
- 工程候选包就绪：`True`
- 真实浏览器客户评审就绪：`True`
- 总商用准备度：`75.0/100`
- 最终发布门状态：`blocked`
- 商业发布就绪：`False`
- 工程验收：`pass`
- 商业验收：`pending_external_evidence`
- 最新交付 ZIP：`expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.zip`
- ZIP SHA256：`260d18cda1a0df4cd14bc2266ea8a07b9064c3d1bed1458738ce1a36765cf422`
- ZIP 普通文件数：`856`
- 完整性 manifest 校验：`852/852`
- MP3/MIDI/WAV：`240/240/0`
- 谱例数 / 播放清单行数：`40` / `240`

## 已通过的证据门

- `logged_full_experiments` (10 分)：pass；证据 `results\project1_metrics.csv`
- `commercial_delivery_package` (15 分)：pass；证据 `results\project1_commercial_delivery_audit_latest.json`
- `delivery_integrity_verification` (5 分)：pass；证据 `results\project1_delivery_integrity_report_latest.json; results\project1_delivery_zip_integrity_report_latest.json`
- `delivery_release_manifest` (5 分)：pass；证据 `results\project1_delivery_release_manifest_latest.json`
- `score_audio_traceability` (15 分)：pass；证据 `results\project1_pro_playback_traceability_audit_latest.json`
- `delivery_score_playback_conformance` (0 分)：pass；证据 `results\project1_delivery_conformance_audit_latest.json`
- `playback_license_notices` (10 分)：pass；证据 `results\project1_playback_license_audit_latest.json`
- `offline_player_browser_qa` (10 分)：pass；证据 `results\project1_delivery_player_qa_latest.json; results\project1_delivery_player_static_audit_latest.json`
- `recipient_usability_audit` (0 分)：pass；证据 `results\project1_recipient_usability_audit_latest.json`
- `paper_compile` (5 分)：pass；证据 `paper\main.pdf`
- `expert_rating_workflow` (0 分)：pass；证据 `scripts\summarize_project1_expert_ratings.ps1; src\chorale\expert_eval_tools.py; paper\tables\project1_expert_eval_results.tex`
- `review_issue_intake_workflow` (0 分)：pass；证据 `scripts\intake_project1_review_issues.ps1; src\chorale\review_issue_intake.py; results\project1_review_issue_intake_latest.json`
- `issue_evidence_packet_workflow` (0 分)：pass；证据 `scripts\build_project1_issue_evidence_packet.ps1; src\chorale\delivery_issue_packet.py; src\chorale\delivery_issue_debugger.py`
- `commercial_legal_review_packet_current` (0 分)：pass；证据 `results\project1_commercial_legal_review_packet\LEGAL_PACKET_SUMMARY.json`

## 未通过或仍需外部证据的门

- `returned_expert_evaluation` (15 分)：expert evaluation pending, invalid, or insufficient: summary_files=0, valid_files=0, summary_absolute_rows=0, summary_paired_rows=0, intake_absolute_rows=0, intake_paired_rows=0；证据 `results\project1_expert_eval_summary.json; results\project1_expert_return_intake_report_latest.json`
- `commercial_legal_signoff` (10 分)：manual legal/commercial redistribution signoff missing；证据 `results\project1_commercial_legal_signoff.json`

## 最终 Release Gate 阻塞项

- `commercial_readiness_100`
- `commercial_acceptance_ready`
- `returned_expert_evaluation`
- `commercial_legal_signoff`

## 专家评分回收要求

回收文件放入：

```text
expert_eval/project1/returned_ratings/
```

正式汇总前必须满足：

- 至少 3 份有效专家评分工作簿。
- 每份工作簿来自不同的 `rater_id`。
- 每份工作簿同时包含完整的逐首评分和 A/B 配对比较。
- 不得把 `-AllowPreliminary` 生成的 pending 表当作正式专家结果。

运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_project1_expert_returns.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\summarize_project1_expert_ratings.ps1
```

## 法务/商业签核要求

完成 `results/project1_commercial_legal_review_packet/` 中的人工审查后，才可以根据模板创建：

```text
results/project1_commercial_legal_signoff.json
```

先写入绑定当前 release 的未批准草稿：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\write_project1_commercial_legal_signoff_draft.ps1
```

草稿只是预填审核材料。只有真实责任人完成手工检查、复制最终文件到 `results/project1_commercial_legal_signoff.json` 并签署后，才能视为有效签核。

签核文件必须绑定不可变 release artifact：

- `delivery_zip`: `expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260624_131322.zip`
- `delivery_zip_sha256`: `260d18cda1a0df4cd14bc2266ea8a07b9064c3d1bed1458738ce1a36765cf422`

该文件必须真实填写 `reviewer_name`、`reviewer_role`、`review_date`，且 `approved_for_commercial_distribution` 和所有 `required_checks` 均为 `true`。

正式发布前校验最终签核：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\validate_project1_commercial_legal_signoff.ps1 -Strict
```

## 最终放行命令

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\audit_project1_commercial_readiness.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\write_project1_commercial_acceptance_report.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\check_project1_commercial_release_gate.ps1 -Strict
```

只有最后一条命令成功退出，才可以声明：

```text
commercial_release_ready = true
release_score = 100/100
```

## 禁止表述

在专家评分和法务/商业签核完成前，不得对外写：

- 已经商业发布
- 专家验证通过
- 法务审核通过
- 世界顶级音乐生成
- 真人合唱音频生成

当前可以诚实表述为：

```text
Project1 已形成可审查的 score-level SATB 和声化工程交付包，包含 MusicXML/PDF 谱例、谱面派生 MP3/MIDI 辅助试听、谱面/播放一致性审计、离线播放器、专家评分材料和法务审查包。工程交付审计通过；商业发布仍需真实专家评分回收和法务/商业签核。
```
