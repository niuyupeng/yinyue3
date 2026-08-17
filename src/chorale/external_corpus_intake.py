from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from music21 import converter, stream

from chorale.data.score_tokenizer import ScoreTokenizer, extract_satb_parts


MUSICXML_PATTERNS = ("*.musicxml", "*.xml", "*.mxl")


def inspect_external_musicxml_corpus(
    folder: str | Path,
    *,
    max_files: int = 200,
    min_encoded_scores: int = 20,
    grid_quarter_length: float = 0.25,
    min_midi: int = 36,
    max_midi: int = 84,
    max_seq_len: int = 256,
) -> dict[str, Any]:
    folder_path = Path(folder)
    tokenizer = ScoreTokenizer(
        grid_quarter_length=grid_quarter_length,
        min_midi=min_midi,
        max_midi=max_midi,
        max_seq_len=max_seq_len,
    )
    files = list_musicxml_files(folder_path)[: max(0, int(max_files))]
    records = [inspect_score(path, folder_path, tokenizer) for path in files]
    parse_ok_count = sum(1 for item in records if item["parse_ok"])
    encoded_count = sum(1 for item in records if item["encoded_ok"])
    satb_candidate_count = sum(1 for item in records if item["satb_candidate"])
    intake_ready = folder_path.is_dir() and encoded_count >= int(min_encoded_scores)
    issues: list[str] = []
    if not folder_path.is_dir():
        issues.append(f"external MusicXML folder missing: {folder_path}")
    if not files:
        issues.append("no MusicXML, XML, or MXL files found")
    if encoded_count < int(min_encoded_scores):
        issues.append(f"encoded SATB score count {encoded_count} is below required minimum {min_encoded_scores}")
    return {
        "schema": "project1_external_musicxml_intake_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "folder": str(folder_path),
        "max_files": int(max_files),
        "min_encoded_scores": int(min_encoded_scores),
        "intake_ready": intake_ready,
        "issues": issues,
        "file_count_scanned": len(files),
        "parse_ok_count": parse_ok_count,
        "satb_candidate_count": satb_candidate_count,
        "encoded_count": encoded_count,
        "records": records,
        "notes": [
            "This intake audit checks whether a folder of external MusicXML-like files can enter the SATB tokenization pipeline.",
            "It is not a trained external-corpus experiment and should not be cited as external-corpus robustness evidence.",
            "If this audit passes, create a dedicated external dataset config and run model evaluation before adding manuscript claims.",
        ],
    }


