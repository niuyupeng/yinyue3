from __future__ import annotations

import argparse
import copy
import csv
import json
import shutil
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from music21 import converter, instrument, note, stream

from chorale.playback_render import (
    PlaybackRenderSettings,
    convert_wav_to_mp3,
    musicxml_to_midi,
    normalize_wav_peak,
    pad_wav_to_duration,
    render_midi_with_fluidsynth,
    validate_wav_file,
)


VOICE_NAMES = ["soprano", "alto", "tenor", "bass"]
VOICE_INSTRUMENTS = [instrument.Soprano, instrument.Alto, instrument.Tenor, instrument.Bass]
GROUPS = {
    "absolute": "absolute_score_musicxml",
    "paired": "paired_comparison_musicxml",
}


@dataclass(frozen=True)
class RenderVariant:
    name: str
    description: str
    solo_voice_index: int | None = None
    instrument_mode: str = "choir"


DEFAULT_VARIANTS = [
    RenderVariant("full_choir", "SATB full mix with vocal part instruments.", None, "choir"),
    RenderVariant("piano_reference", "SATB full mix using piano for pitch clarity.", None, "piano"),
    RenderVariant("stem_soprano", "Soprano-only stem for score-audio checking.", 0, "choir"),
    RenderVariant("stem_alto", "Alto-only stem for score-audio checking.", 1, "choir"),
    RenderVariant("stem_tenor", "Tenor-only stem for score-audio checking.", 2, "choir"),
    RenderVariant("stem_bass", "Bass-only stem for score-audio checking.", 3, "choir"),
]


def prepare_pro_playback_package(
    package_dir: str | Path,
    output_dir: str | Path | None = None,
    audio_backend: str = "musescore_midi_fluidsynth",
    make_zip: bool = True,
    limit: int | None = None,
) -> dict[str, object]:
    package = Path(package_dir)
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")

    if output_dir is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = package.parent / f"PRO_PLAYBACK_{stamp}"
    else:
        output = Path(output_dir)
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(package, output)

    settings = PlaybackRenderSettings(backend=audio_backend)
    pro_root = output / "audio_pro"
    midi_root = output / "midi_pro"
    temp_root = output / "render_xml"
    rows: list[dict[str, str]] = []

    musicxml_items = list(iter_musicxml_items(output))
    if limit is not None and limit > 0:
        musicxml_items = musicxml_items[:limit]

    with tempfile.TemporaryDirectory(prefix="chorale_pro_playback_") as tmp:
        tmp_root = Path(tmp)
        for group, musicxml_path in musicxml_items:
            render_score_variants(
                group=group,
                musicxml_path=musicxml_path,
                output=output,
                pro_root=pro_root,
                midi_root=midi_root,
                temp_root=temp_root,
                tmp_root=tmp_root,
                settings=settings,
                rows=rows,
            )

    manifest = pro_root / "pro_playback_manifest.csv"
    write_manifest(manifest, rows)
    summary = summarize(rows)
    summary_path = pro_root / "pro_playback_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    readme_path = pro_root / "README_PRO_PLAYBACK.md"
    readme_path.write_text(make_readme(summary), encoding="utf-8")

    zip_path = ""
    if make_zip:
        archive_base = output.with_name(output.name + "_FINAL")
        zip_path = shutil.make_archive(str(archive_base), "zip", root_dir=output)

    return {
        "output_dir": str(output),
        "zip_path": zip_path,
        "manifest": str(manifest),
        "summary": summary,
        "summary_path": str(summary_path),
    }


def iter_musicxml_items(package: Path) -> list[tuple[str, Path]]:
    items: list[tuple[str, Path]] = []
    for group, folder in GROUPS.items():
        musicxml_dir = package / folder
        if not musicxml_dir.is_dir():
            continue
        for path in sorted(musicxml_dir.glob("*.musicxml")):
            items.append((group, path))
    return items


