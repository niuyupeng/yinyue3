from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import torch
from music21 import converter, stream

from chorale.data.score_tokenizer import (
    ScoreTokenizer,
    VOICE_NAMES,
    VOICE_RANGES,
    element_offset,
    iter_notes_and_rests,
    make_time_features,
    quantize_offset,
)
from chorale.decoding import decode_predictions
from chorale.export_musicxml import export_tokens_to_musicxml
from chorale.harmonization_quality import evaluate_harmonization_quality
from chorale.score_preflight import analyze_score_input
from chorale.symbolic_repair import apply_final_authentic_cadence, optimize_symbolic_postprocess
from chorale.theory.explain_report import build_explanation_report, write_explanation_report
from chorale.theory.roman_numeral import annotate_tokens_harmony, approximate_key, key_label_and_tonic_pc
from chorale.theory.rule_guided_decoding import apply_constraint_reranking, apply_rule_guided_decoding
from chorale.train import batch_to_device, build_model
from chorale.utils import ensure_dir, get_device, load_config, safe_torch_load, write_json


VOICE_TO_INDEX = {name: idx for idx, name in enumerate(VOICE_NAMES)}


@dataclass(frozen=True)
class ConditionScore:
    source_tokens: np.ndarray
    input_tokens: np.ndarray
    known_mask: np.ndarray
    target_mask: np.ndarray
    valid_mask: np.ndarray
    beat_positions: np.ndarray
    measure_indices: np.ndarray
    length: int
    known_voices: list[str]
    key_label: str
    key_tonic_pc: int


