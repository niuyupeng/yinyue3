from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Any

import numpy as np

from chorale.data.score_tokenizer import ScoreTokenizer, VOICE_NAMES, VOICE_RANGES
from chorale.theory.explain_report import build_explanation_report


SEVERE_RULES = {
    "voice_range",
    "voice_crossing",
    "spacing",
    "parallel_fifth",
    "parallel_octave",
    "hidden_direct_fifth",
    "hidden_direct_octave",
    "leading_tone_resolution",
    "seventh_resolution",
}


@dataclass(frozen=True)
class RepairResult:
    tokens: np.ndarray
    summary: dict[str, Any]


def optimize_symbolic_postprocess(
    tokens: np.ndarray,
    known_mask: np.ndarray,
    tokenizer: ScoreTokenizer,
    *,
    length: int,
    key_tonic_pc: int = 0,
    harmonic_labels: dict[str, Any] | None = None,
    max_passes: int = 2,
    max_hotspots: int = 96,
) -> RepairResult:
    """Greedy symbolic cleanup for generated SATB tokens.

    The optimizer preserves all known input positions. It only changes generated
    voices and accepts a local event edit when the full rule-report penalty
    decreases. This is deliberately conservative; it is a practical cleanup
    pass, not a hidden replacement for expert musical judgment.
    """
    working = tokenizer.sanitize_for_export(np.asarray(tokens, dtype=np.int64), length=length)
    known = np.asarray(known_mask, dtype=bool)
    baseline_report = score_report(working, tokenizer, length, key_tonic_pc, harmonic_labels)
    best_penalty = float(baseline_report["total_penalty"])
    accepted: list[dict[str, Any]] = []
    candidate_checks = 0

    for pass_idx in range(max(0, int(max_passes))):
        report = score_report(working, tokenizer, length, key_tonic_pc, harmonic_labels)
        hotspots = severe_hotspots(report, max_hotspots=max_hotspots)
        if not hotspots:
            break
        improved_this_pass = False
        for timestep in hotspots:
            midi = tokenizer.expand_holds(working, length=length)
            for voice_idx in repair_voice_order(report, timestep):
                if timestep >= known.shape[0] or bool(known[timestep, voice_idx]):
                    continue
                current = midi[timestep, voice_idx]
                if np.isnan(current):
                    continue
                segment = editable_event_segment(midi[:, voice_idx], known[:, voice_idx], timestep)
                if segment is None:
                    continue
                best_candidate: tuple[float, np.ndarray, int] | None = None
                for candidate_pitch in pitch_candidates(int(round(float(current))), voice_idx, midi[timestep]):
                    candidate = working.copy()
                    start, end = segment
                    candidate[start:end, voice_idx] = tokenizer.midi_to_token(candidate_pitch)
                    candidate[known] = working[known]
                    candidate_report = score_report(candidate, tokenizer, length, key_tonic_pc, harmonic_labels)
                    candidate_checks += 1
                    penalty = float(candidate_report["total_penalty"])
                    if penalty + 1e-9 < best_penalty:
                        if best_candidate is None or penalty < best_candidate[0]:
                            best_candidate = (penalty, candidate, candidate_pitch)
                if best_candidate is not None:
                    previous_penalty = best_penalty
                    best_penalty, working, chosen_pitch = best_candidate
                    accepted.append(
                        {
                            "pass": pass_idx + 1,
                            "timestep": int(timestep),
                            "voice": VOICE_NAMES[voice_idx],
                            "chosen_midi": int(chosen_pitch),
                            "penalty_before": previous_penalty,
                            "penalty_after": best_penalty,
                        }
                    )
                    improved_this_pass = True
                    break
            if improved_this_pass:
                break
        if not improved_this_pass:
            break

    final_report = score_report(working, tokenizer, length, key_tonic_pc, harmonic_labels)
    summary = {
        "enabled": True,
        "optimizer_baseline_total_penalty": float(baseline_report["total_penalty"]),
        "optimizer_baseline_total_violations": int(baseline_report["total_violations"]),
        "optimizer_final_total_penalty": float(final_report["total_penalty"]),
        "optimizer_final_total_violations": int(final_report["total_violations"]),
        "accepted_repairs": len(accepted),
        "candidate_checks": int(candidate_checks),
        "repairs": accepted,
        "note": "Known input voices were preserved; only generated voices were edited.",
    }
    return RepairResult(tokens=working, summary=summary)


