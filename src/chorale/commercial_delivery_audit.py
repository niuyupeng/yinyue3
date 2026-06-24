from __future__ import annotations

import argparse
import csv
import io
import json
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


REQUIRED_VARIANTS = {
    "full_choir",
    "piano_reference",
    "stem_soprano",
    "stem_alto",
    "stem_tenor",
    "stem_bass",
}
REQUIRED_TOP_LEVEL_FILES = {
    "score_audio_player.html",
    "COMMERCIAL_PLAYBACK_README_CN.md",
    "DELIVERY_README_CN.md",
    "DELIVERY_FILE_MANIFEST.json",
    "DELIVERY_FILE_MANIFEST.sha256",
    "DELIVERY_MEDIA_AUDIT.csv",
    "DELIVERY_MEDIA_AUDIT.json",
    "DELIVERY_MEDIA_AUDIT.md",
    "DELIVERY_CONFORMANCE_AUDIT.csv",
    "DELIVERY_CONFORMANCE_AUDIT.json",
    "DELIVERY_CONFORMANCE_AUDIT.md",
    "VERIFY_DELIVERY_INTEGRITY.ps1",
    "VERIFY_DELIVERY_INTEGRITY_README_CN.md",
    "README_FOR_EXPERTS.md",
    "SCORING_RUBRIC.md",
    "START_HERE_CN.html",
    "START_HERE_CN.md",
    "OPEN_PROJECT1_REVIEW_PACKAGE.ps1",
    "PROJECT1_PACKAGE_SELF_TEST.ps1",
    "PROJECT1_PACKAGE_SELF_TEST_README_CN.md",
    "REVIEW_ISSUE_REPORT_TEMPLATE.csv",
    "REVIEW_ISSUE_REPORT_GUIDE_CN.md",
    "THIRD_PARTY_PLAYBACK_NOTICES.md",
}
REQUIRED_AUDIO_FILES = {
    "audio_pro/pro_playback_manifest.csv",
    "audio_pro/pro_playback_summary.json",
    "audio_pro/commercial_qc_report.csv",
    "audio_pro/commercial_qc_summary.json",
    "audio_pro/COMMERCIAL_QC_REPORT.md",
}
REQUIRED_THIRD_PARTY_FILES = {
    "third_party/MuseScore_General_License.md",
    "third_party/MuseScore_General_Readme.md",
}
REQUIRED_FORM_FILES = {
    "forms/project1_expert_rating_forms_CN.xlsx",
}


class PackageReader(Protocol):
    def exists(self, path: str) -> bool: ...

    def read_text(self, path: str) -> str: ...

    def list_files(self) -> list[str]: ...


@dataclass
class DirReader:
    root: Path

    def exists(self, path: str) -> bool:
        return (self.root / path).is_file()

    def read_text(self, path: str) -> str:
        return (self.root / path).read_text(encoding="utf-8-sig")

    def list_files(self) -> list[str]:
        files: list[str] = []
        for item in self.root.rglob("*"):
            if item.is_file():
                files.append(item.relative_to(self.root).as_posix())
        return files


@dataclass
class ZipReader:
    zip_path: Path

    def __post_init__(self) -> None:
        with zipfile.ZipFile(self.zip_path) as archive:
            names = [item.filename.replace("\\", "/") for item in archive.infolist() if not item.is_dir()]
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        prefix = ""
        if len(roots) == 1 and all(name.startswith(next(iter(roots)) + "/") for name in names):
            prefix = next(iter(roots)) + "/"
        self._prefix = prefix
        self._names = {self._strip_prefix(name) for name in names}

    def _strip_prefix(self, name: str) -> str:
        return name[len(self._prefix) :] if self._prefix and name.startswith(self._prefix) else name

    def _archive_name(self, path: str) -> str:
        return self._prefix + path.replace("\\", "/")

    def exists(self, path: str) -> bool:
        return path.replace("\\", "/") in self._names

    def read_text(self, path: str) -> str:
        with zipfile.ZipFile(self.zip_path) as archive:
            data = archive.read(self._archive_name(path))
        return data.decode("utf-8-sig")

    def list_files(self) -> list[str]:
        return sorted(self._names)