def harmonize_musicxml(
    input_musicxml: str | Path,
    output_dir: str | Path,
    *,
    checkpoint: str | Path | None = None,
    config: str | Path | None = None,
    task: str = "soprano_to_satb",
    input_role: str = "soprano",
    known_voices: str | list[str] | None = None,
    prefix: str | None = None,
    apply_rules: bool = True,
    render_audio: bool = False,
    audio_backend: str = "additive",
    optimize_symbols: bool = True,
    repair_passes: int = 12,
    repair_final_cadence: bool = True,
    max_violations_per_100: float = 12.0,
    max_total_violations: int = 24,
    max_total_penalty: float = 20.0,
    max_seventh_resolution_violations: int = 12,
    require_audio_for_quality: bool = False,
) -> dict[str, Any]:
    """Harmonize a user-provided MusicXML score into SATB notation.

    This is the practical product-facing entry point. It accepts a soprano
    melody, bass line, or partially known SATB MusicXML file and writes a
    complete four-part score plus a rule explanation report. If no neural
    checkpoint is provided, it falls back to an explicit deterministic rule
    harmonizer and records that choice in the output summary.
    """
    output_dir = ensure_dir(output_dir)
    input_musicxml = Path(input_musicxml)
    loaded_checkpoint = load_checkpoint_payload(checkpoint)
    cfg = load_harmonize_config(config, loaded_checkpoint)
    tokenizer = tokenizer_from_sources(cfg, loaded_checkpoint)
    input_preflight = analyze_score_input(
        input_musicxml,
        task=task,
        input_role=input_role,
        known_voices=known_voices,
        grid_quarter_length=tokenizer.grid_quarter_length,
        max_seq_len=tokenizer.max_seq_len,
    )
    if input_preflight.get("status") == "failed":
        details = "; ".join(input_preflight.get("critical", []) or input_preflight.get("issues", []))
        raise ValueError(f"Input score preflight failed: {details}")

    parsed = parse_as_score(input_musicxml)
    condition = build_condition_score(
        parsed,
        tokenizer,
        task=task,
        input_role=input_role,
        known_voices=known_voices,
    )
    model = None
    engine = "rule_baseline_practical"
    logits = None
    if loaded_checkpoint is not None:
        device = get_device()
        model = build_model(loaded_checkpoint.get("config", cfg), vocab_size=int(loaded_checkpoint["vocab_size"])).to(device)
        model.load_state_dict(loaded_checkpoint["model_state"])
        model.eval()
        engine = f"neural_checkpoint:{Path(str(checkpoint)).name}"

    harmony_for_condition = annotate_tokens_harmony(
        condition.input_tokens,
        tokenizer,
        length=condition.length,
        key_label=condition.key_label,
        key_tonic_pc=condition.key_tonic_pc,
        measure_indices=condition.measure_indices,
        beat_positions=condition.beat_positions,
    )
    if model is None:
        generated = practical_rule_harmonize(
            condition.input_tokens,
            condition.known_mask,
            tokenizer,
            length=condition.length,
            key_tonic_pc=condition.key_tonic_pc,
        )
    else:
        batch = condition_to_batch(condition, harmony_for_condition)
        batch_dev = batch_to_device(batch, next(model.parameters()).device)
        decoding_cfg = cfg.get("decoding", {}) if isinstance(cfg, dict) else {}
        refinement_steps = (
            int(decoding_cfg.get("refinement_steps", 1))
            if bool(decoding_cfg.get("iterative_refinement", False))
            else 1
        )
        pred, logits = decode_predictions(
            model,
            batch_dev,
            mask_token=tokenizer.MASK,
            refinement_steps=refinement_steps,
            refinement_strategy=str(decoding_cfg.get("refinement_strategy", "confidence")),
            remask_fraction=float(decoding_cfg.get("remask_fraction", 0.35)),
        )
        generated = condition.source_tokens.copy()
        pred_np = pred[0].detach().cpu().numpy()
        generated[condition.target_mask] = pred_np[condition.target_mask]

    generated[condition.known_mask] = condition.source_tokens[condition.known_mask]
    constraints_cfg = cfg.get("constraints", {}) if isinstance(cfg, dict) else {}
    if model is not None and bool(constraints_cfg.get("use_constraint_reranking", False)) and logits is not None:
        generated = apply_constraint_reranking(
            generated,
            logits[0],
            condition.target_mask,
            tokenizer,
            length=condition.length,
            harmonic_labels=harmony_for_condition,
            top_k=int(constraints_cfg.get("rerank_top_k", 4)),
            rule_weight=float(constraints_cfg.get("rerank_rule_weight", 1.0)),
            harmony_weight=float(constraints_cfg.get("rerank_harmony_weight", 0.25)),
            temporal_weight=float(constraints_cfg.get("rerank_temporal_weight", 1.0)),
            seventh_weight=float(constraints_cfg.get("rerank_seventh_weight", 1.0)),
        )
        generated[condition.known_mask] = condition.source_tokens[condition.known_mask]
    if apply_rules:
        generated = apply_rule_guided_decoding(generated, tokenizer, length=condition.length)
        generated[condition.known_mask] = condition.source_tokens[condition.known_mask]

    generated = tokenizer.sanitize_for_export(generated, length=condition.length)
    stem = prefix or input_musicxml.stem
    generated_harmony = annotate_tokens_harmony(
        generated,
        tokenizer,
        length=condition.length,
        key_label=condition.key_label,
        key_tonic_pc=condition.key_tonic_pc,
        measure_indices=condition.measure_indices,
        beat_positions=condition.beat_positions,
    )
    symbolic_repair_summary: dict[str, Any] = {"enabled": False}
    cadential_repair_summary: dict[str, Any] = {"enabled": False}
    if optimize_symbols:
        repaired = optimize_symbolic_postprocess(
            generated,
            condition.known_mask,
            tokenizer,
            length=condition.length,
            key_tonic_pc=condition.key_tonic_pc,
            harmonic_labels=generated_harmony,
            max_passes=repair_passes,
        )
        generated = repaired.tokens
        generated[condition.known_mask] = condition.source_tokens[condition.known_mask]
        symbolic_repair_summary = repaired.summary
        generated_harmony = annotate_tokens_harmony(
            generated,
            tokenizer,
            length=condition.length,
            key_label=condition.key_label,
            key_tonic_pc=condition.key_tonic_pc,
            measure_indices=condition.measure_indices,
            beat_positions=condition.beat_positions,
        )
    if repair_final_cadence:
        before_cadence_harmony = generated_harmony
        before_cadence_report = build_explanation_report(
            generated,
            tokenizer,
            length=condition.length,
            title=f"{stem} pre-cadence repair report",
            key_tonic_pc=int(before_cadence_harmony["key_tonic_pc"]),
            harmonic_labels=before_cadence_harmony,
        )
        cadence_candidate = apply_final_authentic_cadence(
            generated,
            condition.known_mask,
            tokenizer,
            length=condition.length,
            key_tonic_pc=condition.key_tonic_pc,
            key_label=condition.key_label,
        )
        candidate_harmony = annotate_tokens_harmony(
            cadence_candidate.tokens,
            tokenizer,
            length=condition.length,
            key_label=condition.key_label,
            key_tonic_pc=condition.key_tonic_pc,
            measure_indices=condition.measure_indices,
            beat_positions=condition.beat_positions,
        )
        candidate_report = build_explanation_report(
            cadence_candidate.tokens,
            tokenizer,
            length=condition.length,
            title=f"{input_musicxml.stem} candidate cadence repair report",
            key_tonic_pc=int(candidate_harmony["key_tonic_pc"]),
            harmonic_labels=candidate_harmony,
        )
        accept_cadence = should_accept_cadential_repair(before_cadence_report, candidate_report, cadence_candidate.summary)
        cadential_repair_summary = {
            **cadence_candidate.summary,
            "accepted": bool(accept_cadence),
            "penalty_before": float(before_cadence_report.get("total_penalty", 0.0)),
            "penalty_after": float(candidate_report.get("total_penalty", 0.0)),
            "violations_before": int(before_cadence_report.get("total_violations", 0)),
            "violations_after": int(candidate_report.get("total_violations", 0)),
            "cadence_before": before_cadence_report.get("cadence_type", "UNKNOWN"),
            "cadence_after": candidate_report.get("cadence_type", "UNKNOWN"),
        }
        if accept_cadence:
            generated = cadence_candidate.tokens
            generated[condition.known_mask] = condition.source_tokens[condition.known_mask]
            generated_harmony = candidate_harmony
    output_musicxml = output_dir / f"{stem}_satb_harmonized.musicxml"
    condition_musicxml = output_dir / f"{stem}_condition.musicxml"
    report_txt = output_dir / f"{stem}_rule_report.txt"
    report_json = output_dir / f"{stem}_rule_report.json"
    summary_json = output_dir / f"{stem}_harmonization_summary.json"

    export_tokens_to_musicxml(
        condition.source_tokens,
        tokenizer,
        condition_musicxml,
        length=condition.length,
        title=f"{stem} input condition",
    )
    export_tokens_to_musicxml(
        generated,
        tokenizer,
        output_musicxml,
        length=condition.length,
        title=f"{stem} SATB harmonization",
    )
    rule_report = build_explanation_report(
        generated,
        tokenizer,
        length=condition.length,
        title=f"{stem} SATB harmonization rule report",
        key_tonic_pc=int(generated_harmony["key_tonic_pc"]),
        harmonic_labels=generated_harmony,
    )
    if symbolic_repair_summary.get("enabled"):
        symbolic_repair_summary["reported_final_total_penalty"] = float(rule_report.get("total_penalty", 0.0))
        symbolic_repair_summary["reported_final_total_violations"] = int(rule_report.get("total_violations", 0))
    write_explanation_report(rule_report, report_txt, report_json)

    audio: dict[str, Any] = {"requested": bool(render_audio)}
    if render_audio:
        from chorale.playback_render import PlaybackRenderSettings, render_musicxml_to_audio

        wav_path = output_dir / f"{stem}_satb_harmonized.wav"
        mp3_path = output_dir / f"{stem}_satb_harmonized.mp3"
        render_result = render_musicxml_to_audio(
            output_musicxml,
            wav_path,
            mp3_path,
            PlaybackRenderSettings(backend=audio_backend),
        )
        audio.update(
            {
                "backend": render_result.backend,
                "wav": str(wav_path) if wav_path.is_file() else "",
                "mp3": str(mp3_path) if mp3_path.is_file() else "",
                "wav_status": render_result.wav_status,
                "mp3_status": render_result.mp3_status,
                "duration_sec": render_result.duration_sec,
                "rms": render_result.rms,
                "peak": render_result.peak,
                "message": render_result.message,
            }
        )

    known_voice_preservation = validate_known_voice_preservation(
        condition.source_tokens,
        generated,
        condition.known_mask,
        length=condition.length,
    )
    score_validation = validate_exported_musicxml(output_musicxml)

    summary = {
        "schema": "project1_user_harmonization_v1",
        "input_musicxml": str(input_musicxml),
        "engine": engine,
        "task": task,
        "input_role": input_role,
        "known_voices": condition.known_voices,
        "input_preflight": input_preflight,
        "length_timesteps": condition.length,
        "grid_quarter_length": tokenizer.grid_quarter_length,
        "key_label": condition.key_label,
        "key_tonic_pc": condition.key_tonic_pc,
        "apply_rule_guided_decoding": bool(apply_rules),
        "symbolic_repair": symbolic_repair_summary,
        "cadential_repair": cadential_repair_summary,
        "outputs": {
            "condition_musicxml": str(condition_musicxml),
            "harmonized_musicxml": str(output_musicxml),
            "rule_report_txt": str(report_txt),
            "rule_report_json": str(report_json),
        },
        "audio": audio,
        "known_voice_preservation": known_voice_preservation,
        "score_validation": score_validation,
        "rule_summary": {
            "total_penalty": rule_report.get("total_penalty", 0),
            "total_violations": rule_report.get("total_violations", 0),
            "violations_per_100_timesteps": rule_report.get("violations_per_100_timesteps", 0),
            "cadence_type": rule_report.get("cadence_type", "UNKNOWN"),
            "seventh_resolution_violations": rule_report.get("seventh_resolution_violations", 0),
        },
        "limitations": [
            "Playback audio, when requested, is rendered from MusicXML notation and is not a neural audio model.",
            "The rule fallback is deterministic and practical for continuity, but neural checkpoint output should be used for model-quality claims.",
        ],
    }
    summary["outputs"]["summary_json"] = str(summary_json)
    summary["quality_gate"] = evaluate_harmonization_quality(
        summary,
        max_violations_per_100=max_violations_per_100,
        max_total_violations=max_total_violations,
        max_total_penalty=max_total_penalty,
        max_seventh_resolution_violations=max_seventh_resolution_violations,
        require_audio=require_audio_for_quality,
    )
    write_json(summary, summary_json)
    return summary