def apply_final_tonic_closure(
    tokens: np.ndarray,
    known_mask: np.ndarray,
    tokenizer: ScoreTokenizer,
    *,
    length: int,
    key_tonic_pc: int = 0,
    key_label: str = "",
) -> RepairResult:
    """Fill generated final voices with a conservative tonic-triad closure.

    This pass is intentionally narrow. It edits only generated voices in the
    final known pitch event and refuses to apply if any known final pitch is not
    compatible with the tonic triad. The goal is practical score usability:
    avoid otherwise successful harmonizations ending with missing lower voices
    or an indeterminate final sonority.
    """
    working = tokenizer.sanitize_for_export(np.asarray(tokens, dtype=np.int64), length=length)
    known = np.asarray(known_mask, dtype=bool)
    midi = tokenizer.expand_holds(working, length=length)
    anchor = final_known_pitch_anchor(midi, known, length)
    if anchor is None:
        return RepairResult(tokens=working, summary={"enabled": True, "applied": False, "reason": "no known final pitch anchor"})
    anchor_t, anchor_voice = anchor
    span = pitch_span(midi[:, anchor_voice], anchor_t)
    if span is None:
        return RepairResult(tokens=working, summary={"enabled": True, "applied": False, "reason": "could not determine final pitch span"})
    start, end = span
    row_at_start = midi[start].copy()
    tonic_pc = int(key_tonic_pc) % 12
    mode = "minor" if "minor" in str(key_label).lower() or str(key_label).strip()[:1].islower() else "major"
    third = 3 if mode == "minor" else 4
    triad_pcs = {tonic_pc, (tonic_pc + third) % 12, (tonic_pc + 7) % 12}

    fixed: list[int | None] = []
    for voice_idx in range(4):
        pitch = row_at_start[voice_idx]
        if bool(known[start, voice_idx]):
            if np.isnan(pitch):
                return RepairResult(
                    tokens=working,
                    summary={
                        "enabled": True,
                        "applied": False,
                        "reason": f"known {VOICE_NAMES[voice_idx]} is resting at final closure point",
                        "start_timestep": int(start),
                        "end_timestep": int(end),
                    },
                )
            pitch_int = int(round(float(pitch)))
            if pitch_int % 12 not in triad_pcs:
                return RepairResult(
                    tokens=working,
                    summary={
                        "enabled": True,
                        "applied": False,
                        "reason": f"known {VOICE_NAMES[voice_idx]} final pitch is not in tonic triad",
                        "start_timestep": int(start),
                        "end_timestep": int(end),
                        "known_pitch": pitch_int,
                    },
                )
            fixed.append(pitch_int)
        else:
            fixed.append(None)

    selected = choose_closure_row(row_at_start, fixed, triad_pcs, tonic_pc)
    if selected is None:
        return RepairResult(
            tokens=working,
            summary={
                "enabled": True,
                "applied": False,
                "reason": "no SATB tonic closure candidate satisfied ordering and spacing",
                "start_timestep": int(start),
                "end_timestep": int(end),
            },
        )

    candidate = working.copy()
    changed: list[dict[str, Any]] = []
    for voice_idx, midi_pitch in enumerate(selected):
        if bool(known[start, voice_idx]):
            continue
        for t in range(start, end):
            if t >= len(candidate) or bool(known[t, voice_idx]):
                continue
            candidate[t, voice_idx] = tokenizer.midi_to_token(int(midi_pitch)) if t == start else tokenizer.HOLD
        for t in range(end, int(length)):
            if t >= len(candidate) or bool(known[t, voice_idx]):
                continue
            candidate[t, voice_idx] = tokenizer.REST
        changed.append({"voice": VOICE_NAMES[voice_idx], "midi": int(midi_pitch)})
    candidate[known] = working[known]
    return RepairResult(
        tokens=candidate,
        summary={
            "enabled": True,
            "applied": bool(changed),
            "reason": "final generated voices closed on tonic triad" if changed else "all final voices were known",
            "start_timestep": int(start),
            "end_timestep": int(end),
            "anchor_voice": VOICE_NAMES[int(anchor_voice)],
            "anchor_timestep": int(anchor_t),
            "key_tonic_pc": int(tonic_pc),
            "mode": mode,
            "chosen_midis": {VOICE_NAMES[idx]: int(pitch) for idx, pitch in enumerate(selected)},
            "changed_generated_voices": changed,
            "cleared_generated_tail_from": int(end),
            "note": "Known input voices were preserved; only generated final-closure voices were edited.",
        },
    )


