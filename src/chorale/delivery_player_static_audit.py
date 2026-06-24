from __future__ import annotations

import argparse
import csv
import json
import re
from datetime import datetime, timezone
from pathlib import Path


BAD_TEXT_PATTERNS = [
    "�",
    "€?",
    "銆",
    "锛",
    "鍥",
    "闊",
    "璋",
    "铻",
    "鍜",
    "浼犵",
    "绁炵",
    "涔愯",
    "涓撳",
    "浜や",
    "瀹㈡",
    "鎵撳",
    "濉",
    "乄AV",
]
TEXT_EXTENSIONS = {".html", ".md", ".txt", ".csv"}


def audit_player_package(package_dir: str | Path) -> dict[str, object]:
    package = Path(package_dir)
    html_path = package / "score_audio_player.html"
    manifest_path = package / "audio_pro" / "pro_playback_manifest.csv"
    issues: list[str] = []
    missing_refs: list[str] = []

    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")
    if not html_path.is_file():
        issues.append(f"missing player HTML: {html_path}")
        html_text = ""
        embedded_scores: list[dict[str, object]] = []
    else:
        html_text = html_path.read_text(encoding="utf-8-sig", errors="replace")
        embedded_scores = parse_embedded_scores(html_text)
    if not manifest_path.is_file():
        issues.append(f"missing playback manifest: {manifest_path}")
        manifest_rows: list[dict[str, str]] = []
    else:
        manifest_rows = read_manifest(manifest_path)

    if html_text:
        if "<title>Project1 SATB 乐谱-音频审阅台</title>" not in html_text:
            issues.append("player title is missing or malformed")
        if "const scores =" not in html_text:
            issues.append("player score JSON is missing")
        missing_refs.extend(check_embedded_score_refs(package, embedded_scores))

    missing_refs.extend(check_manifest_refs(package, manifest_rows))
    bad_text_files = scan_bad_text(package)
    score_count = len({(row.get("group", ""), row.get("score_id", "")) for row in manifest_rows})
    variant_counts = count_by_key(manifest_rows, "variant")
    expected_variants_ok = bool(variant_counts) and all(int(variant_counts.get(name, 0)) == score_count for name in [
        "full_choir",
        "piano_reference",
        "stem_soprano",
        "stem_alto",
        "stem_tenor",
        "stem_bass",
    ])
    if score_count < 40:
        issues.append(f"expected at least 40 score entries, found {score_count}")
    if len(manifest_rows) < score_count * 6:
        issues.append(f"expected at least six manifest rows per score, found {len(manifest_rows)} rows")
    if not expected_variants_ok:
        issues.append(f"variant counts are incomplete: {variant_counts}")
    if embedded_scores and len(embedded_scores) != score_count:
        issues.append(f"embedded score count {len(embedded_scores)} does not match manifest score count {score_count}")

    all_pass = not issues and not missing_refs and not bad_text_files
    return {
        "schema": "project1_delivery_player_static_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_dir": str(package),
        "html": str(html_path),
        "manifest": str(manifest_path),
        "status": "pass" if all_pass else "failed",
        "all_pass": all_pass,
        "score_count": score_count,
        "manifest_rows": len(manifest_rows),
        "embedded_score_count": len(embedded_scores),
        "variant_counts": variant_counts,
        "missing_references": missing_refs[:100],
        "missing_reference_count": len(missing_refs),
        "bad_text_files": bad_text_files[:100],
        "bad_text_file_count": len(bad_text_files),
        "issues": issues,
    }


def parse_embedded_scores(html_text: str) -> list[dict[str, object]]:
    match = re.search(r"const\s+scores\s*=\s*(\[.*?\]);\s*const\s+variantOrder", html_text, flags=re.DOTALL)
    if not match:
        return []
    try:
        value = json.loads(match.group(1))
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def check_embedded_score_refs(package: Path, scores: list[dict[str, object]]) -> list[str]:
    missing: list[str] = []
    for score in scores:
        if not isinstance(score, dict):
            continue
        score_id = str(score.get("score_id", "UNKNOWN"))
        for key in ["pdf", "source_musicxml", "render_musicxml"]:
            rel = str(score.get(key, "") or "")
            if rel and not (package / rel).is_file():
                missing.append(f"{score_id}: {key} -> {rel}")
        variants = score.get("variants", {})
        if isinstance(variants, dict):
            for variant, item in variants.items():
                if not isinstance(item, dict):
                    continue
                for key in ["mp3", "midi"]:
                    rel = str(item.get(key, "") or "")
                    if rel and not (package / rel).is_file():
                        missing.append(f"{score_id}/{variant}: {key} -> {rel}")
    return missing


def check_manifest_refs(package: Path, rows: list[dict[str, str]]) -> list[str]:
    missing: list[str] = []
    for row in rows:
        score_id = row.get("score_id", "UNKNOWN")
        variant = row.get("variant", "UNKNOWN")
        for key in ["source_musicxml", "render_musicxml", "midi", "mp3"]:
            rel = row.get(key, "") or ""
            if rel and not (package / rel).is_file():
                missing.append(f"{score_id}/{variant}: {key} -> {rel}")
    return missing


def scan_bad_text(package: Path) -> list[dict[str, object]]:
    bad: list[dict[str, object]] = []
    for path in package.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        rel = path.relative_to(package).as_posix()
        if rel.startswith("render_xml/") or rel.startswith("absolute_score_musicxml/") or rel.startswith("paired_comparison_musicxml/"):
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        found = [pattern for pattern in BAD_TEXT_PATTERNS if pattern in text]
        if found:
            bad.append({"file": rel, "patterns": found[:10]})
    return bad


def count_by_key(rows: list[dict[str, str]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = row.get(key, "")
        counts[value] = counts.get(value, 0) + 1
    return counts


def write_audit_outputs(report: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out = Path(out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md = out.with_suffix(".md")
    md.write_text(make_markdown(report), encoding="utf-8")
    return {"json": str(out), "markdown": str(md)}


def make_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Project1 Delivery Player Static Audit",
        "",
        f"Status: **{report.get('status')}**",
        f"Package: `{report.get('package_dir')}`",
        f"Scores: {report.get('score_count')}",
        f"Manifest rows: {report.get('manifest_rows')}",
        f"Missing references: {report.get('missing_reference_count')}",
        f"Bad text files: {report.get('bad_text_file_count')}",
        "",
    ]
    issues = report.get("issues", [])
    if isinstance(issues, list) and issues:
        lines.append("## Issues")
        lines.extend(f"- {issue}" for issue in issues)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Project1 offline player package references and text quality.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--out-json", default="results/project1_delivery_player_static_audit_latest.json")
    args = parser.parse_args()
    report = audit_player_package(args.package_dir)
    outputs = write_audit_outputs(report, args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))
    if not report["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
