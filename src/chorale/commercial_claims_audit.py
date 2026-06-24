from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {".md", ".txt", ".tex", ".html", ".htm"}
SAFE_CONTEXT_RE = re.compile(
    r"(?i)\b(do not|must not|not|without|unless|pending|blocked|candidate|not supported|not intended|not yet)\b"
    r"|不是|不得|不能|不可|不可以|未完成|未签|禁止|避免|不代表|不应|候选|待|尚未"
)


@dataclass(frozen=True)
class ClaimPattern:
    label: str
    pattern: re.Pattern[str]
    severity: str
    guidance: str


CLAIM_PATTERNS = [
    ClaimPattern(
        "world_top_music_generation",
        re.compile(r"(?i)world[- ]?(top|class)|state[- ]of[- ]the[- ]art product|世界顶级|全球领先"),
        "violation",
        "Do not claim world-leading product quality without independent benchmark, expert, and market evidence.",
    ),
    ClaimPattern(
        "human_choral_audio_or_vocal_realism",
        re.compile(r"(?i)human vocal realism|real choral recording|真人合唱|真人合唱录音|真人合唱音频|真实合唱音色"),
        "violation",
        "The system renders score-derived listening aids; it must not claim real human choir audio.",
    ),
    ClaimPattern(
        "neural_audio_generation_claim",
        re.compile(r"(?i)audio generation model|neural audio generation|waveform generation|音频生成模型|神经音频生成|波形生成"),
        "violation",
        "Project1 is a score-level SATB harmonization system, not an audio generation model.",
    ),
    ClaimPattern(
        "final_commercial_release_claim",
        re.compile(
            r"(?i)commercial release ready|ready for commercial release|commercially released|approved for commercial distribution"
            r"|已商用发布|商用发布就绪|已可商用发布|已法务审核通过|已专家验证通过|已商业发布"
        ),
        "violation",
        "Do not claim final commercial release until real expert returns and legal/commercial signoff are present.",
    ),
]


def build_claims_audit(root: str | Path = ".", *, package_dir: str | Path = "") -> dict[str, Any]:
    root_path = Path(root)
    target_files = collect_target_files(root_path, Path(package_dir) if package_dir else None)
    findings: list[dict[str, Any]] = []
    scanned_files = 0
    for path in target_files:
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        scanned_files += 1
        findings.extend(scan_file(path, root_path))
    violations = [item for item in findings if item.get("severity") == "violation"]
    warnings = [item for item in findings if item.get("severity") == "warning"]
    return {
        "schema": "project1_commercial_claims_audit_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "all_pass": not violations,
        "status": "pass" if not violations else "failed",
        "scanned_file_count": scanned_files,
        "finding_count": len(findings),
        "violation_count": len(violations),
        "warning_count": len(warnings),
        "findings": findings,
        "method_note": (
            "This audit checks public-facing text for unsupported commercial, audio-generation, and human-vocal claims. "
            "Negated or warning contexts such as 'do not claim' and 'not audio generation' are treated as allowed boundary language."
        ),
    }


def collect_target_files(root: Path, package_dir: Path | None) -> list[Path]:
    roots = [root / "README.md", root / "docs", root / "paper"]
    if package_dir:
        roots.append(root / package_dir if not package_dir.is_absolute() else package_dir)
    else:
        latest = latest_package_dir(root)
        if latest:
            roots.append(latest)
    files: list[Path] = []
    for item in roots:
        if item.is_file():
            files.append(item)
        elif item.is_dir():
            files.extend(path for path in item.rglob("*") if path.is_file() and path.suffix.lower() in TEXT_EXTENSIONS)
    return sorted(set(files))


def latest_package_dir(root: Path) -> Path | None:
    release = root / "results" / "project1_delivery_release_manifest_latest.json"
    if release.is_file():
        data = json.loads(release.read_text(encoding="utf-8-sig"))
        zip_file = Path(str(data.get("zip_file", "")))
        if zip_file.suffix.lower() == ".zip":
            candidate = root / zip_file.with_suffix("")
            if candidate.is_dir():
                return candidate
    deliverables = root / "expert_eval" / "project1" / "deliverables"
    if not deliverables.is_dir():
        return None
    candidates = sorted(
        [path for path in deliverables.iterdir() if path.is_dir() and path.name.startswith("project1_pro_playback_mp3_100_FINAL_")],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def scan_file(path: Path, root: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    except OSError as exc:
        return [
            {
                "severity": "warning",
                "label": "file_read_failed",
                "path": safe_rel(path, root),
                "line": 0,
                "text": "",
                "guidance": f"Could not read public-facing text file: {exc}",
            }
        ]
    findings: list[dict[str, Any]] = []
    for index, line in enumerate(lines):
        window = "\n".join(lines[max(0, index - 8) : min(len(lines), index + 2)])
        for claim in CLAIM_PATTERNS:
            if not claim.pattern.search(line):
                continue
            if SAFE_CONTEXT_RE.search(window):
                continue
            findings.append(
                {
                    "severity": claim.severity,
                    "label": claim.label,
                    "path": safe_rel(path, root),
                    "line": index + 1,
                    "text": line.strip()[:500],
                    "guidance": claim.guidance,
                }
            )
    return findings


def safe_rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return str(path)


def write_outputs(audit: dict[str, Any], out_json: str | Path) -> dict[str, str]:
    out = Path(out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    out_csv = out.with_suffix(".csv")
    findings = audit.get("findings", [])
    with out_csv.open("w", newline="", encoding="utf-8-sig") as handle:
        fieldnames = ["severity", "label", "path", "line", "text", "guidance"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in findings if isinstance(findings, list) else []:
            if isinstance(item, dict):
                writer.writerow({key: item.get(key, "") for key in fieldnames})
    out_md = out.with_suffix(".md")
    out_md.write_text(make_markdown(audit), encoding="utf-8")
    return {"json": str(out), "csv": str(out_csv), "markdown": str(out_md)}


def make_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Project1 Commercial Claims Audit",
        "",
        f"Status: **{audit.get('status')}**",
        f"All pass: **{audit.get('all_pass')}**",
        f"Scanned files: {audit.get('scanned_file_count')}",
        f"Violations: {audit.get('violation_count')}",
        f"Warnings: {audit.get('warning_count')}",
        "",
        str(audit.get("method_note", "")),
        "",
    ]
    findings = audit.get("findings", [])
    if isinstance(findings, list) and findings:
        lines.extend(["## Findings", ""])
        for item in findings:
            if isinstance(item, dict):
                lines.append(
                    f"- {item.get('severity')} `{item.get('label')}` at `{item.get('path')}:{item.get('line')}`: "
                    f"{item.get('text')}"
                )
                lines.append(f"  Guidance: {item.get('guidance')}")
    else:
        lines.append("No unsupported commercial-claim language detected.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit Project1 public-facing text for unsupported commercial claims.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--package-dir", default="")
    parser.add_argument("--out-json", default="results/project1_commercial_claims_audit_latest.json")
    args = parser.parse_args()
    audit = build_claims_audit(args.root, package_dir=args.package_dir)
    outputs = write_outputs(audit, args.out_json)
    print(json.dumps({"summary": {k: v for k, v in audit.items() if k != "findings"}, "outputs": outputs}, indent=2, ensure_ascii=False))
    if not audit["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
