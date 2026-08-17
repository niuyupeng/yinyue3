from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


RATING_COLUMNS = [
    "rater_id",
    "score_id",
    "harmonic_correctness_1_to_5",
    "voice_leading_correctness_1_to_5",
    "seventh_resolution_correctness_1_to_5",
    "cadence_quality_1_to_5",
    "singability_1_to_5",
    "stylistic_consistency_1_to_5",
    "usefulness_for_composition_pedagogy_1_to_5",
    "overall_preference_1_to_5",
    "comments",
]


def sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def candidate_sources(root: Path) -> dict[str, list[Path]]:
    patterns = {
        "ground_truth": [
            "expert_eval/project1/project1_sample*_ground_truth.musicxml",
            "generated_scores/cih_s2s_smoke/*ground_truth.musicxml",
        ],
        "vanilla_transformer": [
            "runs/chorale_transformer_no_constraints/eval_exports/*.musicxml",
        ],
        "current_rule_guided_transformer": [
            "runs/chorale_rule_guided_decoding/eval_exports/*.musicxml",
            "expert_eval/project1/project1_sample*_generated.musicxml",
        ],
        "cih_s2s_transformer": [
            "runs/cih_s2s_smoke/eval_exports/*.musicxml",
            "generated_scores/cih_s2s_smoke/*generated.musicxml",
        ],
    }
    output: dict[str, list[Path]] = {}
    for condition, globs in patterns.items():
        paths: list[Path] = []
        for pattern in globs:
            paths.extend(sorted(root.glob(pattern)))
        unique = []
        seen = set()
        for path in paths:
            resolved = path.resolve()
            if resolved in seen or not path.is_file():
                continue
            seen.add(resolved)
            unique.append(path)
        output[condition] = unique
    return output


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else ["status"]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def protocol_markdown() -> str:
    return """# Expert Evaluation Protocol

This protocol prepares blind human evaluation materials for Project1 SATB harmonization. It is not evidence of completed expert ratings.

## Conditions

The blinded set should include ground truth, vanilla Transformer, current rule-guided Transformer, and CIH-S2S Transformer. If a condition has only smoke-level outputs, mark it as smoke-only and do not use it for formal paper claims.

## Rating Dimensions

Raters score each anonymized score from 1 to 5 for harmonic correctness, voice-leading correctness, seventh-resolution correctness, cadence quality, singability, stylistic consistency, usefulness for composition pedagogy, and overall preference.

## Blindness

The expert-facing packet contains only anonymized IDs. The condition key is stored in `internal_key_do_not_send.csv` and must not be sent to raters.

## Analysis Plan

After at least three completed expert rating forms from distinct raters are returned, compute per-dimension means and paired comparisons where the same source excerpt is rated across conditions. Until then, report the status as `expert evaluation pending`.

## Claim Boundary

Do not write that experts preferred a model, that CIH-S2S is more musical, or that human evaluation is complete until returned forms are validated and summarized.
"""


def render_pdf_if_possible(src: Path, dest: Path) -> tuple[str, str]:
    try:
        from chorale.playback_render import PlaybackRenderSettings, export_pdf_with_musescore

        message = export_pdf_with_musescore(src, dest, PlaybackRenderSettings())
        if not message and dest.is_file():
            return "rendered", ""
        return "pending_renderer_unavailable", message or "PDF output missing"
    except Exception as exc:
        return "pending_renderer_unavailable", f"{type(exc).__name__}: {exc}"


def analysis_script_text() -> str:
    return """from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path


RATING_COLUMNS = [
    "harmonic_correctness_1_to_5",
    "voice_leading_correctness_1_to_5",
    "seventh_resolution_correctness_1_to_5",
    "cadence_quality_1_to_5",
    "singability_1_to_5",
    "stylistic_consistency_1_to_5",
    "usefulness_for_composition_pedagogy_1_to_5",
    "overall_preference_1_to_5",
]


def main() -> None:
    root = Path(__file__).resolve().parent
    rating_path = root / "returned_ratings.csv"
    out_path = root / "expert_rating_summary_pending.json"
    if not rating_path.is_file():
        out_path.write_text(json.dumps({"status": "expert evaluation pending", "reason": "returned_ratings.csv not found"}, indent=2), encoding="utf-8")
        print(out_path)
        return
    with rating_path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    completed = [row for row in rows if any(row.get(col, "") for col in RATING_COLUMNS)]
    if not completed:
        out_path.write_text(json.dumps({"status": "expert evaluation pending", "reason": "no completed rating rows"}, indent=2), encoding="utf-8")
        print(out_path)
        return
    summary = {"status": "completed_template_summary", "completed_rows": len(completed), "metrics": {}}
    for col in RATING_COLUMNS:
        values = []
        for row in completed:
            try:
                values.append(float(row.get(col, "")))
            except ValueError:
                pass
        summary["metrics"][col] = {"n": len(values), "mean": statistics.mean(values) if values else None}
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(out_path)


if __name__ == "__main__":
    main()
"""


