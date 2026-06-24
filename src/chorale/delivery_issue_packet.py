from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from chorale.delivery_issue_debugger import debug_delivery_item, latest_package_dir, make_markdown, normalize_rel


def build_issue_evidence_packet(
    score_id: str,
    variant: str,
    *,
    package_dir: str | Path | None = None,
    time_sec: float | None = None,
    window_quarter: float = 1.0,
    out_dir: str | Path = "results/project1_issue_packets",
    packet_name: str | None = None,
) -> dict[str, Any]:
    package = Path(package_dir) if package_dir else latest_package_dir(".")
    report = debug_delivery_item(package, score_id, variant, time_sec=time_sec, window_quarter=window_quarter)
    packet_root = unique_packet_dir(Path(out_dir), packet_name or default_packet_name(score_id, variant, time_sec))
    files_dir = packet_root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    debug_json = packet_root / "debug_report.json"
    debug_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    debug_md = packet_root / "debug_report.md"
    debug_md.write_text(make_markdown(report), encoding="utf-8")

    copied_files: list[dict[str, Any]] = []
    copy_manifest_paths(package, report, files_dir, copied_files)
    write_row_csv(packet_root / "manifest_row.csv", report.get("manifest_row", {}))
    write_row_csv(packet_root / "media_audit_row.csv", report.get("media_audit", {}))
    write_row_csv(packet_root / "conformance_audit_row.csv", report.get("conformance_audit", {}))

    readme_path = packet_root / "README.md"
    readme_path.write_text(make_packet_readme(report, copied_files), encoding="utf-8")

    summary = {
        "schema": "project1_delivery_issue_evidence_packet_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "packet_dir": str(packet_root),
        "score_id": score_id,
        "variant": variant,
        "time_sec": time_sec,
        "source_package_dir": str(package),
        "debug_status": report.get("status"),
        "copied_file_count": len(copied_files),
        "copied_files": copied_files,
        "debug_report_json": str(debug_json),
        "debug_report_markdown": str(debug_md),
    }
    summary_path = packet_root / "ISSUE_EVIDENCE_PACKET_SUMMARY.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    zip_path = make_zip(packet_root)
    summary["zip_file"] = str(zip_path)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def default_packet_name(score_id: str, variant: str, time_sec: float | None) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    time_label = "no_time" if time_sec is None else f"{float(time_sec):.3f}s".replace(".", "p")
    return sanitize_name(f"{score_id}_{variant}_{time_label}_{timestamp}")


