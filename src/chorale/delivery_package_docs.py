from __future__ import annotations

import argparse
from pathlib import Path


def write_delivery_readme(package_dir: str | Path, master_package: str = "") -> Path:
    package = Path(package_dir)
    text = f"""# Project1 专家/客户试听交付包

这是 Project1 的 score-level SATB 合唱和声化试听交付包。它用于专家评审、客户演示和内部质量检查；音频由 MusicXML 乐谱渲染得到，不是神经音频生成，也不代表真人合唱录音质量。

## 推荐使用顺序

1. 打开 `score_audio_player.html`。
2. 在页面左侧选择谱例，或搜索 `P1S01`、`P1P01_A` 等编号。
3. 对同一首谱例先听 `四声部合成 / Full choir`，再听 `钢琴参考 / Piano reference`，必要时逐个听女高、女低、男高、男低 stem。
4. 需要看谱时点击页面中的 PDF 或 MusicXML 链接。
5. 专家评分请填写 `forms/project1_expert_rating_forms_CN.xlsx`。如果只能使用 CSV，也可使用 `forms/*_CN.csv`。

## 包内关键文件

- `score_audio_player.html`：离线播放器和谱例索引。
- `forms/project1_expert_rating_forms_CN.xlsx`：中文专家评分工作簿。
- `audio_pro/pro_playback_manifest.csv`：每个音频对应的谱面、MIDI、MP3 路径。
- `audio_pro/commercial_qc_summary.json`：母版 playback 自动 QC 摘要。
- `COMMERCIAL_DELIVERY_AUDIT.json`：本交付包完整性审计。
- `PLAYBACK_LICENSE_AUDIT.json`：本地第三方 playback notice 审计。
- `THIRD_PARTY_PLAYBACK_NOTICES.md`：SoundFont/渲染工具相关说明。

## 质量状态

本包是 MP3-only 分发包，WAV 母版保留在本机 master package 中。交付包审计要求：40 首谱例、240 个 MP3、240 个 MIDI、240 行 manifest、中文 Excel 评分表、第三方 notices、播放器入口全部存在且引用无缺失。

母版包路径：

```text
{master_package or "not recorded"}
```
"""
    out = package / "DELIVERY_README_CN.md"
    out.write_text(text, encoding="utf-8")
    (package / "COMMERCIAL_PLAYBACK_README_CN.md").write_text(make_commercial_playback_readme(), encoding="utf-8")
    (package / "README_CN.md").write_text(make_expert_readme_cn(), encoding="utf-8")
    (package / "README_FOR_EXPERTS.md").write_text(make_expert_readme_en(), encoding="utf-8")
    (package / "RETURN_FILES_CHECKLIST.md").write_text(make_return_checklist(), encoding="utf-8")
    (package / "SCORING_RUBRIC.md").write_text(make_scoring_rubric(), encoding="utf-8")
    (package / "START_HERE_CN.md").write_text(make_start_here_cn(), encoding="utf-8")
    (package / "START_HERE_CN.html").write_text(make_start_here_html(), encoding="utf-8")
    return out


def make_commercial_playback_readme() -> str:
    return """# Project1 SATB 乐谱-音频交付包说明

本包用于专家评审和客户级试听演示。内容是从同一份 SATB MusicXML 乐谱自动渲染出的可听音频，不是流行音乐 MIDI 制作，也不是神经音频生成。

## 推荐打开方式

1. 打开 `score_audio_player.html`。
2. 在左侧选择谱例编号。
3. 对同一首乐谱依次试听：
   - `Full choir`：四声部合成试听。
   - `Piano reference`：钢琴参考试听，便于检查音高和节奏。
   - `Soprano/Alto/Tenor/Bass stem`：四个单独声部，便于核对谱面和音频是否对应。
4. 如需看谱，点击页面里的 `查看 PDF`、`查看源 MusicXML` 或 `查看渲染 MusicXML`。

## 质量检查状态

当前包通过自动商业交付 QC：

- 40 首谱例，每首包含 6 个音频版本。
- 240 个 MP3 和 240 个 MIDI 文件全部存在。
- 渲染 MusicXML 与源 MusicXML 在谱例编号和声部结构上逐项对应。
- stem 文件只保留目标声部，其余声部静音。
- 同一首谱例的 6 个音频版本时长已对齐。

详细机器检查结果见：

- `audio_pro/commercial_qc_summary.json`
- `audio_pro/COMMERCIAL_QC_REPORT.md`
- `audio_pro/commercial_qc_report.csv`

## 给评审专家的说明

请优先根据乐谱和对应音频判断。若音色不够自然，请以音高、节奏、声部对应关系、和声进行、声部进行为主要评价对象；音色本身不作为本项目模型质量的核心指标。

本项目研究对象是 score-level SATB choral harmonization，即四部和声乐谱生成与规则解释，不是商业级真人合唱录音合成。
"""