def render_score_variants(
    group: str,
    musicxml_path: Path,
    output: Path,
    pro_root: Path,
    midi_root: Path,
    temp_root: Path,
    tmp_root: Path,
    settings: PlaybackRenderSettings,
    rows: list[dict[str, str]],
) -> None:
    score_rows: list[dict[str, str]] = []
    for variant in DEFAULT_VARIANTS:
        score_id = musicxml_path.stem
        variant_dir = pro_root / group / score_id
        midi_dir = midi_root / group / score_id
        source_dir = temp_root / group / score_id
        variant_dir.mkdir(parents=True, exist_ok=True)
        midi_dir.mkdir(parents=True, exist_ok=True)
        source_dir.mkdir(parents=True, exist_ok=True)

        render_source = source_dir / f"{score_id}_{variant.name}.musicxml"
        tmp_source = tmp_root / f"{group}_{score_id}_{variant.name}.musicxml"
        midi_path = midi_dir / f"{score_id}_{variant.name}.mid"
        wav_path = variant_dir / f"{score_id}_{variant.name}.wav"
        mp3_path = variant_dir / f"{score_id}_{variant.name}.mp3"
        row = base_row(group, score_id, variant, musicxml_path, render_source, midi_path, wav_path, mp3_path, output)

        try:
            write_variant_musicxml_file(musicxml_path, tmp_source, variant)
            shutil.copy2(tmp_source, render_source)
            musicxml_to_midi(tmp_source, midi_path, bpm=settings.bpm)
            wav_message = render_midi_with_fluidsynth(midi_path, wav_path, settings)
            if wav_message:
                raise RuntimeError(f"FluidSynth render failed: {wav_message}")
            normalized = normalize_wav_peak(wav_path)
            if not normalized.ok:
                raise RuntimeError(f"WAV normalization failed: {normalized.message}")
            mp3_message = convert_wav_to_mp3(wav_path, mp3_path, settings.mp3_bitrate)
            if mp3_message:
                raise RuntimeError(f"MP3 conversion failed: {mp3_message}")
            validation = validate_wav_file(wav_path, settings.min_rms)
            if not validation.ok:
                raise RuntimeError(f"WAV validation failed: {validation.message}")
            row.update(
                {
                    "status": "ok",
                    "duration_sec": f"{validation.duration_sec:.3f}",
                    "rms": f"{validation.rms:.3f}",
                    "peak": str(validation.peak),
                }
            )
        except Exception as exc:
            row["status"] = "failed"
            row["message"] = f"{type(exc).__name__}: {exc}"
        score_rows.append(row)
    align_variant_audio_durations(score_rows, output, settings)
    rows.extend(score_rows)


def align_variant_audio_durations(rows: list[dict[str, str]], output: Path, settings: PlaybackRenderSettings) -> None:
    ok_rows = [row for row in rows if row["status"] == "ok" and row.get("duration_sec")]
    if len(ok_rows) < 2:
        return
    target_duration = max(float(row["duration_sec"]) for row in ok_rows)
    for row in ok_rows:
        current = float(row["duration_sec"])
        if target_duration - current <= 0.05:
            continue
        wav_path = output / row["wav"]
        mp3_path = output / row["mp3"]
        try:
            padded = pad_wav_to_duration(wav_path, target_duration)
            if not padded.ok:
                raise RuntimeError(padded.message)
            mp3_message = convert_wav_to_mp3(wav_path, mp3_path, settings.mp3_bitrate)
            if mp3_message:
                raise RuntimeError(mp3_message)
            row.update(
                {
                    "duration_sec": f"{padded.duration_sec:.3f}",
                    "rms": f"{padded.rms:.3f}",
                    "peak": str(padded.peak),
                    "message": append_message(row.get("message", ""), f"padded_to_{target_duration:.3f}s"),
                }
            )
        except Exception as exc:
            row["status"] = "failed"
            row["message"] = append_message(row.get("message", ""), f"duration alignment failed: {type(exc).__name__}: {exc}")


def append_message(existing: str, addition: str) -> str:
    if not existing:
        return addition
    return f"{existing}; {addition}"


def write_variant_musicxml_file(source_musicxml: Path, output_musicxml: Path, variant: RenderVariant) -> None:
    tree = ET.parse(source_musicxml)
    root = tree.getroot()
    part_ids = update_part_list(root, variant)
    if variant.solo_voice_index is not None and variant.solo_voice_index < len(part_ids):
        target_id = part_ids[variant.solo_voice_index]
        for part in children_named(root, "part"):
            if part.attrib.get("id") != target_id:
                mute_part_in_place(part)
    output_musicxml.parent.mkdir(parents=True, exist_ok=True)
    tree.write(output_musicxml, encoding="utf-8", xml_declaration=True)