def load_checkpoint_payload(checkpoint: str | Path | None) -> dict[str, Any] | None:
    if not checkpoint:
        return None
    path = Path(checkpoint)
    if not path.is_file():
        raise FileNotFoundError(f"Checkpoint not found: {path}")
    return safe_torch_load(path, map_location=torch.device("cpu"))


def load_harmonize_config(config: str | Path | None, checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    if checkpoint is not None and isinstance(checkpoint.get("config"), dict):
        return dict(checkpoint["config"])
    if config:
        return load_config(config)
    return {}


def tokenizer_from_sources(config: dict[str, Any], checkpoint: dict[str, Any] | None) -> ScoreTokenizer:
    if checkpoint is not None and isinstance(checkpoint.get("tokenizer"), dict):
        meta = checkpoint["tokenizer"]
        return ScoreTokenizer(
            grid_quarter_length=float(meta.get("grid_quarter_length", 0.25)),
            min_midi=int(meta.get("min_midi", 36)),
            max_midi=int(meta.get("max_midi", 84)),
            max_seq_len=int(meta.get("max_seq_len", 256)),
        )
    data_cfg = config.get("data", {}) if isinstance(config, dict) else {}
    return ScoreTokenizer(
        grid_quarter_length=float(data_cfg.get("grid_quarter_length", 0.25)),
        min_midi=int(data_cfg.get("min_midi", 36)),
        max_midi=int(data_cfg.get("max_midi", 84)),
        max_seq_len=int(data_cfg.get("max_seq_len", 256)),
    )


def parse_as_score(path: Path) -> stream.Score:
    parsed = converter.parse(str(path))
    if isinstance(parsed, stream.Score):
        return parsed
    score = stream.Score()
    if isinstance(parsed, stream.Part):
        score.insert(0, parsed)
    else:
        part = stream.Part()
        for element in parsed.flatten().notesAndRests:
            part.insert(float(element.offset), element)
        score.insert(0, part)
    return score


def build_condition_score(
    score: stream.Score,
    tokenizer: ScoreTokenizer,
    *,
    task: str,
    input_role: str,
    known_voices: str | list[str] | None,
) -> ConditionScore:
    parts = list(score.parts)
    if not parts:
        raise ValueError("Input score has no parts")
    normalized_task = task.lower().strip()
    known_indices = resolve_known_voice_indices(score, normalized_task, input_role, known_voices)
    if not known_indices:
        raise ValueError("No known voices resolved from input; use --input-role or --known-voices")

    source_tokens = np.full((tokenizer.max_seq_len, 4), tokenizer.PAD, dtype=np.int64)
    total_quarters = max(float(part.duration.quarterLength) for part in parts)
    length = max(1, int(np.ceil(total_quarters / tokenizer.grid_quarter_length)))
    length = min(length, tokenizer.max_seq_len)
    source_tokens[:length, :] = tokenizer.REST

    if len(parts) >= 4:
        encoded = tokenizer.encode_score(score, name=score.metadata.title if score.metadata else "")
        source_tokens = np.asarray(encoded["tokens"], dtype=np.int64)
        length = int(encoded["length"])
        beat_positions = np.asarray(encoded["beat_positions"], dtype=np.int64)
        measure_indices = np.asarray(encoded["measure_indices"], dtype=np.int64)
    else:
        part_voice_indices = infer_part_voice_indices(score, input_role)
        for part, voice_idx in zip(parts, part_voice_indices):
            encode_part_into_tokens(source_tokens, part, int(voice_idx), tokenizer, length)
        beat_positions, measure_indices = make_time_features(tokenizer.max_seq_len, tokenizer.grid_quarter_length)

    valid_mask = np.zeros_like(source_tokens, dtype=bool)
    valid_mask[:length, :] = True
    known_mask = np.zeros_like(source_tokens, dtype=bool)
    for idx in known_indices:
        known_mask[:length, idx] = True
    target_mask = valid_mask & ~known_mask
    input_tokens = source_tokens.copy()
    input_tokens[target_mask] = tokenizer.MASK
    input_tokens[~valid_mask] = tokenizer.PAD

    try:
        local_key = approximate_key(score)
        key_label, key_tonic_pc = key_label_and_tonic_pc(local_key)
    except Exception:
        key_label, key_tonic_pc = "C major", 0

    return ConditionScore(
        source_tokens=source_tokens,
        input_tokens=input_tokens,
        known_mask=known_mask,
        target_mask=target_mask,
        valid_mask=valid_mask,
        beat_positions=beat_positions,
        measure_indices=measure_indices,
        length=length,
        known_voices=[VOICE_NAMES[idx] for idx in known_indices],
        key_label=key_label,
        key_tonic_pc=int(key_tonic_pc),
    )


def resolve_known_voice_indices(
    score: stream.Score,
    task: str,
    input_role: str,
    known_voices: str | list[str] | None,
) -> list[int]:
    if known_voices:
        if isinstance(known_voices, str):
            names = [item.strip().lower() for item in known_voices.split(",") if item.strip()]
        else:
            names = [str(item).strip().lower() for item in known_voices if str(item).strip()]
        return sorted({VOICE_TO_INDEX[name] for name in names if name in VOICE_TO_INDEX})
    if task == "bass_to_satb":
        return [VOICE_TO_INDEX["bass"]]
    if task == "masked_infill":
        return infer_part_voice_indices(score, input_role)
    if task == "auto":
        inferred = infer_part_voice_indices(score, input_role)
        if len(inferred) == 1:
            return inferred
        return [VOICE_TO_INDEX["soprano"]]
    return [VOICE_TO_INDEX["soprano"]]


def infer_part_voice_indices(score: stream.Score, input_role: str) -> list[int]:
    parts = list(score.parts)
    indices: list[int] = []
    for part in parts:
        label = " ".join(str(item or "") for item in (part.partName, part.partAbbreviation, part.id)).lower()
        found = next((VOICE_TO_INDEX[name] for name in VOICE_NAMES if name in label), None)
        indices.append(int(found) if found is not None else -1)
    if all(idx >= 0 for idx in indices):
        return indices
    if len(parts) == 1:
        return [VOICE_TO_INDEX.get(input_role.lower().strip(), VOICE_TO_INDEX["soprano"])]
    if len(parts) == 2:
        fallback = [VOICE_TO_INDEX["soprano"], VOICE_TO_INDEX["bass"]]
    else:
        fallback = [0, 1, 2, 3]
    return [idx if idx >= 0 else fallback[pos] for pos, idx in enumerate(indices[:4])]


def encode_part_into_tokens(
    tokens: np.ndarray,
    part: stream.Part,
    voice_idx: int,
    tokenizer: ScoreTokenizer,
    length: int,
) -> None:
    for element in iter_notes_and_rests(part):
        start = quantize_offset(element_offset(element, part), tokenizer.grid_quarter_length)
        if start >= length:
            continue
        dur_steps = max(1, int(round(float(element.duration.quarterLength) / tokenizer.grid_quarter_length)))
        end = min(length, start + dur_steps)
        token = tokenizer.element_to_token(element, voice_idx)
        tokens[start, voice_idx] = token
        if end > start + 1:
            tokens[start + 1 : end, voice_idx] = tokenizer.HOLD


def condition_to_batch(condition: ConditionScore, harmony: dict[str, Any]) -> dict[str, torch.Tensor]:
    return {
        "tokens": torch.from_numpy(condition.source_tokens).long().unsqueeze(0),
        "input_tokens": torch.from_numpy(condition.input_tokens).long().unsqueeze(0),
        "known_mask": torch.from_numpy(condition.known_mask).bool().unsqueeze(0),
        "target_mask": torch.from_numpy(condition.target_mask).bool().unsqueeze(0),
        "valid_mask": torch.from_numpy(condition.valid_mask).bool().unsqueeze(0),
        "beat_positions": torch.from_numpy(condition.beat_positions).long().unsqueeze(0),
        "measure_indices": torch.from_numpy(condition.measure_indices).long().unsqueeze(0),
        "key_tonic_pc": torch.tensor([condition.key_tonic_pc], dtype=torch.long),
        "chord_roots": torch.from_numpy(np.asarray(harmony["chord_roots"], dtype=np.int64)).long().unsqueeze(0),
        "is_seventh_chord": torch.from_numpy(np.asarray(harmony["is_seventh_chord"], dtype=bool)).bool().unsqueeze(0),
        "is_dominant_function": torch.from_numpy(np.asarray(harmony["is_dominant_function"], dtype=bool)).bool().unsqueeze(0),
        "is_phrase_end": torch.from_numpy(np.asarray(harmony["is_phrase_end"], dtype=bool)).bool().unsqueeze(0),
        "chord_label_known": torch.from_numpy(np.asarray(harmony["chord_label_known"], dtype=bool)).bool().unsqueeze(0),
        "roman_numeral_known": torch.from_numpy(np.asarray(harmony["roman_numeral_known"], dtype=bool)).bool().unsqueeze(0),
    }


def practical_rule_harmonize(
    input_tokens: np.ndarray,
    known_mask: np.ndarray,
    tokenizer: ScoreTokenizer,
    *,
    length: int,
    key_tonic_pc: int = 0,
) -> np.ndarray:
    output = np.asarray(input_tokens, dtype=np.int64).copy()
    output[output == tokenizer.MASK] = tokenizer.REST
    known_midi = tokenizer.expand_holds(output, length=length)
    last = [72, 64, 55, 48]
    for t in range(length):
        row = known_midi[t].copy()
        soprano = _known_pitch(row, known_mask, t, 0)
        bass = _known_pitch(row, known_mask, t, 3)
        if soprano is None and bass is None:
            soprano = last[0]
        chord_pcs = choose_chord_pcs(soprano, bass, key_tonic_pc)
        if bass is None:
            bass = nearest_pitch(chord_pcs, last[3], VOICE_RANGES["bass"], upper_limit=(soprano - 12 if soprano else None))
        if soprano is None:
            soprano = nearest_pitch(chord_pcs, bass + 19, VOICE_RANGES["soprano"], lower_limit=bass + 8)
        alto = _known_pitch(row, known_mask, t, 1)
        tenor = _known_pitch(row, known_mask, t, 2)
        if alto is None:
            alto = nearest_pitch(chord_pcs, soprano - 5, VOICE_RANGES["alto"], upper_limit=soprano)
        if tenor is None:
            tenor = nearest_pitch(chord_pcs, min(alto - 4, bass + 12), VOICE_RANGES["tenor"], lower_limit=bass, upper_limit=alto)
        midi_row = repair_vertical_order([soprano, alto, tenor, bass])
        for voice_idx, midi in enumerate(midi_row):
            if known_mask[t, voice_idx]:
                continue
            output[t, voice_idx] = tokenizer.midi_to_token(int(midi))
            last[voice_idx] = int(midi)
        for voice_idx in range(4):
            if known_mask[t, voice_idx] and not np.isnan(row[voice_idx]):
                last[voice_idx] = int(row[voice_idx])
    if length < output.shape[0]:
        output[length:] = tokenizer.PAD
    return output


def _known_pitch(row: np.ndarray, known_mask: np.ndarray, t: int, voice_idx: int) -> int | None:
    if not bool(known_mask[t, voice_idx]) or np.isnan(row[voice_idx]):
        return None
    return int(row[voice_idx])


def choose_chord_pcs(soprano: int | None, bass: int | None, key_tonic_pc: int) -> set[int]:
    if bass is not None:
        root = bass % 12
    elif soprano is not None and soprano % 12 in major_triad_pcs(key_tonic_pc):
        root = key_tonic_pc % 12
    elif soprano is not None:
        root = soprano % 12
    else:
        root = key_tonic_pc % 12
    pcs = diatonic_triad(root, key_tonic_pc)
    if soprano is not None:
        pcs.add(soprano % 12)
    if bass is not None:
        pcs.add(bass % 12)
    return pcs


def major_triad_pcs(root_pc: int) -> set[int]:
    root = int(root_pc) % 12
    return {root, (root + 4) % 12, (root + 7) % 12}


def diatonic_triad(root_pc: int, key_tonic_pc: int) -> set[int]:
    root = int(root_pc) % 12
    degree = (root - int(key_tonic_pc)) % 12
    if degree in {0, 5, 7}:
        third = 4
        fifth = 7
    elif degree == 11:
        third = 3
        fifth = 6
    else:
        third = 3
        fifth = 7
    return {root, (root + third) % 12, (root + fifth) % 12}


def nearest_pitch(
    pcs: set[int],
    target: int,
    midi_range: tuple[int, int],
    *,
    lower_limit: int | None = None,
    upper_limit: int | None = None,
) -> int:
    low, high = midi_range
    if lower_limit is not None:
        low = max(low, int(lower_limit))
    if upper_limit is not None:
        high = min(high, int(upper_limit))
    if low > high:
        low, high = midi_range
    candidates = [midi for midi in range(low, high + 1) if midi % 12 in pcs]
    if not candidates:
        return int(np.clip(target, low, high))
    return int(min(candidates, key=lambda pitch: abs(pitch - target)))


def repair_vertical_order(row: list[int]) -> list[int]:
    ranges = [VOICE_RANGES[name] for name in VOICE_NAMES]
    repaired = [int(np.clip(pitch, low, high)) for pitch, (low, high) in zip(row, ranges)]
    repaired[1] = min(repaired[1], repaired[0])
    repaired[2] = min(repaired[2], repaired[1])
    repaired[3] = min(repaired[3], repaired[2])
    repaired[1] = max(repaired[1], VOICE_RANGES["alto"][0])
    repaired[2] = max(repaired[2], VOICE_RANGES["tenor"][0])
    repaired[3] = max(repaired[3], VOICE_RANGES["bass"][0])
    return repaired


def validate_known_voice_preservation(
    source_tokens: np.ndarray,
    generated_tokens: np.ndarray,
    known_mask: np.ndarray,
    *,
    length: int,
) -> dict[str, Any]:
    active = np.zeros_like(known_mask, dtype=bool)
    active[:length, :] = known_mask[:length, :]
    mismatches = np.argwhere((np.asarray(source_tokens) != np.asarray(generated_tokens)) & active)
    examples = [
        {
            "timestep": int(t),
            "voice": VOICE_NAMES[int(v)],
            "source_token": int(source_tokens[int(t), int(v)]),
            "generated_token": int(generated_tokens[int(t), int(v)]),
        }
        for t, v in mismatches[:10]
    ]
    return {
        "pass": int(len(mismatches)) == 0,
        "known_token_cells": int(active.sum()),
        "mismatches": int(len(mismatches)),
        "examples": examples,
    }


def validate_exported_musicxml(path: str | Path) -> dict[str, Any]:
    try:
        parsed = converter.parse(str(path))
        parts = list(parsed.parts) if isinstance(parsed, stream.Score) else []
        note_count = sum(1 for part in parts for _ in part.flatten().notes)
        issues: list[str] = []
        if len(parts) != 4:
            issues.append(f"expected 4 SATB parts, found {len(parts)}")
        if note_count <= 0:
            issues.append("exported score contains no notes")
        return {
            "parse_ok": True,
            "part_count": int(len(parts)),
            "note_count": int(note_count),
            "has_notes": note_count > 0,
            "issues": issues,
        }
    except Exception as exc:
        return {
            "parse_ok": False,
            "part_count": None,
            "note_count": 0,
            "has_notes": False,
            "issues": ["MusicXML parse failed"],
            "error": str(exc),
        }


def should_accept_cadential_repair(
    before_report: dict[str, Any],
    after_report: dict[str, Any],
    repair_summary: dict[str, Any],
) -> bool:
    if not bool(repair_summary.get("applied", False)):
        return False
    before_penalty = float(before_report.get("total_penalty", 0.0))
    after_penalty = float(after_report.get("total_penalty", 0.0))
    before_violations = int(before_report.get("total_violations", 0))
    after_violations = int(after_report.get("total_violations", 0))
    before_cadence = str(before_report.get("cadence_type", "UNKNOWN"))
    after_cadence = str(after_report.get("cadence_type", "UNKNOWN"))
    cadence_rank = {
        "UNKNOWN": 0,
        "half_cadence_like": 1,
        "deceptive_cadence_like": 1,
        "tonic_closure_like": 2,
        "authentic_cadence_like": 3,
    }
    cadence_improved = cadence_rank.get(after_cadence, 0) > cadence_rank.get(before_cadence, 0)
    penalty_ok = after_penalty <= before_penalty + 2.0
    violations_ok = after_violations <= before_violations + 2
    return bool(cadence_improved and penalty_ok and violations_ok)


def main() -> None:
    parser = argparse.ArgumentParser(description="Harmonize a user MusicXML melody/bass/partial SATB file.")
    parser.add_argument("--input", required=True, help="Input MusicXML, XML, or MXL score.")
    parser.add_argument("--output-dir", default="generated_scores/user_harmonizations")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--config", default=None)
    parser.add_argument("--task", default="soprano_to_satb", choices=["soprano_to_satb", "bass_to_satb", "masked_infill", "auto"])
    parser.add_argument("--input-role", default="soprano", choices=list(VOICE_NAMES))
    parser.add_argument("--known-voices", default=None, help="Comma-separated known voices, e.g. soprano,bass.")
    parser.add_argument("--prefix", default=None)
    parser.add_argument("--no-rule-guided", action="store_true")
    parser.add_argument("--no-symbolic-repair", action="store_true")
    parser.add_argument("--no-final-cadence-repair", action="store_true")
    parser.add_argument("--repair-passes", type=int, default=12)
    parser.add_argument("--render-audio", action="store_true")
    parser.add_argument("--audio-backend", default="additive")
    parser.add_argument("--max-violations-per-100", type=float, default=12.0)
    parser.add_argument("--max-total-violations", type=int, default=24)
    parser.add_argument("--max-total-penalty", type=float, default=20.0)
    parser.add_argument("--max-seventh-resolution-violations", type=int, default=12)
    parser.add_argument("--require-audio-for-quality", action="store_true")
    args = parser.parse_args()
    summary = harmonize_musicxml(
        args.input,
        args.output_dir,
        checkpoint=args.checkpoint,
        config=args.config,
        task=args.task,
        input_role=args.input_role,
        known_voices=args.known_voices,
        prefix=args.prefix,
        apply_rules=not args.no_rule_guided,
        render_audio=args.render_audio,
        audio_backend=args.audio_backend,
        optimize_symbols=not args.no_symbolic_repair,
        repair_passes=args.repair_passes,
        repair_final_cadence=not args.no_final_cadence_repair,
        max_violations_per_100=args.max_violations_per_100,
        max_total_violations=args.max_total_violations,
        max_total_penalty=args.max_total_penalty,
        max_seventh_resolution_violations=args.max_seventh_resolution_violations,
        require_audio_for_quality=args.require_audio_for_quality,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