def apply_final_authentic_cadence(
    tokens: np.ndarray,
    known_mask: np.ndarray,
    tokenizer: ScoreTokenizer,
    *,
    length: int,
    key_tonic_pc: int = 0,
    key_label: str = "",
) -> RepairResult:
    """Create a conservative V-I final cadence when the known line permits it.

    The final tonic closure is applied first. Then the previous known pitch
    event in the anchor voice is rewritten as a generated-voice dominant
    sonority only if that known pitch belongs to V in the estimated key.
    """
    closure = apply_final_tonic_closure(
        tokens,
        known_mask,
        tokenizer,
        length=length,
        key_tonic_pc=key_tonic_pc,
        key_label=key_label,
    )
    working = closure.tokens.copy()
    known = np.asarray(known_mask, dtype=bool)
    if not bool(closure.summary.get("applied", False)):
        return RepairResult(
            tokens=working,
            summary={
                "enabled": True,
                "applied": False,
                "tonic_closure": closure.summary,
                "reason": "tonic closure did not apply; authentic cadence repair skipped",
            },
        )

    midi = tokenizer.expand_holds(working, length=length)
    anchor_voice = VOICE_NAMES.index(str(closure.summary.get("anchor_voice", "soprano")))
    final_start = int(closure.summary.get("start_timestep", 0))
    previous = previous_known_pitch_event(midi[:, anchor_voice], known[:, anchor_voice], final_start)
    if previous is None:
        return RepairResult(
            tokens=working,
            summary={
                "enabled": True,
                "applied": False,
                "tonic_closure": closure.summary,
                "reason": "no previous known pitch event for dominant preparation",
            },
        )
    prev_start, prev_end, prev_pitch = previous
    tonic_pc = int(key_tonic_pc) % 12
    dominant_pc = (tonic_pc + 7) % 12
    dominant_pcs = {dominant_pc, (tonic_pc + 11) % 12, (tonic_pc + 2) % 12}
    if int(prev_pitch) % 12 not in dominant_pcs:
        return RepairResult(
            tokens=working,
            summary={
                "enabled": True,
                "applied": False,
                "tonic_closure": closure.summary,
                "reason": "previous known pitch is not compatible with dominant harmony",
                "previous_pitch": int(prev_pitch),
                "previous_timestep": int(prev_start),
            },
        )

    row_at_start = midi[prev_start].copy()
    fixed: list[int | None] = []
    for voice_idx in range(4):
        pitch = row_at_start[voice_idx]
        if bool(known[prev_start, voice_idx]):
            if np.isnan(pitch) or int(round(float(pitch))) % 12 not in dominant_pcs:
                return RepairResult(
                    tokens=working,
                    summary={
                        "enabled": True,
                        "applied": False,
                        "tonic_closure": closure.summary,
                        "reason": f"known {VOICE_NAMES[voice_idx]} is not compatible with dominant preparation",
                        "previous_timestep": int(prev_start),
                    },
                )
            fixed.append(int(round(float(pitch))))
        else:
            fixed.append(None)

    selected = choose_cadence_row(row_at_start, fixed, dominant_pcs, dominant_pc)
    if selected is None:
        return RepairResult(
            tokens=working,
            summary={
                "enabled": True,
                "applied": False,
                "tonic_closure": closure.summary,
                "reason": "no SATB dominant candidate satisfied ordering and spacing",
                "previous_timestep": int(prev_start),
            },
        )

    candidate = working.copy()
    changed: list[dict[str, Any]] = []
    for voice_idx, midi_pitch in enumerate(selected):
        if bool(known[prev_start, voice_idx]):
            continue
        for t in range(prev_start, prev_end):
            if t >= len(candidate) or bool(known[t, voice_idx]):
                continue
            candidate[t, voice_idx] = tokenizer.midi_to_token(int(midi_pitch)) if t == prev_start else tokenizer.HOLD
        changed.append({"voice": VOICE_NAMES[voice_idx], "midi": int(midi_pitch)})
    candidate[known] = working[known]
    return RepairResult(
        tokens=candidate,
        summary={
            "enabled": True,
            "applied": bool(changed),
            "reason": "final cadence prepared with dominant-to-tonic progression" if changed else "dominant preparation already fixed by known voices",
            "tonic_closure": closure.summary,
            "dominant_start_timestep": int(prev_start),
            "dominant_end_timestep": int(prev_end),
            "dominant_anchor_voice": VOICE_NAMES[int(anchor_voice)],
            "dominant_anchor_pitch": int(prev_pitch),
            "dominant_pc": int(dominant_pc),
            "dominant_midis": {VOICE_NAMES[idx]: int(pitch) for idx, pitch in enumerate(selected)},
            "changed_generated_voices": changed,
            "note": "Known input voices were preserved; only generated dominant-preparation and final-closure voices were edited.",
        },
    )


