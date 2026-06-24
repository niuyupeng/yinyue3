from __future__ import annotations

import argparse
import csv
import shutil
from datetime import datetime
from pathlib import Path

from music21 import converter, instrument, stream

from chorale.playback_render import (
    PlaybackRenderSettings,
    export_midi_with_musescore,
    export_pdf_with_musescore,
    render_musicxml_to_audio,
)
from chorale.verify_expert_playback_package import audit_package, write_audit_outputs


PROJECT_TITLE = "Explainable Neural-Symbolic Choral Harmonization with Common-Practice Harmony and Counterpoint Constraints"
PROJECT_TITLE_CN = "融合传统和声与对位约束的可解释神经符号合唱和声化方法"


EMAIL_TEMPLATE_EN = f"""Subject: Expert blind evaluation request for SATB chorale harmonization study

Dear Professor / Expert,

I am conducting a study on score-level SATB chorale harmonization: "{PROJECT_TITLE}".

Attached is a blind evaluation package containing anonymized SATB score examples in PDF and MusicXML formats. The package also includes MP3/WAV playback files as optional listening aids. Please evaluate the written four-part scores according to common-practice harmony, counterpoint, voice leading, cadence quality, singability, stylistic consistency, and usefulness for composition pedagogy.

This is not an audio-generation or production-quality listening test. Playback may be used only as an auxiliary tool; the ratings should be based on the written score.

Could you please complete the following files in the `forms/` folder:

1. `rater_background_form_project1.csv`
2. `absolute_rating_form_project1.csv`
3. `paired_comparison_form_project1.csv`

The files are anonymized, and the source key is not included in the expert-facing package.

Thank you very much for your time and expertise.
"""


EXPERT_README_EN = f"""# Project 1 Formal Expert Blind Evaluation Package

Project title: {PROJECT_TITLE}
Chinese title: {PROJECT_TITLE_CN}

## Evaluation object

This is a score-level SATB chorale harmonization evaluation. Please evaluate the written four-part score: soprano, alto, tenor, and bass. This is not an audio-generation or production-quality listening test. MP3/WAV/MIDI playback files are included only as auxiliary aids for hearing pitches, rhythm, and voice leading; final ratings should be based on common-practice harmony, counterpoint, cadence behavior, and singability in the score.

## Blinding

The files are anonymized. Some scores are model outputs and some are reference Bach chorale realizations. Please do not try to infer the source. The source key is held by the project owner and is not included in this expert-facing package.

## What to complete

1. Fill `forms/rater_background_form_project1.csv` once.
2. For single-score evaluation, open the files in `absolute_score_pdfs/` if PDFs are present; otherwise open `absolute_score_musicxml/`. Fill `forms/absolute_rating_form_project1.csv`.
3. For paired comparison, open the A/B files in `paired_comparison_pdfs/` if PDFs are present; otherwise open `paired_comparison_musicxml/`. Fill `forms/paired_comparison_form_project1.csv`.

If a notation program has no sound, use the matching files in `playback_audio/absolute_score_mp3/`, `playback_audio/absolute_score_wav/`, `playback_audio/paired_comparison_mp3/`, or `playback_audio/paired_comparison_wav/`.

## Rating scale for single-score evaluation

Use integer ratings from 1 to 5:

- 5 = excellent: idiomatic common-practice SATB writing, no salient harmonic or voice-leading problems.
- 4 = good: mostly correct, with only minor or local issues.
- 3 = acceptable: musically usable but with noticeable weaknesses.
- 2 = weak: frequent or musically disruptive problems.
- 1 = poor: severe harmonic, contrapuntal, cadence, or singability problems.

## Paired-comparison choices

For each pair, use one of: `A_strongly`, `A_slightly`, `tie`, `B_slightly`, `B_strongly`. Use `uncertain` only when the comparison cannot be judged.

## Dimensions

- Harmonic correctness: functional harmony, sonority choice, and local progression.
- Voice-leading correctness: spacing, crossing, parallels, tendency tones, and contrapuntal motion.
- Seventh-resolution correctness: whether chordal sevenths resolve properly when present.
- Cadence quality: whether phrase endings and final cadences are stylistically convincing.
- Singability: whether the four parts are plausible for SATB singers.
- Stylistic consistency: closeness to common-practice chorale writing.
- Usefulness for composition pedagogy: whether the realization would be useful as a teaching or correction example.

Please add short comments when a rating is low or when a specific issue is musically important.
"""