def audit_package(
    package_dir: str | Path | None = None,
    zip_file: str | Path | None = None,
    *,
    mode: str = "mp3_only",
) -> dict[str, object]:
    if bool(package_dir) == bool(zip_file):
        raise ValueError("Provide exactly one of package_dir or zip_file.")
    if mode not in {"mp3_only", "master"}:
        raise ValueError("mode must be 'mp3_only' or 'master'.")
    reader: PackageReader = DirReader(Path(package_dir)) if package_dir else ZipReader(Path(zip_file))  # type: ignore[arg-type]
    return audit_reader(reader, mode=mode)


def audit_reader(reader: PackageReader, *, mode: str) -> dict[str, object]:
    files = reader.list_files()
    file_set = set(files)
    issues: list[str] = []

    for path in sorted(REQUIRED_TOP_LEVEL_FILES | REQUIRED_AUDIO_FILES | REQUIRED_THIRD_PARTY_FILES | REQUIRED_FORM_FILES):
        if path not in file_set:
            issues.append(f"missing required file: {path}")

    manifest_rows = read_csv(reader, "audio_pro/pro_playback_manifest.csv", issues)
    qc_summary = read_json(reader, "audio_pro/commercial_qc_summary.json", issues)
    playback_summary = read_json(reader, "audio_pro/pro_playback_summary.json", issues)

    counts = count_files(files)
    expected_entry_count = 240
    if len(manifest_rows) != expected_entry_count:
        issues.append(f"manifest row count is {len(manifest_rows)}, expected {expected_entry_count}")

    validate_qc_summary(qc_summary, issues, expected_entry_count)
    validate_playback_summary(playback_summary, issues, expected_entry_count)
    validate_manifest(reader, manifest_rows, issues, mode=mode)
    validate_html(reader, issues)

    if mode == "mp3_only":
        if counts["wav"] != 0:
            issues.append(f"mp3_only package contains {counts['wav']} WAV files")
        nonempty_wav_refs = sum(1 for row in manifest_rows if row.get("wav"))
        if nonempty_wav_refs:
            issues.append(f"mp3_only manifest contains {nonempty_wav_refs} nonempty WAV references")
    else:
        if counts["wav"] != expected_entry_count:
            issues.append(f"master package has {counts['wav']} WAV files, expected {expected_entry_count}")

    if counts["mp3"] != expected_entry_count:
        issues.append(f"package has {counts['mp3']} MP3 files, expected {expected_entry_count}")
    if counts["mid"] != expected_entry_count:
        issues.append(f"package has {counts['mid']} MIDI files, expected {expected_entry_count}")

    score_groups = {(row.get("group", ""), row.get("score_id", "")) for row in manifest_rows}
    summary = {
        "commercial_delivery_score": 100 if not issues else max(0, 100 - len(issues) * 5),
        "all_pass": not issues,
        "mode": mode,
        "file_count": len(files),
        "mp3_count": counts["mp3"],
        "wav_count": counts["wav"],
        "midi_count": counts["mid"],
        "manifest_rows": len(manifest_rows),
        "score_count": len(score_groups),
        "issues": issues,
    }
    return summary


def read_csv(reader: PackageReader, path: str, issues: list[str]) -> list[dict[str, str]]:
    if not reader.exists(path):
        return []
    try:
        return list(csv.DictReader(io.StringIO(reader.read_text(path))))
    except Exception as exc:  # pragma: no cover - defensive report path
        issues.append(f"could not parse CSV {path}: {exc}")
        return []


def read_json(reader: PackageReader, path: str, issues: list[str]) -> dict[str, object]:
    if not reader.exists(path):
        return {}
    try:
        value = json.loads(reader.read_text(path))
        return value if isinstance(value, dict) else {}
    except Exception as exc:  # pragma: no cover - defensive report path
        issues.append(f"could not parse JSON {path}: {exc}")
        return {}