def final_known_pitch_anchor(midi: np.ndarray, known: np.ndarray, length: int) -> tuple[int, int] | None:
    voice_priority = [0, 3, 1, 2]
    best: tuple[int, int] | None = None
    for voice_idx in voice_priority:
        for timestep in range(int(length) - 1, -1, -1):
            if timestep >= known.shape[0] or not bool(known[timestep, voice_idx]):
                continue
            if np.isnan(midi[timestep, voice_idx]):
                continue
            candidate = (int(timestep), int(voice_idx))
            if best is None or candidate[0] > best[0]:
                best = candidate
            break
    return best


def pitch_span(voice_midi: np.ndarray, timestep: int) -> tuple[int, int] | None:
    if timestep < 0 or timestep >= len(voice_midi) or np.isnan(voice_midi[timestep]):
        return None
    pitch = int(round(float(voice_midi[timestep])))
    start = int(timestep)
    while start > 0 and not np.isnan(voice_midi[start - 1]):
        if int(round(float(voice_midi[start - 1]))) != pitch:
            break
        start -= 1
    end = int(timestep) + 1
    while end < len(voice_midi) and not np.isnan(voice_midi[end]):
        if int(round(float(voice_midi[end]))) != pitch:
            break
        end += 1
    return (start, end) if end > start else None


def previous_known_pitch_event(
    voice_midi: np.ndarray,
    known_voice_mask: np.ndarray,
    before_timestep: int,
) -> tuple[int, int, int] | None:
    t = int(before_timestep) - 1
    while t >= 0:
        if bool(known_voice_mask[t]) and not np.isnan(voice_midi[t]):
            span = pitch_span(voice_midi, t)
            if span is None:
                return None
            start, end = span
            pitch = int(round(float(voice_midi[t])))
            return int(start), int(min(end, before_timestep)), pitch
        t -= 1
    return None