EXPERT_README_CN = f"""# Project 1 正式专家盲评材料包

英文题目：{PROJECT_TITLE}

中文题目：{PROJECT_TITLE_CN}

## 评价对象

这是一个谱面级 SATB 四部合唱和声化评价任务。请评价书面的四部谱面：
Soprano、Alto、Tenor、Bass。本项目不是音频生成或音频制作质量听辨实验。
MP3、WAV 和 MIDI 只作为辅助听辨材料，用来帮助确认音高、节奏和声部进行；
最终评分应基于乐谱中的传统和声、对位、声部进行、终止式质量和可唱性。

## 盲评说明

文件已经匿名化。其中一部分是模型输出，一部分是参考 Bach 众赞歌实现。请不要推测
文件来源。来源对照表由项目负责人保留，不包含在专家材料包中。

## 需要填写的文件

1. `forms/rater_background_form_project1.csv`：每位专家填写一次。
2. `forms/absolute_rating_form_project1.csv`：逐首乐谱评分。
3. `forms/paired_comparison_form_project1.csv`：A/B 配对比较评分。

优先打开 `absolute_score_pdfs/` 和 `paired_comparison_pdfs/` 里的 PDF 乐谱。
如需辅助试听，可打开 `playback_audio/` 中同名 MP3 或 WAV 文件。

## 单首乐谱评分尺度

请使用 1 到 5 的整数分：

- 5 = 优秀：符合 common-practice SATB 写作，基本没有明显和声或声部进行问题。
- 4 = 良好：整体正确，仅有轻微或局部问题。
- 3 = 可接受：音乐上可用，但存在明显弱点。
- 2 = 较弱：问题较频繁，影响音乐效果。
- 1 = 较差：存在严重和声、对位、终止式或可唱性问题。

## A/B 配对比较

每一组请选择：`A_strongly`、`A_slightly`、`tie`、`B_slightly`、`B_strongly`。
只有在确实无法判断时使用 `uncertain`。

## 评分维度

- harmonic correctness：功能和声、纵向和弦与局部进行是否合理。
- voice-leading correctness：间距、交叉、平行五八度、倾向音和对位进行是否合理。
- seventh-resolution correctness：出现七音时是否按风格合理解决。
- cadence quality：乐句末和终止式是否自然、有说服力。
- singability：四个声部是否适合 SATB 演唱。
- stylistic consistency：是否接近 common-practice chorale 写作风格。
- usefulness for composition pedagogy：是否适合作为作曲/和声教学中的示例或纠错材料。

若给出低分，或发现特别重要的问题，请在 comments 栏简要说明。
"""


PLAYBACK_README_EN = """# Playback Support for Expert Evaluation

This folder adds optional MIDI, WAV, and MP3 playback files to the formal blind
score package. The evaluation remains score-based. Please judge the written SATB
notation, not the realism, balance, or timbre of the playback rendering.

## Recommended use

1. Open the PDF score first.
2. Use the matching MP3/WAV/MIDI file only as an auxiliary playback reference.
3. Enter ratings in the forms folder.

## File mapping

- `playback_midi/absolute_score_midi/*.mid`, `playback_audio/absolute_score_wav/*.wav`,
  and `playback_audio/absolute_score_mp3/*.mp3` correspond to
  `absolute_score_pdfs/*.pdf` and `absolute_score_musicxml/*.musicxml`.
- `playback_midi/paired_comparison_midi/*.mid`, `playback_audio/paired_comparison_wav/*.wav`,
  and `playback_audio/paired_comparison_mp3/*.mp3` correspond to the paired A/B
  comparison files.

The same score ID always maps across formats. For example, `P1S01.pdf`,
`P1S01.musicxml`, `P1S01.mid`, `P1S01.wav`, and `P1S01.mp3` belong to the same
score. The file `SCORE_AUDIO_CORRESPONDENCE.csv` lists the full mapping,
four-part MusicXML check, audio validation, and SHA256 hashes.

The playback files are rendered from the score using the best available local
score-playback backend: MuseScore export or FluidSynth with a SoundFont when
available, with an internal deterministic renderer only as a portability
fallback. The purpose is to make pitches, rhythm, and voice leading audible on
ordinary computers, not to evaluate choral sound production.

If a notation program plays MusicXML with no sound, open the matching `.mp3` or
`.wav` file first. MIDI is included as an additional compact interchange format.
"""