def count_files(files: list[str]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for path in files:
        suffix = Path(path).suffix.lower().lstrip(".")
        if suffix:
            counts[suffix] += 1
    return counts


def validate_qc_summary(summary: dict[str, object], issues: list[str], expected_entry_count: int) -> None:
    expected = {
        "qc_score": 100,
        "entry_count": expected_entry_count,
        "pass_count": expected_entry_count,
        "fail_count": 0,
        "all_pass": True,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            issues.append(f"commercial QC summary {key}={summary.get(key)!r}, expected {value!r}")


def validate_playback_summary(summary: dict[str, object], issues: list[str], expected_entry_count: int) -> None:
    expected = {
        "entry_count": expected_entry_count,
        "ok_count": expected_entry_count,
        "failed_count": 0,
        "all_ok": True,
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            issues.append(f"playback summary {key}={summary.get(key)!r}, expected {value!r}")


def validate_manifest(reader: PackageReader, rows: list[dict[str, str]], issues: list[str], *, mode: str) -> None:
    seen_by_score: dict[tuple[str, str], set[str]] = defaultdict(set)
    missing_refs: list[str] = []
    for row in rows:
        group = row.get("group", "")
        score_id = row.get("score_id", "")
        variant = row.get("variant", "")
        seen_by_score[(group, score_id)].add(variant)
        required_refs = ["mp3", "midi", "source_musicxml", "render_musicxml"]
        if mode == "master":
            required_refs.append("wav")
        for key in required_refs:
            rel = row.get(key, "").replace("\\", "/")
            if not rel:
                missing_refs.append(f"{group}/{score_id}/{variant}: empty {key}")
            elif not reader.exists(rel):
                missing_refs.append(f"{group}/{score_id}/{variant}: missing {key} -> {rel}")
        if row.get("status") != "ok":
            issues.append(f"{group}/{score_id}/{variant} manifest status is {row.get('status')!r}, expected 'ok'")
    if missing_refs:
        issues.append("missing manifest references: " + "; ".join(missing_refs[:10]))
    for (group, score_id), variants in sorted(seen_by_score.items()):
        missing = REQUIRED_VARIANTS - variants
        extra = variants - REQUIRED_VARIANTS
        if missing:
            issues.append(f"{group}/{score_id} missing variants: {','.join(sorted(missing))}")
        if extra:
            issues.append(f"{group}/{score_id} has unexpected variants: {','.join(sorted(extra))}")


def validate_html(reader: PackageReader, issues: list[str]) -> None:
    if not reader.exists("score_audio_player.html"):
        return
    html = reader.read_text("score_audio_player.html")
    required_snippets = ["QC score: 100/100", "Full choir", "Piano reference", "Soprano stem"]
    for snippet in required_snippets:
        if snippet not in html:
            issues.append(f"score_audio_player.html missing snippet: {snippet}")


def write_audit_outputs(summary: dict[str, object], out_json: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(summary), encoding="utf-8")


def make_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Commercial Delivery Audit",
        "",
        f"Score: {summary['commercial_delivery_score']}/100",
        f"All pass: {summary['all_pass']}",
        f"Mode: {summary['mode']}",
        f"Files: {summary['file_count']}",
        f"Scores: {summary['score_count']}",
        f"Manifest rows: {summary['manifest_rows']}",
        f"MP3 files: {summary['mp3_count']}",
        f"WAV files: {summary['wav_count']}",
        f"MIDI files: {summary['midi_count']}",
        "",
    ]
    issues = summary.get("issues", [])
    if issues:
        lines.extend(["## Issues", ""])
        for issue in issues:
            lines.append(f"- {issue}")
    else:
        lines.append("No delivery-blocking issues detected.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit a Project1 commercial delivery folder or ZIP.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--package-dir")
    src.add_argument("--zip-file")
    parser.add_argument("--mode", choices=["mp3_only", "master"], default="mp3_only")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()
    summary = audit_package(args.package_dir, args.zip_file, mode=args.mode)
    if args.out_json:
        write_audit_outputs(summary, Path(args.out_json))
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
