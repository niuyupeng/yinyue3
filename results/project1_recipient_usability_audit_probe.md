# Project1 Recipient Usability Audit

Source: `expert_eval\project1\deliverables\project1_pro_playback_mp3_100_FINAL_20260622_165044`
Score: **68/100**
Status: **failed**

## Checks

- Workbook: `{'status': 'pass', 'sheets': ['评分说明', '专家背景', '逐首评分', 'AB配对比较']}`
- Issue template: `{'status': 'pass', 'headers': ['问题编号', '谱例编号(score_id)', '材料类型(absolute/paired)', '音频版本', '问题时间点(秒)', '问题类别', '严重程度(1-5)', '具体描述', '是否影响评分', '反馈人', '备注'], 'example_rows': 2}`
- Score-audio correspondence: `{'status': 'failed', 'rows': 40}`

## Issues

- SCORE_AUDIO_CORRESPONDENCE.csv missing columns: ['render_musicxml', 'source_musicxml', 'variant']
- SCORE_AUDIO_CORRESPONDENCE.csv row count 40, expected 240
- SCORE_AUDIO_CORRESPONDENCE.csv has missing references: P1S01/None: midi -> playback_midi/absolute_score_midi/P1S01.mid; P1S01/None: mp3 -> playback_audio/absolute_score_mp3/P1S01.mp3; P1S02/None: midi -> playback_midi/absolute_score_midi/P1S02.mid; P1S02/None: mp3 -> playback_audio/absolute_score_mp3/P1S02.mp3; P1S03/None: midi -> playback_midi/absolute_score_midi/P1S03.mid; P1S03/None: mp3 -> playback_audio/absolute_score_mp3/P1S03.mp3; P1S04/None: midi -> playback_midi/absolute_score_midi/P1S04.mid; P1S04/None: mp3 -> playback_audio/absolute_score_mp3/P1S04.mp3; P1S05/None: midi -> playback_midi/absolute_score_midi/P1S05.mid; P1S05/None: mp3 -> playback_audio/absolute_score_mp3/P1S05.mp3

## Warnings

- legacy English CSV alternatives are present; START_HERE should direct reviewers to the CN workbook first