def make_expert_readme_cn() -> str:
    return """# Project 1 正式专家盲评材料包

英文题目：Explainable Neural-Symbolic Choral Harmonization with Common-Practice Harmony and Counterpoint Constraints

中文题目：融合传统和声与对位约束的可解释神经符号合唱和声化方法

## 评价对象

这是一个乐谱级 SATB 四部合唱和声化评价任务。请评价书面的四部乐谱：Soprano、Alto、Tenor、Bass。本项目不是神经音频生成、真人合唱录音合成或音频制作质量听辨实验。MP3、MIDI 只作为辅助听辨材料，用来帮助确认音高、节奏和声部进行；最终评分应基于乐谱中的传统和声、对位、声部进行、终止式质量和可唱性。

## 盲评说明

文件已经匿名化。其中一部分是模型输出，一部分是参考实现。请不要推测文件来源。来源对照表由项目负责人保留，不包含在专家材料包中。

## 需要填写的文件

推荐填写 `forms/project1_expert_rating_forms_CN.xlsx`。如果只能使用 CSV，请填写：

1. `forms/rater_background_form_project1_CN.csv`：每位专家填写一次。
2. `forms/absolute_rating_form_project1_CN.csv`：逐首乐谱评分。
3. `forms/paired_comparison_form_project1_CN.csv`：A/B 配对比较。

优先打开 `absolute_score_pdfs/` 和 `paired_comparison_pdfs/` 中的 PDF 乐谱。如需辅助试听，可打开 `score_audio_player.html`。
"""


def make_expert_readme_en() -> str:
    return """# Project 1 Formal Expert Blind Evaluation Package

Project title: Explainable Neural-Symbolic Choral Harmonization with Common-Practice Harmony and Counterpoint Constraints

Chinese title: 融合传统和声与对位约束的可解释神经符号合唱和声化方法

## Evaluation object

This is a score-level SATB chorale harmonization evaluation. Please evaluate the written four-part score: soprano, alto, tenor, and bass. This is not an audio-generation or production-quality listening test. MP3/MIDI playback files are included only as auxiliary aids for hearing pitch, rhythm, and voice leading; final ratings should be based on common-practice harmony, counterpoint, cadence behavior, and singability in the score.

## Blinding

The files are anonymized. Some scores are model outputs and some are reference realizations. Please do not try to infer the source. The source key is held by the project owner and is not included in this expert-facing package.

## What to complete

The recommended file is `forms/project1_expert_rating_forms_CN.xlsx`. CSV alternatives are also provided in the `forms/` folder.
"""


def make_return_checklist() -> str:
    return """# Return Checklist

Please return the completed workbook:

- `forms/project1_expert_rating_forms_CN.xlsx`

If you used CSV instead, please return:

- `forms/rater_background_form_project1_CN.csv`
- `forms/absolute_rating_form_project1_CN.csv`
- `forms/paired_comparison_form_project1_CN.csv`

Optional:

- Any additional comments or annotated PDFs, if you choose to provide them.
"""


