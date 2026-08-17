from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("r", encoding="utf-8-sig") as handle:
            data = json.load(handle)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def manifest_rows(root: Path) -> list[dict[str, Any]]:
    bcfb_subset = read_json(root / "results" / "project1_bcfb_external_subset_latest.json")
    bcfb_intake = read_json(root / "results" / "project1_external_musicxml_intake_latest.json")
    bcfb_summary = read_json(root / "results" / "project1_external_dataset_summary_latest.json")
    cpdl_subset = read_json(root / "results" / "project1_cpdl_musicxml_subset_expanded.json")
    cpdl_intake = read_json(root / "results" / "project1_cpdl_external_musicxml_intake_expanded.json")
    cpdl_summary = read_json(root / "results" / "project1_cpdl_external_dataset_summary_expanded.json")
    return [
        {
            "benchmark_id": "bcfb_bach_related_source_pilot",
            "source": bcfb_subset.get("source_name", "BCFB"),
            "status": "pilot_complete" if bcfb_summary else "pending",
            "selection_criteria": "Selected top-level MusicXML files from a Bach-related source package.",
            "license_filtering_status": bcfb_subset.get("source_license", "source license not confirmed for publication benchmark"),
            "selected_files": bcfb_subset.get("selected_top_level_musicxml_count", ""),
            "parsed_files": bcfb_intake.get("parse_ok_count", ""),
            "encoded_satb_candidates": bcfb_intake.get("encoded_count", ""),
            "split_counts": json.dumps((bcfb_summary.get("dataset", {}) or {}).get("split_counts", {}), sort_keys=True),
            "allowed_claim": "source-chain pilot on Bach-related chorale material",
            "forbidden_claim": "external-repertory robustness or non-Bach generalization",
            "evidence": "results/project1_external_dataset_summary_latest.json",
        },
        {
            "benchmark_id": "cpdl_candidate_subset_pilot",
            "source": cpdl_subset.get("source_name", "CPDL"),
            "status": "pilot_complete" if cpdl_summary else "pending",
            "selection_criteria": "Automatically selected CPDL SATB-category MusicXML/MXL candidates.",
            "license_filtering_status": "candidate-source only; public-domain and copyright filtering require manual curation",
            "selected_files": cpdl_subset.get("selected_mxl_count", cpdl_subset.get("selected_top_level_musicxml_count", "")),
            "parsed_files": cpdl_intake.get("parse_ok_count", ""),
            "encoded_satb_candidates": cpdl_intake.get("encoded_count", ""),
            "split_counts": json.dumps((cpdl_summary.get("dataset", {}) or {}).get("split_counts", {}), sort_keys=True),
            "allowed_claim": "small automatically selected non-Bach source-chain pilot",
            "forbidden_claim": "representative CPDL robustness, expert preference, or license-cleared benchmark",
            "evidence": "results/project1_cpdl_external_dataset_summary_expanded.json",
        },
        {
            "benchmark_id": "curated_public_domain_external_benchmark",
            "source": "CPDL and other public-domain MusicXML sources",
            "status": "protocol_pending_curation",
            "selection_criteria": "Manual public-domain/license screening, SATB candidate detection, duplicate removal, metadata audit, fixed split.",
            "license_filtering_status": "pending",
            "selected_files": "",
            "parsed_files": "",
            "encoded_satb_candidates": "",
            "split_counts": "",
            "allowed_claim": "formal external-source benchmark only after curation and locked split",
            "forbidden_claim": "generalization before benchmark curation is complete",
            "evidence": "external_benchmark_protocol.md",
        },
    ]


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def protocol_markdown() -> str:
    return """# External Benchmark Protocol

This protocol defines how Project1 should turn external MusicXML sources into a formal SATB benchmark. Existing BCFB and CPDL files are pilots unless every step below is completed and logged.

## Source Classes

- BCFB is Bach-related material. It can test source-chain portability, but it must not be described as true external-repertory robustness.
- CPDL and similar repositories can provide non-Bach public-domain candidates only after license, copyright, voicing, duplicate, and metadata filtering.

## Inclusion Criteria

1. Score is available as MusicXML, XML, or MXL.
2. Score is public-domain or has a license that permits research redistribution of derived symbolic features.
3. Score contains four singable SATB parts or can be converted into an unambiguous SATB texture.
4. The tokenizer can encode at least the configured minimum number of grid positions.
5. The score is not duplicated across train, validation, or test splits.

## Exclusion Criteria

1. Copyright or license status is unknown.
2. The file cannot be parsed reproducibly by music21.
3. SATB part detection is ambiguous after manual review.
4. The score is a transcription of a Bach chorale already present in the main music21 split.
5. Tokenization produces excessive padding, missing voices, or unresolved measure-grid errors.

## Required Manifest Fields

Each source item must record source URL, archive identifier, composer, title, license status, parse status, SATB detection status, tokenization status, split assignment, and exclusion reason when excluded.

## Split Protocol

Use a deterministic seed and split only after duplicate removal. Report exact train, validation, and test counts. Keep the split locked before model tuning.

## Evaluation Protocol

Run Rule-only, LSTM, vanilla Transformer, current rule-guided Transformer, and CIH-S2S Transformer when checkpoints exist. Report pitch accuracy, cross entropy where applicable, voice-wise accuracy, rule flags per 100 score positions, MusicXML export success, generation validity, and decoding runtime. Use the same checkpoint-selection rule as the Bach split.

## Claim Boundary

Until this manifest is curated and the split is locked, write only "external-source pilot" or "candidate-source pilot". Do not claim external-corpus robustness, CPDL generalization, expert preference, or state-of-the-art performance.
"""


def run(root: str | Path = ROOT) -> dict[str, str]:
    root = Path(root)
    rows = manifest_rows(root)
    csv_path = root / "results" / "external_benchmark_manifest.csv"
    json_path = root / "results" / "external_benchmark_manifest.json"
    protocol_path = root / "external_benchmark_protocol.md"
    write_csv(csv_path, rows)
    json_path.write_text(
        json.dumps(
            {
                "schema": "project1_external_benchmark_manifest_v1",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "rows": rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    protocol_path.write_text(protocol_markdown(), encoding="utf-8")
    return {
        "manifest_csv": str(csv_path.relative_to(root)),
        "manifest_json": str(json_path.relative_to(root)),
        "protocol_md": str(protocol_path.relative_to(root)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Project1 external-source benchmark manifest and protocol.")
    parser.add_argument("--root", default=str(ROOT))
    args = parser.parse_args()
    print(json.dumps(run(args.root), indent=2))


if __name__ == "__main__":
    main()