def choose_closure_row(
    current_row: np.ndarray,
    fixed: list[int | None],
    triad_pcs: set[int],
    tonic_pc: int,
) -> list[int] | None:
    candidates: list[list[int]] = []
    for voice_idx, fixed_pitch in enumerate(fixed):
        if fixed_pitch is not None:
            candidates.append([int(fixed_pitch)])
            continue
        low, high = VOICE_RANGES[VOICE_NAMES[voice_idx]]
        pcs = {tonic_pc} if voice_idx == 3 else triad_pcs
        voice_candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 in pcs]
        if not voice_candidates:
            return None
        reference = current_row[voice_idx]
        if np.isnan(reference):
            reference = default_voice_target(voice_idx, tonic_pc)
        voice_candidates = sorted(voice_candidates, key=lambda pitch: abs(pitch - float(reference)))[:10]
        candidates.append([int(pitch) for pitch in voice_candidates])

    best_row: list[int] | None = None
    best_score = float("inf")
    for row_tuple in product(*candidates):
        row = [int(pitch) for pitch in row_tuple]
        if not valid_satb_closure_row(row):
            continue
        pcs = {pitch % 12 for pitch in row}
        missing = triad_pcs - pcs
        score = 0.0
        for voice_idx, pitch in enumerate(row):
            if not np.isnan(current_row[voice_idx]):
                score += abs(pitch - float(current_row[voice_idx]))
        score += 30.0 * len(missing)
        if row[3] % 12 != tonic_pc:
            score += 100.0
        if (tonic_pc + 3) % 12 not in pcs and (tonic_pc + 4) % 12 not in pcs:
            score += 15.0
        if score < best_score:
            best_score = score
            best_row = row
    return best_row


def choose_cadence_row(
    current_row: np.ndarray,
    fixed: list[int | None],
    chord_pcs: set[int],
    bass_pc: int,
) -> list[int] | None:
    candidates: list[list[int]] = []
    for voice_idx, fixed_pitch in enumerate(fixed):
        if fixed_pitch is not None:
            candidates.append([int(fixed_pitch)])
            continue
        low, high = VOICE_RANGES[VOICE_NAMES[voice_idx]]
        pcs = {int(bass_pc) % 12} if voice_idx == 3 else chord_pcs
        voice_candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 in pcs]
        if not voice_candidates:
            return None
        reference = current_row[voice_idx]
        if np.isnan(reference):
            reference = default_voice_target(voice_idx, int(bass_pc) % 12)
        voice_candidates = sorted(voice_candidates, key=lambda pitch: abs(pitch - float(reference)))[:12]
        candidates.append([int(pitch) for pitch in voice_candidates])

    best_row: list[int] | None = None
    best_score = float("inf")
    for row_tuple in product(*candidates):
        row = [int(pitch) for pitch in row_tuple]
        if not valid_satb_closure_row(row):
            continue
        pcs = {pitch % 12 for pitch in row}
        missing = chord_pcs - pcs
        score = 20.0 * len(missing)
        if row[3] % 12 != int(bass_pc) % 12:
            score += 100.0
        for voice_idx, pitch in enumerate(row):
            if not np.isnan(current_row[voice_idx]):
                score += abs(pitch - float(current_row[voice_idx]))
        if score < best_score:
            best_score = score
            best_row = row
    return best_row


def valid_satb_closure_row(row: list[int]) -> bool:
    if len(row) != 4:
        return False
    if not (row[0] >= row[1] >= row[2] >= row[3]):
        return False
    if row[0] - row[1] > 12:
        return False
    if row[1] - row[2] > 12:
        return False
    if row[2] - row[3] > 19:
        return False
    for voice_idx, pitch in enumerate(row):
        low, high = VOICE_RANGES[VOICE_NAMES[voice_idx]]
        if pitch < low or pitch > high:
            return False
    return True


