from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_release_gate_report(
    root: str | Path = ".",
    *,
    min_raters: int = 3,
    min_absolute_rows: int = 1,
    min_paired_rows: int = 1,
) -> dict[str, Any]:
    root_path = Path(root)
    readiness = read_json(root_path / "results" / "project1_commercial_readiness_audit.json")
    acceptance = read_json(root_path / "results" / "project1_commercial_acceptance_report_latest.json")
    release = read_json(root_path / "results" / "project1_delivery_release_manifest_latest.json")
    expert = read_json(root_path / "results" / "project1_expert_eval_summary.json")
    expert_intake = read_json(root_path / "results" / "project1_expert_return_intake_report_latest.json")
    legal = read_json(root_path / "results" / "project1_commercial_legal_signoff.json")

    checks = [
        check_readiness(readiness),
        check_acceptance(acceptance),
        check_release_manifest(root_path, release),
        check_expert_summary(expert, expert_intake, min_raters, min_absolute_rows, min_paired_rows),
        check_legal_signoff(legal, release),
    ]
    blocking = [item for item in checks if not item["passed"]]
    ready = not blocking
    report = {
        "schema": "project1_commercial_release_gate_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commercial_release_ready": ready,
        "release_status": "ready_for_commercial_release" if ready else "blocked",
        "release_score": 100 if ready else int(readiness.get("commercial_readiness_score", 0) or 0),
        "blocking_items": [item["gate"] for item in blocking],
        "checks": checks,
        "next_actions": next_actions(blocking),
        "non_substitutable_evidence_note": (
            "This gate intentionally requires real expert-rating returns and real legal/commercial signoff. "
            "Generated files, smoke tests, and engineering audits cannot substitute for those external decisions."
        ),
    }
    return report


def check_readiness(readiness: dict[str, Any]) -> dict[str, Any]:
    score = readiness.get("commercial_readiness_score")
    passed = readiness.get("all_pass") is True and float(score or 0) >= 100
    status = "pass" if passed else f"commercial readiness is not 100/100: score={score}, all_pass={readiness.get('all_pass')}"
    return {
        "gate": "commercial_readiness_100",
        "passed": passed,
        "status": status,
        "evidence": "results/project1_commercial_readiness_audit.json",
    }


def check_acceptance(acceptance: dict[str, Any]) -> dict[str, Any]:
    passed = (
        acceptance.get("engineering_acceptance") == "pass"
        and acceptance.get("commercial_release") == "ready"
        and acceptance.get("all_commercial_gates_pass") is True
    )
    status = (
        "pass"
        if passed
        else (
            "acceptance report is not commercial-release ready: "
            f"engineering={acceptance.get('engineering_acceptance')}, "
            f"commercial_release={acceptance.get('commercial_release')}, "
            f"all_gates={acceptance.get('all_commercial_gates_pass')}"
        )
    )
    return {
        "gate": "commercial_acceptance_ready",
        "passed": passed,
        "status": status,
        "evidence": "results/project1_commercial_acceptance_report_latest.json",
    }


def check_release_manifest(root: Path, release: dict[str, Any]) -> dict[str, Any]:
    zip_rel = str(release.get("zip_file", ""))
    zip_path = root / zip_rel
    expected_sha = str(release.get("zip_sha256", ""))
    exists = zip_path.is_file()
    actual_sha = sha256_file(zip_path) if exists else ""
    passed = (
        exists
        and bool(expected_sha)
        and actual_sha == expected_sha
        and release.get("commercial_delivery_all_pass") is True
        and release.get("folder_integrity_all_pass") is True
        and release.get("zip_integrity_all_pass") is True
    )
    status = (
        "pass"
        if passed
        else (
            "release manifest or ZIP hash is not final: "
            f"exists={exists}, expected_sha={expected_sha}, actual_sha={actual_sha}, "
            f"delivery={release.get('commercial_delivery_all_pass')}, "
            f"folder_integrity={release.get('folder_integrity_all_pass')}, "
            f"zip_integrity={release.get('zip_integrity_all_pass')}"
        )
    )
    return {
        "gate": "immutable_release_zip",
        "passed": passed,
        "status": status,
        "evidence": "results/project1_delivery_release_manifest_latest.json",
        "zip_file": zip_rel,
        "zip_sha256": expected_sha,
        "computed_zip_sha256": actual_sha,
    }


def check_expert_summary(
    expert: dict[str, Any],
    intake: dict[str, Any],
    min_raters: int,
    min_absolute_rows: int,
    min_paired_rows: int,
) -> dict[str, Any]:
    files = int(expert.get("rating_file_count", 0) or 0)
    absolute_rows = int(expert.get("absolute_completed_rows", 0) or 0)
    paired_rows = int(expert.get("paired_completed_rows", 0) or 0)
    valid_files = int(intake.get("valid_rating_file_count", 0) or 0)
    intake_absolute_rows = int(intake.get("absolute_completed_rows", 0) or 0)
    intake_paired_rows = int(intake.get("paired_completed_rows", 0) or 0)
    passed = (
        expert.get("status") == "completed"
        and files >= min_raters
        and absolute_rows >= min_absolute_rows
        and paired_rows >= min_paired_rows
        and intake.get("status") == "ready_to_summarize"
        and valid_files >= min_raters
        and intake_absolute_rows >= min_absolute_rows
        and intake_paired_rows >= min_paired_rows
    )
    status = (
        "pass"
        if passed
        else (
            "expert evaluation is missing or insufficient: "
            f"status={expert.get('status')}, files={files}/{min_raters}, "
            f"absolute_rows={absolute_rows}/{min_absolute_rows}, paired_rows={paired_rows}/{min_paired_rows}, "
            f"intake_status={intake.get('status')}, valid_files={valid_files}/{min_raters}, "
            f"intake_absolute_rows={intake_absolute_rows}/{min_absolute_rows}, "
            f"intake_paired_rows={intake_paired_rows}/{min_paired_rows}"
        )
    )
    return {
        "gate": "returned_expert_evaluation",
        "passed": passed,
        "status": status,
        "evidence": "results/project1_expert_eval_summary.json; results/project1_expert_return_intake_report_latest.json",
    }