PLAYBACK_README_CN = """# 专家评审播放辅助说明

这个版本在正式盲评乐谱包之外，额外加入了 MIDI、WAV 和 MP3 播放辅助文件。
评分仍然是“看 SATB 乐谱”的专业评分，不是音频制作质量评分。
请不要评价试听文件的音色真实感、混音、响度或人声效果。

## 推荐使用方式

1. 先打开 PDF 乐谱。
2. 如需辅助听辨，再打开同名 MP3 或 WAV 文件试听。
3. 最后填写 forms 文件夹里的评分表。

## 文件对应关系

- `playback_midi/absolute_score_midi/*.mid`、`playback_audio/absolute_score_wav/*.wav`
  和 `playback_audio/absolute_score_mp3/*.mp3` 对应
  `absolute_score_pdfs/*.pdf` 和 `absolute_score_musicxml/*.musicxml`。
- `playback_midi/paired_comparison_midi/*.mid`、`playback_audio/paired_comparison_wav/*.wav`
  和 `playback_audio/paired_comparison_mp3/*.mp3` 对应 A/B 配对比较材料。

同一个乐谱编号在所有格式中一一对应。例如 `P1S01.pdf`、`P1S01.musicxml`、
`P1S01.mid`、`P1S01.wav` 和 `P1S01.mp3` 属于同一首乐谱。
完整对应关系、四声部 MusicXML 检查、音频非静音验证和 SHA256 哈希见
`SCORE_AUDIO_CORRESPONDENCE.csv`。

试听文件由乐谱渲染得到。程序会优先使用本机可用的 MuseScore 导出或
FluidSynth + SoundFont 声库；只有外部后端不可用时，才退回到项目内置的确定性
渲染器。这样做是为了在普通电脑上更稳定地播放音高、节奏和声部进行，而不是让
专家评价合唱音色或音频制作效果。

如果 MusicXML 在记谱软件里没有声音，请直接打开同名 `.mp3` 或 `.wav` 文件。
MIDI 文件也保留为额外的轻量交换格式。
"""