def default_voice_target(voice_idx: int, tonic_pc: int) -> int:
    defaults = [72, 64, 55, 48]
    target = defaults[voice_idx]
    low, high = VOICE_RANGES[VOICE_NAMES[voice_idx]]
    candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 == tonic_pc]
    if voice_idx in {1, 2}:
        candidates = [pitch for pitch in range(low, high + 1) if pitch % 12 in {tonic_pc, (tonic_pc + 4) % 12, (tonic_pc + 3) % 12, (tonic_pc + 7) % 12}]
    if not candidates:
        return int(np.clip(target, low, high))
    return int(min(candidates, key=lambda pitch: abs(pitch - target)))


def score_report(
    tokens: np.ndarray,
    tokenizer: ScoreTokenizer,
    length: int,
    key_tonic_pc: int,
    harmonic_labels: dict[str, Any] | None,
) -> dict[str, Any]:
    return build_explanation_report(
        tokens,
        tokenizer,
        length=length,
        key_tonic_pc=key_tonic_pc,
        harmonic_labels=harmonic_labels,
    )


def severe_hotspots(report: dict[str, Any], *, max_hotspots: int) -> list[int]:
    timesteps: list[int] = []
    seen: set[int] = set()
    for item in report.get("violations", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("rule")) not in SEVERE_RULES:
            continue
        timestep = int(item.get("timestep", -1))
        if timestep < 0 or timestep in seen:
            continue
        seen.add(timestep)
        timesteps.append(timestep)
        if len(timesteps) >= max(1, int(max_hotspots)):
            break
    return timesteps


def repair_voice_order(report: dict[str, Any], timestep: int) -> list[int]:
    rules_at_t = [
        str(item.get("rule"))
        for item in report.get("violations", [])
        if isinstance(item, dict) and int(item.get("timestep", -1)) == timestep
    ]
    if any(rule in {"parallel_octave", "parallel_fifth", "hidden_direct_fifth", "hidden_direct_octave"} for rule in rules_at_t):
        return [2, 1, 3, 0]
    if any(rule in {"voice_crossing", "spacing"} for rule in rules_at_t):
        return [1, 2, 3, 0]
    if any(rule in {"seventh_resolution", "leading_tone_resolution"} for rule in rules_at_t):
        return [1, 2, 3, 0]
    return [1, 2, 3, 0]


def editable_event_segment(voice_midi: np.ndarray, known_voice_mask: np.ndarray, timestep: int) -> tuple[int, int] | None:
    if timestep < 0 or timestep >= len(voice_midi) or bool(known_voice_mask[timestep]) or np.isnan(voice_midi[timestep]):
        return None
    pitch = int(round(float(voice_midi[timestep])))
    start = timestep
    while start > 0 and not bool(known_voice_mask[start - 1]) and not np.isnan(voice_midi[start - 1]):
        if int(round(float(voice_midi[start - 1]))) != pitch:
            break
        start -= 1
    end = timestep + 1
    while end < len(voice_midi) and not bool(known_voice_mask[end]) and not np.isnan(voice_midi[end]):
        if int(round(float(voice_midi[end]))) != pitch:
            break
        end += 1
    return (start, end) if end > start else None


def pitch_candidates(current: int, voice_idx: int, row: np.ndarray) -> list[int]:
    low, high = VOICE_RANGES[VOICE_NAMES[voice_idx]]
    local = [current, current - 1, current + 1, current - 2, current + 2, current - 3, current + 3, current - 5, current + 5]
    if voice_idx > 0 and not np.isnan(row[voice_idx - 1]):
        high = min(high, int(row[voice_idx - 1]))
    if voice_idx < 3 and not np.isnan(row[voice_idx + 1]):
        low = max(low, int(row[voice_idx + 1]))
    candidates = [int(p) for p in local if low <= int(p) <= high]
    if not candidates:
        candidates = [int(np.clip(current, low, high))]
    unique: list[int] = []
    for pitch in candidates:
        if pitch not in unique:
            unique.append(pitch)
    return unique