def update_part_list(root: ET.Element, variant: RenderVariant) -> list[str]:
    score_parts = children_named(first_child(root, "part-list") or root, "score-part")
    part_ids: list[str] = []
    for idx, score_part in enumerate(score_parts):
        part_id = score_part.attrib.get("id", f"P{idx + 1}")
        part_ids.append(part_id)
        part_name = first_child(score_part, "part-name")
        if part_name is None:
            part_name = ET.Element("part-name")
            score_part.insert(0, part_name)
        part_name.text = infer_part_name(idx, variant)
        instrument_id = ensure_score_instrument(score_part, part_id, idx, variant)
        ensure_midi_instrument(score_part, instrument_id, idx, variant)
    if not part_ids:
        part_ids = [part.attrib.get("id", "") for part in children_named(root, "part")]
    return part_ids


def ensure_score_instrument(score_part: ET.Element, part_id: str, idx: int, variant: RenderVariant) -> str:
    score_instrument = first_child(score_part, "score-instrument")
    if score_instrument is None:
        score_instrument = ET.Element("score-instrument", {"id": f"{part_id}-I1"})
        score_part.append(score_instrument)
    instrument_id = score_instrument.attrib.get("id", f"{part_id}-I1")
    score_instrument.attrib["id"] = instrument_id
    instrument_name = first_child(score_instrument, "instrument-name")
    if instrument_name is None:
        instrument_name = ET.Element("instrument-name")
        score_instrument.append(instrument_name)
    instrument_name.text = "Acoustic Grand Piano" if variant.instrument_mode == "piano" else infer_part_name(idx, variant)
    return instrument_id


def ensure_midi_instrument(score_part: ET.Element, instrument_id: str, idx: int, variant: RenderVariant) -> None:
    midi_instrument = first_child(score_part, "midi-instrument")
    if midi_instrument is None:
        midi_instrument = ET.Element("midi-instrument", {"id": instrument_id})
        score_part.append(midi_instrument)
    midi_instrument.attrib["id"] = instrument_id
    channel = first_child(midi_instrument, "midi-channel")
    if channel is None:
        channel = ET.Element("midi-channel")
        midi_instrument.append(channel)
    channel.text = str(min(idx + 1, 16))
    program = first_child(midi_instrument, "midi-program")
    if program is None:
        program = ET.Element("midi-program")
        midi_instrument.append(program)
    program.text = "1" if variant.instrument_mode == "piano" else "53"


def mute_part_in_place(part: ET.Element) -> None:
    for measure in children_named(part, "measure"):
        for note_el in list(children_named(measure, "note")):
            if first_child(note_el, "chord") is not None:
                measure.remove(note_el)
                continue
            convert_note_to_rest(note_el)


def convert_note_to_rest(note_el: ET.Element) -> None:
    for removable in ["pitch", "accidental", "tie", "notations", "lyric"]:
        for child in list(children_named(note_el, removable)):
            note_el.remove(child)
    if first_child(note_el, "rest") is not None:
        return
    rest = ET.Element("rest")
    insert_at = 0
    for idx, child in enumerate(list(note_el)):
        if local_name(child.tag) in {"duration", "voice", "type"}:
            insert_at = idx
            break
    note_el.insert(insert_at, rest)


def children_named(parent: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(parent) if local_name(child.tag) == name]


def first_child(parent: ET.Element, name: str) -> ET.Element | None:
    for child in list(parent):
        if local_name(child.tag) == name:
            return child
    return None


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


def make_render_variant_score(score: stream.Score, variant: RenderVariant) -> stream.Score:
    target_duration = float(score.highestTime)
    rendered = copy.deepcopy(score)
    parts = list(rendered.parts)
    if variant.solo_voice_index is not None:
        for idx, part in enumerate(parts):
            if idx != variant.solo_voice_index:
                silence_part(part)
        parts = list(rendered.parts)
    for idx, part in enumerate(parts):
        clear_instruments(part)
        part.partName = infer_part_name(idx, variant)
        part.partAbbreviation = part.partName[:3]
        part.insert(0, choose_instrument(idx, variant))
        pad_part_to_duration(part, target_duration)
        rendered.setElementOffset(part, 0.0)
    return rendered


def clear_instruments(part: stream.Part) -> None:
    for item in list(part.recurse().getElementsByClass(instrument.Instrument)):
        site = item.activeSite
        if site is not None:
            try:
                site.remove(item)
            except Exception:
                pass


def silence_part(part: stream.Part) -> None:
    for item in list(part.recurse().notes):
        rest = note.Rest(quarterLength=item.quarterLength)
        site = item.activeSite
        if site is not None:
            try:
                site.replace(item, rest)
            except Exception:
                pass


def pad_part_to_duration(part: stream.Part, target_duration: float) -> None:
    part_end = float(part.highestTime)
    if target_duration <= part_end:
        return
    padding = note.Rest(quarterLength=target_duration - part_end)
    part.insert(part_end, padding)