def prepare_playback_package(
    source_package: str | Path,
    output_dir: str | Path | None = None,
    overwrite: bool = False,
    make_zip: bool = True,
    audio_backend: str = "auto",
    soundfont_path: str | None = None,
    fluidsynth_path: str | None = None,
    musescore_path: str | None = None,
    regenerate_pdfs: bool = False,
) -> dict[str, str]:
    source = Path(source_package)
    if not source.exists():
        raise FileNotFoundError(f"Source expert package not found: {source}")
    if not source.is_dir():
        raise NotADirectoryError(f"Source expert package is not a directory: {source}")

    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = source.with_name(f"{source.name}_WITH_SCORE_PLAYBACK_AUDIO_{stamp}")
    else:
        output = Path(output_dir)

    if output.exists():
        if not overwrite:
            raise FileExistsError(f"Output already exists: {output}")
        shutil.rmtree(output)
    shutil.copytree(source, output)
    write_expert_text_files(output)

    render_settings = PlaybackRenderSettings(
        backend=audio_backend,
        soundfont_path=soundfont_path,
        fluidsynth_path=fluidsynth_path,
        musescore_path=musescore_path,
    )

    pdf_manifest_rows: list[dict[str, str]] = []
    if regenerate_pdfs:
        regenerate_pdf_folder(output / "absolute_score_musicxml", output / "absolute_score_pdfs", pdf_manifest_rows, render_settings)
        regenerate_pdf_folder(output / "paired_comparison_musicxml", output / "paired_comparison_pdfs", pdf_manifest_rows, render_settings)
        failed_pdfs = [row for row in pdf_manifest_rows if row["status"] != "ok"]
        if failed_pdfs:
            raise RuntimeError(f"PDF regeneration failed: {failed_pdfs[:3]}")

    playback_root = output / "playback_midi"
    absolute_out = playback_root / "absolute_score_midi"
    paired_out = playback_root / "paired_comparison_midi"
    absolute_out.mkdir(parents=True, exist_ok=True)
    paired_out.mkdir(parents=True, exist_ok=True)

    audio_root = output / "playback_audio"
    audio_dirs = {
        "absolute_wav": audio_root / "absolute_score_wav",
        "absolute_mp3": audio_root / "absolute_score_mp3",
        "paired_wav": audio_root / "paired_comparison_wav",
        "paired_mp3": audio_root / "paired_comparison_mp3",
    }
    for audio_dir in audio_dirs.values():
        audio_dir.mkdir(parents=True, exist_ok=True)

    manifest_rows: list[dict[str, str]] = []
    convert_folder(output / "absolute_score_musicxml", absolute_out, manifest_rows, render_settings)
    convert_folder(output / "paired_comparison_musicxml", paired_out, manifest_rows, render_settings)
    audio_manifest_rows: list[dict[str, str]] = []
    render_audio_folder(
        output / "absolute_score_musicxml",
        audio_dirs["absolute_wav"],
        audio_dirs["absolute_mp3"],
        audio_manifest_rows,
        render_settings,
    )
    render_audio_folder(
        output / "paired_comparison_musicxml",
        audio_dirs["paired_wav"],
        audio_dirs["paired_mp3"],
        audio_manifest_rows,
        render_settings,
    )

    write_playback_text_files(output)
    write_manifest(playback_root / "playback_midi_manifest.csv", manifest_rows)
    if pdf_manifest_rows:
        write_pdf_manifest(output / "pdf_regeneration_manifest.csv", pdf_manifest_rows)
    write_audio_manifest(audio_root / "playback_audio_manifest.csv", audio_manifest_rows)
    audit = audit_package(output)
    audit_outputs = write_audit_outputs(output, audit)
    if not audit["summary"]["all_entries_ok"]:
        raise RuntimeError(f"Score-audio correspondence audit failed: {audit['errors']}")

    zip_path = ""
    if make_zip:
        zip_base = output.with_suffix("")
        archive = shutil.make_archive(str(zip_base), "zip", root_dir=output)
        zip_path = archive

    ok_count = sum(1 for row in manifest_rows if row["status"] == "ok")
    failed_count = len(manifest_rows) - ok_count
    wav_count = sum(1 for row in audio_manifest_rows if row["wav_status"] == "ok")
    mp3_count = sum(1 for row in audio_manifest_rows if row["mp3_status"] == "ok")
    audio_backends = ",".join(sorted({row["backend"] for row in audio_manifest_rows if row.get("backend")}))
    return {
        "output_dir": str(output),
        "zip_path": zip_path,
        "midi_files": str(ok_count),
        "wav_files": str(wav_count),
        "mp3_files": str(mp3_count),
        "audio_backends": audio_backends,
        "failed": str(failed_count),
        "manifest": str(playback_root / "playback_midi_manifest.csv"),
        "audio_manifest": str(audio_root / "playback_audio_manifest.csv"),
        "pdf_manifest": str(output / "pdf_regeneration_manifest.csv") if pdf_manifest_rows else "",
        "correspondence_csv": audit_outputs["csv"],
        "correspondence_summary": audit_outputs["json"],
    }


def write_expert_text_files(output: Path) -> None:
    (output / "EMAIL_TEMPLATE_TO_EXPERTS.md").write_text(EMAIL_TEMPLATE_EN, encoding="utf-8")
    (output / "README_FOR_EXPERTS.md").write_text(EXPERT_README_EN, encoding="utf-8")
    (output / "README_CN.md").write_text(EXPERT_README_CN, encoding="utf-8-sig")


def write_playback_text_files(output: Path) -> None:
    (output / "README_PLAYBACK_FOR_EXPERTS.md").write_text(PLAYBACK_README_EN, encoding="utf-8")
    (output / "README_PLAYBACK_CN.md").write_text(PLAYBACK_README_CN, encoding="utf-8-sig")
    (output / "README_PLAYBACK_CN.txt").write_text(PLAYBACK_README_CN, encoding="utf-8-sig")


def regenerate_pdf_folder(
    source_dir: Path,
    output_dir: Path,
    manifest_rows: list[dict[str, str]],
    settings: PlaybackRenderSettings,
) -> None:
    if not source_dir.exists():
        return
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_pdf in output_dir.glob("*.pdf"):
        old_pdf.unlink()
    for musicxml_path in sorted(source_dir.glob("*.musicxml")):
        pdf_path = output_dir / f"{musicxml_path.stem}.pdf"
        message = export_pdf_with_musescore(musicxml_path, pdf_path, settings)
        manifest_rows.append(
            {
                "source_musicxml": str(musicxml_path),
                "output_pdf": str(pdf_path),
                "backend": "musescore",
                "status": "failed" if message else "ok",
                "message": message,
            }
        )


