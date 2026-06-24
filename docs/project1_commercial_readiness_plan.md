# Project1 商用级整改与验收计划

本文件把 Project1 从“论文实验可复现”推进到“可对外演示、可专家评审、可进入商业审查”的标准。所有结论必须来自真实结果文件、审计报告或人工评审；不得把自动指标、专家材料或试听音频包装成已经完成的商业验证。

## 当前可承诺范围

- 产品对象：score-level SATB 四部合唱和声化，输出 MusicXML 乐谱、规则违规报告、评分材料和谱面派生试听音频。
- 可以演示：40 份专家/客户试听谱例、240 个 MP3、240 个 MIDI、离线 HTML 播放器、中文评分表、完整性自检脚本、问题反馈模板。
- 可以证明：文件完整性、MusicXML/MIDI/MP3 引用关系、MP3 可解析性、MIDI 可解析性、播放器静态引用完整性、第三方 playback notice 存在、问题反馈模板存在、返回问题可批量匹配到交付 manifest。
- 不能承诺：真人合唱音色、商业级混音、专家偏好胜出、所有风格场景泛化、无版权/再分发风险。

## 当前自动验收状态

- 最新交付包：`expert_eval/project1/deliverables/project1_pro_playback_mp3_100_FINAL_20260624_131322.zip`
- ZIP SHA256：`260d18cda1a0df4cd14bc2266ea8a07b9064c3d1bed1458738ce1a36765cf422`
- ZIP 普通文件数：`856`
- 完整性 manifest 校验文件数：`852/852`
- 商业交付审计：`results/project1_commercial_delivery_audit_latest.json`
- 媒体审计：`results/project1_delivery_media_audit_latest.json`
- 谱面-播放一致性审计：`results/project1_delivery_conformance_audit_latest.json`
- 播放器 QA：`results/project1_delivery_player_qa_latest.json`
- 完整性校验：`results/project1_delivery_integrity_report_latest.json` 和 `results/project1_delivery_zip_integrity_report_latest.json`
- 商业验收报告：`results/project1_commercial_acceptance_report_latest.json`

注意：ZIP 总文件数和完整性 manifest 校验文件数统计口径不同。自指文件 `DELIVERY_FILE_MANIFEST.json`、其 SHA256 sidecar、完整性报告和收件人打开报告不纳入自身 hash manifest，因此 release manifest 显示 ZIP 内普通文件数为 856，而完整性校验显示 852 个 manifest 文件。

## 商用级必须补齐的外部证据

1. 专家盲评返回
   - 至少 3 名具备和声/对位/合唱写作背景的评分者。
   - 每人填写一份 `forms/project1_expert_rating_forms_CN.xlsx`。
   - 回收文件放入 `expert_eval/project1/returned_ratings/`。
   - 运行 `scripts/summarize_project1_expert_ratings.ps1` 生成真实统计。

2. 法律/商业再分发审查
   - 审查 music21 Bach 数据、SoundFont、FFmpeg/FluidSynth/MuseScore 工具链、生成谱例、试听音频、第三方 notice。
   - 审查通过后才能填写 `results/project1_commercial_legal_signoff.json`。
   - 未签字前，商业发布状态必须保持 `pending_external_evidence`。

3. 用户试用验收
   - 至少让目标用户完成：打开播放器、查看谱面、播放全曲和声部 stem、填写评分表、返回文件。
   - 使用交付包中的 `REVIEW_ISSUE_REPORT_TEMPLATE.csv` 记录无法播放、谱音不一致、表格看不懂、文件过大等问题。
   - 回收后放入 `expert_eval/project1/returned_issues/`，运行 `scripts/intake_project1_review_issues.ps1` 生成可追踪 issue intake 报告。

## 下一轮工程改进优先级

1. 模型质量
   - 保留 LSTM 和 vanilla Transformer 作为基线。
   - 主模型继续推进 Coconet-style iterative infilling、voice-relation attention、harmony-conditioned decoding 和 constraint reranking。
   - 新结果必须重新跑完整对比实验，不可把旧 checkpoint 指标套到新模型上。

2. 谱音一致性
   - 继续以 MusicXML 为唯一 score source of truth。
- 每个 MP3 必须由对应 MusicXML/MIDI 派生，并进入 `SCORE_AUDIO_CORRESPONDENCE.csv`。
- 发送给专家前必须通过 `delivery_media_audit`、`delivery_conformance_audit`、`traceability_audit` 和 Chrome QA。

3. 专家体验
   - 默认给专家发送一个 ZIP，不让专家手动匹配散乱文件。
   - 首屏入口使用 `START_HERE_CN.html` 和 `score_audio_player.html`。
   - 评分说明必须强调：评的是谱面和四部和声质量，音频只是辅助校听。

4. 商业边界
   - 对外表述必须是“乐谱级 SATB 和声化系统”，不能说成真人合唱生成器、音频生成模型或自动作曲万能工具。
   - 未完成专家盲评和法务签字前，不得声称“已商用发布可销售”。

## 发布前硬门槛

- `python -m pytest` 全部通过。
- `scripts/audit_project1_commercial_delivery.ps1` 通过。
- `scripts/audit_project1_delivery_media.ps1` 通过。
- `scripts/audit_project1_delivery_conformance.ps1` 通过。
- `scripts/qa_project1_delivery_player_chrome.ps1` 通过。
- `scripts/intake_project1_review_issues.ps1` 可读取返回问题文件并生成 `results/project1_review_issue_intake_latest.json`。
- `scripts/audit_project1_commercial_readiness.ps1` 显示 `all_pass=true`。
- `results/project1_expert_eval_summary.json` 来自真实回收评分。
- `results/project1_commercial_legal_signoff.json` 来自真实人工审查。

## Final no-fabrication release gate

Before any commercial-release claim, run:

```powershell
.\scripts\check_project1_commercial_release_gate.ps1
```

For an automation/blocking check, run:

```powershell
.\scripts\check_project1_commercial_release_gate.ps1 -Strict
```

This gate must remain blocked until the real expert-return summary and legal/commercial signoff are present. It recomputes the release ZIP SHA256 and rejects stale or mismatched delivery packages.