def unique_packet_dir(out_dir: Path, name: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    base = out_dir / sanitize_name(name)
    if not base.exists():
        base.mkdir(parents=True)
        return base
    for index in range(2, 1000):
        candidate = out_dir / f"{sanitize_name(name)}_{index:02d}"
        if not candidate.exists():
            candidate.mkdir(parents=True)
            return candidate
    raise FileExistsError(f"Could not create a unique issue packet directory under {out_dir}")


def sanitize_name(value: str) -> str:
    allowed = []
    for char in value.strip():
        if char.isalnum() or char in {"-", "_", "."}:
            allowed.append(char)
        else:
            allowed.append("_")
    return "".join(allowed).strip("._") or "issue_packet"


def copy_manifest_paths(package: Path, report: dict[str, Any], files_dir: Path, copied_files: list[dict[str, Any]]) -> None:
    path_status = report.get("path_status", {})
    if isinstance(path_status, dict):
        for label, info in path_status.items():
            if not isinstance(info, dict) or not info.get("exists"):
                continue
            rel = normalize_rel(str(info.get("path", "")))
            copy_package_file(package, rel, files_dir, str(label), copied_files)
    manifest_row = report.get("manifest_row", {})
    if isinstance(manifest_row, dict):
        for rel in infer_pdf_paths(manifest_row):
            copy_package_file(package, rel, files_dir, "score_pdf", copied_files, required=False)


def infer_pdf_paths(manifest_row: dict[str, Any]) -> list[str]:
    group = str(manifest_row.get("group", "")).strip().lower()
    score_id = str(manifest_row.get("score_id", "")).strip()
    if not score_id:
        return []
    if group == "absolute":
        return [f"absolute_score_pdfs/{score_id}.pdf"]
    if group == "paired":
        return [f"paired_comparison_pdfs/{score_id}.pdf"]
    return [f"absolute_score_pdfs/{score_id}.pdf", f"paired_comparison_pdfs/{score_id}.pdf"]


def copy_package_file(
    package: Path,
    rel_path: str,
    files_dir: Path,
    label: str,
    copied_files: list[dict[str, Any]],
    *,
    required: bool = True,
) -> None:
    if not rel_path:
        if required:
            copied_files.append({"label": label, "source": rel_path, "copied": False, "reason": "empty path"})
        return
    source = safe_package_path(package, rel_path)
    if not source.is_file():
        if required:
            copied_files.append({"label": label, "source": rel_path, "copied": False, "reason": "missing"})
        return
    suffix = source.suffix
    destination = files_dir / f"{sanitize_name(label)}__{sanitize_name(source.stem)}{suffix}"
    shutil.copy2(source, destination)
    copied_files.append(
        {
            "label": label,
            "source": rel_path,
            "copied": True,
            "destination": str(destination),
            "size_bytes": destination.stat().st_size,
        }
    )


def safe_package_path(package: Path, rel_path: str) -> Path:
    package_resolved = package.resolve()
    candidate = (package / normalize_rel(rel_path)).resolve()
    try:
        candidate.relative_to(package_resolved)
    except ValueError as exc:
        raise ValueError(f"Manifest path escapes package directory: {rel_path}") from exc
    return candidate


def write_row_csv(path: Path, row: object) -> None:
    if not isinstance(row, dict) or not row:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = [str(key) for key in row.keys()]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow({key: row.get(key, "") for key in fieldnames})


def make_packet_readme(report: dict[str, Any], copied_files: list[dict[str, Any]]) -> str:
    timepoint = report.get("timepoint_diagnostic", {})
    lines = [
        "# Project1 Issue Evidence Packet",
        "",
        f"Score ID: `{report.get('score_id')}`",
        f"Variant: `{report.get('variant')}`",
        f"Automatic status: `{report.get('status')}`",
        "",
        "## What This Packet Contains",
        "",
        "- `debug_report.json` and `debug_report.md`: item-level diagnosis.",
        "- `manifest_row.csv`: the delivery manifest row.",
        "- `media_audit_row.csv`: MP3/MIDI media audit row.",
        "- `conformance_audit_row.csv`: score-playback conformance row.",
        "- `files/`: copied PDF, MusicXML, MIDI, and MP3 evidence when available.",
        "",
    ]
    if isinstance(timepoint, dict) and timepoint:
        lines.extend(
            [
                "## Timepoint",
                "",
                f"- time_sec: `{timepoint.get('time_sec')}`",
                f"- estimated_measure: `{timepoint.get('estimated_measure')}`",
                f"- estimated_beat: `{timepoint.get('estimated_beat')}`",
                f"- measure_relative_offset_quarter: `{timepoint.get('measure_relative_offset_quarter')}`",
                f"- measure_duration_quarter: `{timepoint.get('measure_duration_quarter')}`",
                "",
            ]
        )
    lines.extend(["## Copied Files", ""])
    for item in copied_files:
        status = "copied" if item.get("copied") else f"missing: {item.get('reason')}"
        lines.append(f"- {item.get('label')}: {status} `{item.get('source')}`")
    lines.extend(
        [
            "",
            "## Use",
            "",
            "Open the PDF and source/render MusicXML, then compare them with the MP3/MIDI files and the debug report.",
            "This packet is for engineering triage and does not replace expert musical judgment.",
            "",
        ]
    )
    return "\n".join(lines)


def make_zip(packet_dir: Path) -> Path:
    zip_path = packet_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(packet_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(packet_dir.parent))
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Project1 issue evidence packet for one score/variant.")
    parser.add_argument("--package-dir", default="")
    parser.add_argument("--score-id", required=True)
    parser.add_argument("--variant", required=True)
    parser.add_argument("--time-sec", type=float, default=None)
    parser.add_argument("--window-quarter", type=float, default=1.0)
    parser.add_argument("--out-dir", default="results/project1_issue_packets")
    parser.add_argument("--packet-name", default="")
    args = parser.parse_args()
    package = Path(args.package_dir) if args.package_dir else None
    summary = build_issue_evidence_packet(
        args.score_id,
        args.variant,
        package_dir=package,
        time_sec=args.time_sec,
        window_quarter=args.window_quarter,
        out_dir=args.out_dir,
        packet_name=args.packet_name or None,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