def check_legal_signoff(legal: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    required_checks = legal.get("required_checks", {})
    if not isinstance(required_checks, dict):
        required_checks = {}
    missing_checks = [key for key, value in required_checks.items() if value is not True]
    reviewer_ok = bool(str(legal.get("reviewer_name", "")).strip()) and "TODO" not in str(
        legal.get("reviewer_name", "")
    )
    role_ok = bool(str(legal.get("reviewer_role", "")).strip()) and "TODO" not in str(legal.get("reviewer_role", ""))
    date_ok = bool(str(legal.get("review_date", "")).strip()) and "YYYY" not in str(legal.get("review_date", ""))
    expected_zip = str(release.get("zip_file", "")).replace("\\", "/").strip()
    signed_zip = str(legal.get("delivery_zip", "")).replace("\\", "/").strip()
    expected_sha = str(release.get("zip_sha256", "")).strip()
    signed_sha = str(legal.get("delivery_zip_sha256", "")).strip()
    zip_ok = bool(expected_zip) and signed_zip == expected_zip
    sha_ok = bool(expected_sha) and signed_sha == expected_sha
    passed = (
        legal.get("approved_for_commercial_distribution") is True
        and not missing_checks
        and reviewer_ok
        and role_ok
        and date_ok
        and zip_ok
        and sha_ok
    )
    status = (
        "pass"
        if passed
        else (
            "legal/commercial signoff is incomplete: "
            f"approved={legal.get('approved_for_commercial_distribution')}, "
            f"missing_required_checks={missing_checks}, reviewer_ok={reviewer_ok}, "
            f"role_ok={role_ok}, date_ok={date_ok}, zip_ok={zip_ok}, sha_ok={sha_ok}"
        )
    )
    return {
        "gate": "commercial_legal_signoff",
        "passed": passed,
        "status": status,
        "evidence": "results/project1_commercial_legal_signoff.json",
    }


def next_actions(blocking: list[dict[str, Any]]) -> list[str]:
    actions: list[str] = []
    gates = {str(item.get("gate")) for item in blocking}
    if "returned_expert_evaluation" in gates or "commercial_readiness_100" in gates:
        actions.append(
            "Collect at least three completed expert rating workbooks in expert_eval/project1/returned_ratings, "
            "then run scripts/validate_project1_expert_returns.ps1 and scripts/summarize_project1_expert_ratings.ps1."
        )
    if "commercial_legal_signoff" in gates or "commercial_readiness_100" in gates:
        actions.append(
            "Complete the manual legal/commercial review packet and create results/project1_commercial_legal_signoff.json "
            "only after all required_checks are true."
        )
    if "commercial_acceptance_ready" in gates:
        actions.append(
            "Rerun scripts/audit_project1_commercial_readiness.ps1 and scripts/write_project1_commercial_acceptance_report.ps1 "
            "after expert and legal evidence are present."
        )
    if "immutable_release_zip" in gates:
        actions.append(
            "Regenerate or reverify the delivery release manifest so the ZIP exists and its SHA256 matches."
        )
    return dedupe(actions)


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def write_report(report: dict[str, Any], out_json: str | Path) -> dict[str, str]:
    out_path = Path(out_json)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out_path.with_suffix(".md")
    out_md.write_text(make_markdown(report), encoding="utf-8")
    return {"json": str(out_path), "markdown": str(out_md)}


def make_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Project1 Final Commercial Release Gate",
        "",
        f"Release status: **{report.get('release_status')}**",
        f"Commercial release ready: **{report.get('commercial_release_ready')}**",
        f"Release score: **{report.get('release_score')}/100**",
        "",
        "## Checks",
        "",
        "| Gate | Status | Evidence |",
        "|---|---|---|",
    ]
    for item in report.get("checks", []):
        if not isinstance(item, dict):
            continue
        mark = "PASS" if item.get("passed") else "BLOCKED"
        lines.append(f"| {item.get('gate')} | {mark}: {item.get('status')} | `{item.get('evidence')}` |")
    lines.extend(["", "## Blocking Items", ""])
    blocking = report.get("blocking_items", [])
    if blocking:
        for item in blocking:
            lines.append(f"- {item}")
    else:
        lines.append("No blocking items.")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions", [])
    if actions:
        lines.extend(f"- {item}" for item in actions)
    else:
        lines.append("No next actions required.")
    lines.extend(["", str(report.get("non_substitutable_evidence_note", "")), ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Final no-fabrication commercial release gate for Project1.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-json", default="results/project1_commercial_release_gate_latest.json")
    parser.add_argument("--min-raters", type=int, default=3)
    parser.add_argument("--min-absolute-rows", type=int, default=1)
    parser.add_argument("--min-paired-rows", type=int, default=1)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if the commercial release gate is blocked.")
    args = parser.parse_args()
    report = build_release_gate_report(
        args.root,
        min_raters=args.min_raters,
        min_absolute_rows=args.min_absolute_rows,
        min_paired_rows=args.min_paired_rows,
    )
    outputs = write_report(report, args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))
    if args.strict and not report["commercial_release_ready"]:
        sys.exit(2)


if __name__ == "__main__":
    main()