def choose_instrument(idx: int, variant: RenderVariant) -> instrument.Instrument:
    if variant.instrument_mode == "piano":
        return instrument.Piano()
    cls = VOICE_INSTRUMENTS[idx] if idx < len(VOICE_INSTRUMENTS) else instrument.Vocalist
    return cls()


def infer_part_name(idx: int, variant: RenderVariant) -> str:
    if idx < len(VOICE_NAMES):
        name = VOICE_NAMES[idx].title()
        if variant.solo_voice_index is not None and idx != variant.solo_voice_index:
            return f"{name} Muted"
        return name
    return f"Part {idx + 1}"


def base_row(
    group: str,
    score_id: str,
    variant: RenderVariant,
    source_musicxml: Path,
    render_musicxml: Path,
    midi_path: Path,
    wav_path: Path,
    mp3_path: Path,
    output: Path,
) -> dict[str, str]:
    voice = "" if variant.solo_voice_index is None else VOICE_NAMES[variant.solo_voice_index]
    return {
        "group": group,
        "score_id": score_id,
        "variant": variant.name,
        "voice": voice,
        "description": variant.description,
        "source_musicxml": rel(source_musicxml, output),
        "render_musicxml": rel(render_musicxml, output),
        "midi": rel(midi_path, output),
        "wav": rel(wav_path, output),
        "mp3": rel(mp3_path, output),
        "midi_backend": "score_aligned_internal",
        "audio_backend": "fluidsynth",
        "status": "pending",
        "duration_sec": "",
        "rms": "",
        "peak": "",
        "message": "",
    }


def rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "group",
        "score_id",
        "variant",
        "voice",
        "description",
        "source_musicxml",
        "render_musicxml",
        "midi",
        "wav",
        "mp3",
        "midi_backend",
        "audio_backend",
        "status",
        "duration_sec",
        "rms",
        "peak",
        "message",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize(rows: list[dict[str, str]]) -> dict[str, object]:
    by_variant: dict[str, dict[str, int]] = {}
    by_group: dict[str, int] = {}
    for row in rows:
        variant = row["variant"]
        by_variant.setdefault(variant, {"ok": 0, "failed": 0})
        by_variant[variant][row["status"]] = by_variant[variant].get(row["status"], 0) + 1
        by_group[row["group"]] = by_group.get(row["group"], 0) + 1
    return {
        "entry_count": len(rows),
        "ok_count": sum(1 for row in rows if row["status"] == "ok"),
        "failed_count": sum(1 for row in rows if row["status"] != "ok"),
        "all_ok": all(row["status"] == "ok" for row in rows),
        "by_group": by_group,
        "by_variant": by_variant,
        "variants": [variant.name for variant in DEFAULT_VARIANTS],
    }


def make_readme(summary: dict[str, object]) -> str:
    return (
        "# Pro Playback Package\n\n"
        "This folder contains score-derived playback assets for SATB MusicXML files.\n"
        "It is intended for product-grade checking and expert review support, not as a neural audio generation model.\n\n"
        "## Variants\n\n"
        "- `full_choir`: full SATB mix using vocal part instruments.\n"
        "- `piano_reference`: full SATB mix with piano instruments for pitch clarity.\n"
        "- `stem_soprano`, `stem_alto`, `stem_tenor`, `stem_bass`: isolated voice stems.\n\n"
        "Every variant is rendered from a MusicXML file, exported to MIDI through MuseScore, "
        "and rendered to WAV/MP3 through FluidSynth and the configured SoundFont.\n\n"
        "## QC Summary\n\n"
        f"- Entry count: {summary.get('entry_count')}\n"
        f"- OK count: {summary.get('ok_count')}\n"
        f"- Failed count: {summary.get('failed_count')}\n"
        f"- All OK: {summary.get('all_ok')}\n\n"
        "See `pro_playback_manifest.csv` for per-score, per-variant details.\n"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build product-grade score playback assets from an expert package.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--audio-backend", default="musescore_midi_fluidsynth")
    parser.add_argument("--limit", type=int, default=0, help="Optional number of MusicXML scores to render for debug.")
    parser.add_argument("--no-zip", action="store_true")
    args = parser.parse_args()
    result = prepare_pro_playback_package(
        package_dir=args.package_dir,
        output_dir=args.output_dir,
        audio_backend=args.audio_backend,
        limit=args.limit if args.limit > 0 else None,
        make_zip=not args.no_zip,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