def list_musicxml_files(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    files: list[Path] = []
    for pattern in MUSICXML_PATTERNS:
        files.extend(path for path in folder.rglob(pattern) if path.is_file())
    return sorted(set(files), key=lambda path: path.as_posix().lower())


def inspect_score(path: Path, root: Path, tokenizer: ScoreTokenizer) -> dict[str, Any]:
    relative = safe_relative(path, root)
    record: dict[str, Any] = {
        "path": relative,
        "parse_ok": False,
        "part_count": 0,
        "part_names": [],
        "selected_part_names": [],
        "note_count": 0,
        "duration_quarter_length": 0.0,
        "satb_candidate": False,
        "encoded_ok": False,
        "encoded_length": 0,
        "error": "",
    }
    try:
        parsed = converter.parse(str(path))
        score = parsed if isinstance(parsed, stream.Score) else wrap_as_score(parsed)
        parts = list(score.parts)
        part_names = [str(part.partName or part.partAbbreviation or part.id or "") for part in parts]
        note_count = sum(1 for part in parts for _ in part.flatten().notes)
        duration = max((float(part.duration.quarterLength) for part in parts), default=0.0)
        record.update(
            {
                "parse_ok": True,
                "part_count": len(parts),
                "part_names": part_names,
                "note_count": int(note_count),
                "duration_quarter_length": float(duration),
            }
        )
        try:
            selected_parts = extract_satb_parts(score)
            selected_part_names = [
                str(part.partName or part.partAbbreviation or part.id or "") for part in selected_parts
            ]
            record.update(
                {
                    "selected_part_names": selected_part_names,
                    "satb_candidate": len(selected_parts) == 4 and note_count > 0,
                }
            )
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
        try:
            encoded = tokenizer.encode_score(score, name=path.stem)
            record.update({"encoded_ok": True, "encoded_length": int(encoded["length"]), "error": ""})
        except Exception as exc:
            if not record["error"]:
                record["error"] = f"{type(exc).__name__}: {exc}"
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def wrap_as_score(parsed: stream.Stream) -> stream.Score:
    if isinstance(parsed, stream.Part):
        score = stream.Score()
        score.insert(0, parsed)
        return score
    score = stream.Score()
    part = stream.Part()
    for element in parsed.flatten().notesAndRests:
        part.insert(float(element.offset), element)
    score.insert(0, part)
    return score


def safe_relative(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def write_outputs(data: dict[str, Any], out_json: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    out_json.with_suffix(".md").write_text(make_markdown(data), encoding="utf-8")
    out_json.with_suffix(".csv").write_text(make_csv(data), encoding="utf-8")


def make_markdown(data: dict[str, Any]) -> str:
    lines = [
        "# Project1 External MusicXML Corpus Intake Audit",
        "",
        f"Folder: `{data.get('folder')}`",
        f"Intake status: {'PASS' if data.get('intake_ready') else 'PENDING/BLOCKED'}",
        f"Scanned files: {data.get('file_count_scanned')}",
        f"Parse OK: {data.get('parse_ok_count')}",
        f"SATB candidates: {data.get('satb_candidate_count')}",
        f"Encoded SATB scores: {data.get('encoded_count')}",
        "",
        "## Issues",
        "",
    ]
    issues = data.get("issues", [])
    if issues:
        lines.extend(f"- {issue}" for issue in issues)
    else:
        lines.append("No intake issues detected.")
    lines.extend(["", "## Records", "", "| Path | Parse | Parts | Notes | Encoded | Error |", "|---|---:|---:|---:|---:|---|"])
    for record in data.get("records", [])[:100]:
        if not isinstance(record, dict):
            continue
        error = str(record.get("error", "")).replace("|", "/")
        lines.append(
            f"| `{record.get('path')}` | {record.get('parse_ok')} | {record.get('part_count')} | "
            f"{record.get('note_count')} | {record.get('encoded_ok')} | {error} |"
        )
    return "\n".join(lines) + "\n"


def make_csv(data: dict[str, Any]) -> str:
    fieldnames = [
        "path",
        "parse_ok",
        "part_count",
        "selected_part_names",
        "note_count",
        "duration_quarter_length",
        "satb_candidate",
        "encoded_ok",
        "encoded_length",
        "error",
    ]
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for record in data.get("records", []):
        if isinstance(record, dict):
            writer.writerow({name: record.get(name, "") for name in fieldnames})
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit an external MusicXML folder for SATB corpus intake.")
    parser.add_argument("--folder", required=True)
    parser.add_argument("--out-json", default="results/project1_external_musicxml_intake_latest.json")
    parser.add_argument("--max-files", type=int, default=200)
    parser.add_argument("--min-encoded-scores", type=int, default=20)
    parser.add_argument("--grid-quarter-length", type=float, default=0.25)
    parser.add_argument("--min-midi", type=int, default=36)
    parser.add_argument("--max-midi", type=int, default=84)
    parser.add_argument("--max-seq-len", type=int, default=256)
    args = parser.parse_args()
    data = inspect_external_musicxml_corpus(
        args.folder,
        max_files=args.max_files,
        min_encoded_scores=args.min_encoded_scores,
        grid_quarter_length=args.grid_quarter_length,
        min_midi=args.min_midi,
        max_midi=args.max_midi,
        max_seq_len=args.max_seq_len,
    )
    write_outputs(data, Path(args.out_json))
    print(json.dumps(data, indent=2, ensure_ascii=True))
    if not data["intake_ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
