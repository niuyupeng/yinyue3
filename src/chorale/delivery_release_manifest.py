from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


def build_release_manifest(
    zip_file: str | Path,
    *,
    folder_integrity_report: str | Path = "results/project1_delivery_integrity_report_latest.json",
    zip_integrity_report: str | Path = "results/project1_delivery_zip_integrity_report_latest.json",
    commercial_delivery_audit: str | Path = "results/project1_commercial_delivery_audit_latest.json",
) -> dict[str, object]:
    zip_path = Path(zip_file)
    if not zip_path.is_file():
        raise FileNotFoundError(f"ZIP file not found: {zip_path}")
    folder_report = read_json(Path(folder_integrity_report))
    zip_report = read_json(Path(zip_integrity_report))
    delivery_audit = read_json(Path(commercial_delivery_audit))
    return {
        "schema": "project1_delivery_release_manifest_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "zip_file": str(zip_path),
        "zip_name": zip_path.name,
        "zip_size_bytes": zip_path.stat().st_size,
        "zip_sha256": sha256_file(zip_path),
        "zip_regular_file_count": count_zip_files(zip_path),
        "commercial_delivery_score": delivery_audit.get("commercial_delivery_score"),
        "commercial_delivery_all_pass": delivery_audit.get("all_pass"),
        "folder_integrity_all_pass": folder_report.get("all_pass"),
        "folder_integrity_checked_file_count": folder_report.get("checked_file_count"),
        "zip_integrity_all_pass": zip_report.get("all_pass"),
        "zip_integrity_checked_file_count": zip_report.get("checked_file_count"),
        "mp3_count": delivery_audit.get("mp3_count"),
        "midi_count": delivery_audit.get("midi_count"),
        "wav_count": delivery_audit.get("wav_count"),
        "score_count": delivery_audit.get("score_count"),
        "manifest_rows": delivery_audit.get("manifest_rows"),
        "notes": [
            "This release manifest identifies the exact ZIP archive to distribute.",
            "It is an engineering integrity record, not legal advice and not expert evaluation evidence.",
        ],
    }


def verify_release_manifest(manifest_path: str | Path) -> dict[str, object]:
    path = Path(manifest_path)
    if not path.is_file():
        raise FileNotFoundError(f"Release manifest not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    zip_path = Path(str(data.get("zip_file", "")))
    issues: list[str] = []
    if not zip_path.is_file():
        issues.append(f"ZIP file missing: {zip_path}")
    else:
        expected_size = int(data.get("zip_size_bytes", -1) or -1)
        expected_hash = str(data.get("zip_sha256", ""))
        actual_size = zip_path.stat().st_size
        actual_hash = sha256_file(zip_path)
        if actual_size != expected_size:
            issues.append(f"ZIP size changed: {actual_size} != {expected_size}")
        if actual_hash != expected_hash:
            issues.append("ZIP SHA256 changed")
    for key in ["commercial_delivery_all_pass", "folder_integrity_all_pass", "zip_integrity_all_pass"]:
        if data.get(key) is not True:
            issues.append(f"{key} is not true")
    return {
        "all_pass": not issues,
        "status": "pass" if not issues else "failed",
        "manifest": str(path),
        "zip_file": str(zip_path),
        "issues": issues,
    }


def write_release_outputs(manifest: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(manifest), encoding="utf-8")
    out_sha = out_json.with_suffix(".sha256")
    out_sha.write_text(f"{manifest['zip_sha256']}  {manifest['zip_name']}\n", encoding="utf-8")
    return {"json": str(out_json), "markdown": str(out_md), "sha256": str(out_sha)}


def make_markdown(manifest: dict[str, object]) -> str:
    lines = [
        "# Project1 Delivery Release Manifest",
        "",
        f"ZIP: `{manifest.get('zip_name')}`",
        f"Size bytes: {manifest.get('zip_size_bytes')}",
        f"SHA256: `{manifest.get('zip_sha256')}`",
        f"ZIP regular files: {manifest.get('zip_regular_file_count')}",
        "",
        "## Audit Evidence",
        "",
        f"- Commercial delivery score: {manifest.get('commercial_delivery_score')}",
        f"- Commercial delivery all pass: {manifest.get('commercial_delivery_all_pass')}",
        f"- Folder integrity all pass: {manifest.get('folder_integrity_all_pass')}",
        f"- Folder checked files: {manifest.get('folder_integrity_checked_file_count')}",
        f"- ZIP integrity all pass: {manifest.get('zip_integrity_all_pass')}",
        f"- ZIP checked files: {manifest.get('zip_integrity_checked_file_count')}",
        f"- MP3 files: {manifest.get('mp3_count')}",
        f"- MIDI files: {manifest.get('midi_count')}",
        f"- WAV files: {manifest.get('wav_count')}",
        f"- Score count: {manifest.get('score_count')}",
        f"- Manifest rows: {manifest.get('manifest_rows')}",
        "",
        "Send the ZIP together with the `.sha256` line if the recipient wants to verify the archive before extraction.",
        "This record does not replace expert ratings or legal/commercial signoff.",
    ]
    return "\n".join(lines) + "\n"


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_zip_files(path: Path) -> int:
    with zipfile.ZipFile(path) as archive:
        return sum(1 for item in archive.infolist() if not item.is_dir())


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or verify Project1 delivery release ZIP manifests.")
    parser.add_argument("--zip-file")
    parser.add_argument("--out-json", default="results/project1_delivery_release_manifest_latest.json")
    parser.add_argument("--verify-manifest", default="")
    args = parser.parse_args()
    if args.verify_manifest:
        result = verify_release_manifest(args.verify_manifest)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        if not result["all_pass"]:
            raise SystemExit(1)
        return
    if not args.zip_file:
        parser.error("--zip-file is required unless --verify-manifest is used.")
    manifest = build_release_manifest(args.zip_file)
    outputs = write_release_outputs(manifest, args.out_json)
    result = {"manifest": manifest, "outputs": outputs}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