def generate_packet(root: str | Path = ROOT, output_dir: str = "expert_eval/project1/sci_blind_protocol_packet", num_per_condition: int = 2, seed: int = 2026, render_pdfs: bool = False) -> dict[str, Any]:
    root = Path(root)
    packet = root / output_dir
    musicxml_dir = packet / "musicxml"
    pdf_dir = packet / "pdf_pairs"
    packet.mkdir(parents=True, exist_ok=True)
    musicxml_dir.mkdir(parents=True, exist_ok=True)
    pdf_dir.mkdir(parents=True, exist_ok=True)

    sources = candidate_sources(root)
    rng = random.Random(seed)
    inventory: list[dict[str, Any]] = []
    for condition, paths in sources.items():
        selected = list(paths)
        rng.shuffle(selected)
        for path in selected[:num_per_condition]:
            score_id = f"S{len(inventory) + 1:03d}"
            dest = musicxml_dir / f"{score_id}.musicxml"
            shutil.copy2(path, dest)
            inventory.append(
                {
                    "score_id": score_id,
                    "condition": condition,
                    "source_path": str(path.relative_to(root)),
                    "expert_musicxml": str(dest.relative_to(root)),
                    "sha256_12": sha12(dest),
                    "evidence_level": "smoke" if "cih_s2s_smoke" in str(path).lower() else "candidate",
                }
            )

    key_path = packet / "internal_key_do_not_send.csv"
    write_rows(key_path, inventory if inventory else [{"status": "no candidates found"}])

    rating_rows = [
        {
            "rater_id": "",
            "score_id": item["score_id"],
            **{column: "" for column in RATING_COLUMNS[2:]},
        }
        for item in inventory
    ]
    write_rows(packet / "rating_form.csv", rating_rows if rating_rows else [{"status": "expert evaluation pending"}])

    pdf_rows = []
    if render_pdfs:
        for item in inventory:
            src = root / item["expert_musicxml"]
            pdf_path = pdf_dir / f"{item['score_id']}.pdf"
            status, note = render_pdf_if_possible(src, pdf_path)
            pdf_rows.append({"score_id": item["score_id"], "pdf_path": str(pdf_path.relative_to(root)), "status": status, "note": note})
    else:
        pdf_rows.append({"score_id": "", "pdf_path": "", "status": "pending_not_requested", "note": "Run with --render-pdfs on a machine with a working MusicXML-to-PDF backend."})
    write_rows(packet / "pdf_pairs_manifest.csv", pdf_rows)

    (root / "expert_eval_protocol.md").write_text(protocol_markdown(), encoding="utf-8")
    (packet / "expert_eval_protocol.md").write_text(protocol_markdown(), encoding="utf-8")
    (packet / "README_FOR_EXPERTS.md").write_text(
        "# Project1 Blind SATB Rating Packet\n\nRate only the anonymized scores listed in `rating_form.csv`. Do not ask for or inspect `internal_key_do_not_send.csv`.\n",
        encoding="utf-8",
    )
    (packet / "analyze_expert_ratings.py").write_text(analysis_script_text(), encoding="utf-8")
    pending = {"status": "expert evaluation pending", "completed_rating_files": 0, "summary": "No returned expert scores have been ingested."}
    (packet / "expert_rating_summary_pending.json").write_text(json.dumps(pending, indent=2), encoding="utf-8")
    manifest = {
        "schema": "project1_expert_eval_packet_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "packet_dir": output_dir,
        "conditions": {key: len(value) for key, value in sources.items()},
        "selected_scores": len(inventory),
        "render_pdfs": render_pdfs,
        "status": "protocol_packet_prepared_pending_completed_ratings",
    }
    (packet / "packet_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Project1 blind expert-evaluation protocol packet.")
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--output-dir", default="expert_eval/project1/sci_blind_protocol_packet")
    parser.add_argument("--num-per-condition", type=int, default=2)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--render-pdfs", action="store_true")
    args = parser.parse_args()
    manifest = generate_packet(args.root, args.output_dir, args.num_per_condition, args.seed, args.render_pdfs)
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