def convert_folder(
    source_dir: Path,
    output_dir: Path,
    manifest_rows: list[dict[str, str]],
    settings: PlaybackRenderSettings,
) -> None:
    if not source_dir.exists():
        return
    for musicxml_path in sorted(source_dir.glob("*.musicxml")):
        midi_path = output_dir / f"{musicxml_path.stem}.mid"
        backend = "music21"
        row = {
            "source_musicxml": str(musicxml_path),
            "output_midi": str(midi_path),
            "backend": backend,
            "status": "ok",
            "message": "",
        }
        try:
            prefer_musescore = settings.backend in {"auto", "musescore", "musescore_midi_fluidsynth"}
            if prefer_musescore:
                message = export_midi_with_musescore(musicxml_path, midi_path, settings)
                if not message:
                    row["backend"] = "musescore"
                    manifest_rows.append(row)
                    continue
                if settings.backend in {"musescore", "musescore_midi_fluidsynth"}:
                    raise RuntimeError(message)
                row["message"] = f"MuseScore MIDI export unavailable; used music21 fallback: {message}"
            score = converter.parse(str(musicxml_path))
            force_piano_instruments(score)
            score.write("midi", fp=str(midi_path))
        except Exception as exc:  # pragma: no cover - depends on external score parsing.
            row["status"] = "failed"
            row["message"] = f"{type(exc).__name__}: {exc}"
        manifest_rows.append(row)


def force_piano_instruments(score: stream.Score) -> None:
    for part in score.parts:
        part.insert(0, instrument.Piano())


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source_musicxml", "output_midi", "backend", "status", "message"])
        writer.writeheader()
        writer.writerows(rows)


def write_pdf_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source_musicxml", "output_pdf", "backend", "status", "message"])
        writer.writeheader()
        writer.writerows(rows)


def render_audio_folder(
    source_dir: Path,
    wav_dir: Path,
    mp3_dir: Path,
    manifest_rows: list[dict[str, str]],
    settings: PlaybackRenderSettings,
) -> None:
    if not source_dir.exists():
        return
    for musicxml_path in sorted(source_dir.glob("*.musicxml")):
        wav_path = wav_dir / f"{musicxml_path.stem}.wav"
        mp3_path = mp3_dir / f"{musicxml_path.stem}.mp3"
        result = render_musicxml_to_audio(musicxml_path, wav_path, mp3_path, settings)
        row = {
            "source_musicxml": str(musicxml_path),
            "output_wav": str(wav_path),
            "output_mp3": str(mp3_path),
            "wav_status": result.wav_status,
            "mp3_status": result.mp3_status,
            "backend": result.backend,
            "duration_sec": f"{result.duration_sec:.3f}",
            "rms": f"{result.rms:.3f}",
            "peak": str(result.peak),
            "message": result.message,
        }
        manifest_rows.append(row)


def write_audio_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "source_musicxml",
                "output_wav",
                "output_mp3",
                "wav_status",
                "mp3_status",
                "backend",
                "duration_sec",
                "rms",
                "peak",
                "message",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Add MIDI/WAV/MP3 playback support to a formal expert-evaluation package.")
    parser.add_argument("--source-package", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--no-zip", action="store_true")
    parser.add_argument(
        "--audio-backend",
        default="auto",
        choices=["auto", "musescore", "musescore_midi_fluidsynth", "fluidsynth", "additive"],
    )
    parser.add_argument("--soundfont-path")
    parser.add_argument("--fluidsynth-path")
    parser.add_argument("--musescore-path")
    parser.add_argument("--regenerate-pdfs", action="store_true")
    args = parser.parse_args()
    print(
        prepare_playback_package(
            source_package=args.source_package,
            output_dir=args.output_dir,
            overwrite=args.overwrite,
            make_zip=not args.no_zip,
            audio_backend=args.audio_backend,
            soundfont_path=args.soundfont_path,
            fluidsynth_path=args.fluidsynth_path,
            musescore_path=args.musescore_path,
            regenerate_pdfs=args.regenerate_pdfs,
        )
    )


if __name__ == "__main__":
    main()