def make_scoring_rubric() -> str:
    return """# Scoring Rubric: Project 1 SATB Chorale Evaluation

This rubric is intended to make ratings comparable across experts. The evaluation is score-based. Do not evaluate production, timbre, MIDI playback realism, or audio quality.

## Single-score ratings

For each anonymized SATB score, assign 1--5 for each dimension. A score may receive high harmonic correctness but lower singability, or vice versa. Use the comments column to identify concrete problems such as parallel fifths/octaves, unresolved sevenths, awkward leaps, bad spacing, weak cadence, or non-idiomatic doubling.

## Paired comparison

For each A/B pair, both versions share the same source sample condition. Compare the musical quality of the two written harmonizations. Prefer the version that would be more acceptable in a common-practice harmony or counterpoint class.

Valid entries: A_strongly, A_slightly, tie, B_slightly, B_strongly, uncertain.
"""


def make_start_here_cn() -> str:
    return """# 请先打开这里

这是 Project1 SATB 乐谱级合唱和声化专家/客户交付包。

## 如果你只是试听和看谱

请打开：

```text
score_audio_player.html
```

在播放器中可以选择谱例、试听四声部合成、钢琴参考和四个单独声部，并打开对应 PDF / MusicXML。

## 如果你是评审专家

请优先看 PDF 或 MusicXML 乐谱，音频只用于辅助核对音高、节奏和声部对应关系。评分请填写：

```text
forms/project1_expert_rating_forms_CN.xlsx
```

## 如果你要检查包是否完整

在解压后的文件夹里运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\\OPEN_PROJECT1_REVIEW_PACKAGE.ps1
```

该脚本会先执行完整性检查，然后打开入口页或播放器。

也可以只运行完整性检查：

```powershell
powershell -ExecutionPolicy Bypass -File .\\VERIFY_DELIVERY_INTEGRITY.ps1
```

正常结果应显示：

```text
Project1 delivery integrity PASS
```

## 重要说明

本包的 MP3/MIDI 是从 SATB MusicXML 乐谱渲染得到的试听辅助材料，不是真人合唱录音，也不是神经音频生成。评价对象是乐谱级四部和声写作质量。
"""


def make_start_here_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Project1 交付包入口</title>
  <style>
    body { font-family: "Segoe UI", "Microsoft YaHei", Arial, sans-serif; margin: 32px; line-height: 1.7; color: #17202a; }
    main { max-width: 820px; }
    a { color: #0f766e; font-weight: 650; }
    code { background: #f3f6f8; padding: 2px 5px; }
    .panel { border: 1px solid #d8dde3; padding: 16px; margin: 14px 0; }
  </style>
</head>
<body>
<main>
  <h1>Project1 SATB 乐谱级和声化交付包</h1>
  <div class="panel">
    <h2>试听和看谱</h2>
    <p><a href="score_audio_player.html">打开 score_audio_player.html</a></p>
    <p>播放器包含四声部合成、钢琴参考、女高、女低、男高、男低六类试听音频，并链接对应 PDF / MusicXML。</p>
  </div>
  <div class="panel">
    <h2>专家评分</h2>
    <p>请填写 <code>forms/project1_expert_rating_forms_CN.xlsx</code>。音频只作辅助，最终评分以乐谱为准。</p>
  </div>
  <div class="panel">
    <h2>完整性检查</h2>
    <p>Recommended one-step command: <code>powershell -ExecutionPolicy Bypass -File .\\OPEN_PROJECT1_REVIEW_PACKAGE.ps1</code></p>
    <p>运行 <code>powershell -ExecutionPolicy Bypass -File .\\VERIFY_DELIVERY_INTEGRITY.ps1</code>，正常应显示 PASS。</p>
  </div>
  <p>说明：本包 MP3/MIDI 均由 MusicXML 乐谱渲染得到，不是真人合唱录音，也不是神经音频生成。</p>
</main>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Write Project1 commercial delivery documentation.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--master-package", default="")
    args = parser.parse_args()
    print(write_delivery_readme(args.package_dir, args.master_package))


if __name__ == "__main__":
    main()
