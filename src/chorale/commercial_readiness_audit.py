from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GateResult:
    gate: str
    weight: int
    passed: bool
    status: str
    evidence: str
    blocking: bool = False


def run_readiness_audit(root: str | Path = ".") -> dict[str, object]:
    root_path = Path(root)
    gates = [
        audit_logged_experiments(root_path),
        audit_delivery_package(root_path),
        audit_delivery_integrity(root_path),
        audit_release_manifest(root_path),
        audit_score_audio_traceability(root_path),
        audit_delivery_conformance(root_path),
        audit_playback_license(root_path),
        audit_browser_player(root_path),
        audit_recipient_usability(root_path),
        audit_expert_evaluation(root_path),
        audit_paper_compile(root_path),
        audit_rating_workflow(root_path),
        audit_review_issue_workflow(root_path),
        audit_issue_evidence_packet_workflow(root_path),
        audit_legal_review_packet(root_path),
        audit_legal_signoff(root_path),
    ]
    achieved = sum(gate.weight for gate in gates if gate.passed)
    total = sum(gate.weight for gate in gates)
    score = round(100 * achieved / total, 2) if total else 0.0
    blocking = [gate for gate in gates if gate.blocking and not gate.passed]
    summary = {
        "commercial_readiness_score": score,
        "achieved_weight": achieved,
        "total_weight": total,
        "all_pass": not blocking and all(gate.passed for gate in gates),
        "status": "commercial release ready" if not blocking and all(gate.passed for gate in gates) else "not yet commercial release ready",
        "blocking_items": [gate.gate for gate in blocking],
        "gates": [gate.__dict__ for gate in gates],
    }
    return summary


def audit_logged_experiments(root: Path) -> GateResult:
    path = root / "results" / "project1_metrics.csv"
    required = {"lstm", "transformer", "proposed", "masked", "soprano"}
    if not path.is_file():
        return gate("logged_full_experiments", 10, False, "missing", str(path), True)
    rows = read_csv(path)
    joined = " ".join(row.get("model", "") + " " + row.get("task", "") for row in rows).lower()
    missing = sorted(key for key in required if key not in joined)
    passed = not missing and any("smoke" not in row.get("model", "").lower() for row in rows)
    status = "pass" if passed else f"missing experiment categories: {missing}"
    return gate("logged_full_experiments", 10, passed, status, str(path), not passed)


def audit_delivery_package(root: Path) -> GateResult:
    path = root / "results" / "project1_commercial_delivery_audit_latest.json"
    data = read_json(path)
    passed = bool(data.get("all_pass")) and data.get("commercial_delivery_score") == 100
    status = "pass" if passed else "delivery audit is not 100/100"
    return gate("commercial_delivery_package", 15, passed, status, str(path), not passed)


def audit_score_audio_traceability(root: Path) -> GateResult:
    path = root / "results" / "project1_pro_playback_traceability_audit_latest.json"
    data = read_json(path)
    passed = bool(data.get("all_pass")) and data.get("score_audio_traceability_score") == 100
    status = "pass" if passed else "pro playback score-audio traceability audit is missing or not 100/100"
    return gate("score_audio_traceability", 15, passed, status, str(path), not passed)


def audit_delivery_conformance(root: Path) -> GateResult:
    path = root / "results" / "project1_delivery_conformance_audit_latest.json"
    data = read_json(path)
    passed = bool(data.get("all_pass")) and data.get("conformance_score") == 100
    status = "pass" if passed else "delivery score-playback conformance audit is missing or not 100/100"
    return gate("delivery_score_playback_conformance", 0, passed, status, str(path), not passed)


def audit_delivery_integrity(root: Path) -> GateResult:
    folder_path = root / "results" / "project1_delivery_integrity_report_latest.json"
    zip_path = root / "results" / "project1_delivery_zip_integrity_report_latest.json"
    folder_data = read_json(folder_path)
    zip_data = read_json(zip_path)
    folder_passed = bool(folder_data.get("all_pass")) and int(folder_data.get("checked_file_count", 0) or 0) > 0
    zip_passed = bool(zip_data.get("all_pass")) and int(zip_data.get("checked_file_count", 0) or 0) > 0
    passed = folder_passed and zip_passed
    status = (
        "pass"
        if passed
        else f"delivery integrity verification missing or failed: folder={folder_passed}, zip={zip_passed}"
    )
    return gate("delivery_integrity_verification", 5, passed, status, f"{folder_path}; {zip_path}", not passed)


def audit_release_manifest(root: Path) -> GateResult:
    path = root / "results" / "project1_delivery_release_manifest_latest.json"
    data = read_json(path)
    zip_file = root / str(data.get("zip_file", ""))
    passed = (
        data.get("commercial_delivery_all_pass") is True
        and data.get("folder_integrity_all_pass") is True
        and data.get("zip_integrity_all_pass") is True
        and bool(data.get("zip_sha256"))
        and int(data.get("zip_size_bytes", 0) or 0) > 0
        and zip_file.is_file()
    )
    status = "pass" if passed else "delivery release ZIP manifest is missing, stale, or incomplete"
    return gate("delivery_release_manifest", 5, passed, status, str(path), not passed)


def audit_playback_license(root: Path) -> GateResult:
    path = root / "results" / "project1_playback_license_audit_latest.json"
    data = read_json(path)
    passed = bool(data.get("all_pass")) and data.get("license_audit_score") == 100
    status = "pass" if passed else "playback license notices are incomplete"
    return gate("playback_license_notices", 10, passed, status, str(path), not passed)


def audit_browser_player(root: Path) -> GateResult:
    path = root / "results" / "project1_delivery_player_qa_latest.json"
    static_path = root / "results" / "project1_delivery_player_static_audit_latest.json"
    release_path = root / "results" / "project1_delivery_release_manifest_latest.json"
    data = read_json(path)
    static_data = read_json(static_path)
    release_data = read_json(release_path)
    release_zip = Path(str(release_data.get("zip_file", "")))
    expected_package = release_zip.with_suffix("") if release_zip.suffix.lower() == ".zip" else Path("")
    static_package = Path(str(static_data.get("package_dir", "")))
    chrome_package = Path(str(data.get("package_dir", "")))
    browser_passed = (
        data.get("status") in {"pass", "fallback_static_pass"}
        and int(data.get("nav_items", 0)) >= 40
        and int(data.get("audio_controls_initial", 0)) >= 6
        and int(data.get("audio_controls_after_search", 0)) >= 6
    )
    static_passed = (
        static_data.get("all_pass") is True
        and int(static_data.get("score_count", 0) or 0) >= 40
        and int(static_data.get("manifest_rows", 0) or 0) >= 240
        and not static_data.get("bad_text_files")
    )
    package_matches_release = bool(expected_package) and (
        same_path(root / expected_package, static_package) or same_path(expected_package, static_package)
    )
    chrome_package_matches_release = bool(expected_package) and (
        same_path(root / expected_package, chrome_package) or same_path(expected_package, chrome_package)
    )
    passed = browser_passed and static_passed and package_matches_release and chrome_package_matches_release
    status = (
        "pass"
        if passed
        else (
            "offline player QA incomplete: "
            f"browser={browser_passed}, static={static_passed}, "
            f"static_package_matches_release={package_matches_release}, "
            f"qa_package_matches_release={chrome_package_matches_release}"
        )
    )
    return gate("offline_player_browser_qa", 10, passed, status, f"{path}; {static_path}", not passed)


def audit_recipient_usability(root: Path) -> GateResult:
    path = root / "results" / "project1_recipient_usability_audit_latest.json"
    data = read_json(path)
    passed = bool(data.get("all_pass")) and data.get("recipient_usability_score") == 100
    status = "pass" if passed else "recipient-facing usability audit is missing or not 100/100"
    return gate("recipient_usability_audit", 0, passed, status, str(path), not passed)


def same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left).replace("\\", "/").rstrip("/") == str(right).replace("\\", "/").rstrip("/")


def audit_expert_evaluation(root: Path) -> GateResult:
    summary_path = root / "results" / "project1_expert_eval_summary.json"
    intake_path = root / "results" / "project1_expert_return_intake_report_latest.json"
    summary = read_json(summary_path)
    intake = read_json(intake_path)
    summary_absolute = as_int(summary.get("absolute_completed_rows"))
    summary_paired = as_int(summary.get("paired_completed_rows"))
    summary_files = as_int(summary.get("rating_file_count"))
    valid_files = as_int(intake.get("valid_rating_file_count"))
    intake_absolute = as_int(intake.get("absolute_completed_rows"))
    intake_paired = as_int(intake.get("paired_completed_rows"))
    summary_ready = (
        summary.get("status") == "completed"
        and summary_files >= 3
        and summary_absolute > 0
        and summary_paired > 0
    )
    intake_ready = (
        intake_path.is_file()
        and intake.get("status") == "ready_to_summarize"
        and valid_files >= 3
        and intake_absolute > 0
        and intake_paired > 0
    )
    passed = summary_ready and intake_ready
    if passed:
        status = "pass"
    elif not intake_path.is_file():
        status = "expert evaluation intake validation report missing"
    else:
        status = (
            "expert evaluation pending, invalid, or insufficient: "
            f"summary_files={summary_files}, valid_files={valid_files}, "
            f"summary_absolute_rows={summary_absolute}, summary_paired_rows={summary_paired}, "
            f"intake_absolute_rows={intake_absolute}, intake_paired_rows={intake_paired}"
        )
    return gate("returned_expert_evaluation", 15, passed, status, f"{summary_path}; {intake_path}", True)


def audit_paper_compile(root: Path) -> GateResult:
    pdf = root / "paper" / "main.pdf"
    log = root / "paper" / "main.log"
    if not pdf.is_file() or not log.is_file():
        return gate("paper_compile", 5, False, "paper/main.pdf or main.log missing", f"{pdf}; {log}", True)
    log_text = log.read_text(encoding="utf-8", errors="ignore")
    bad_tokens = ["! LaTeX Error", "Fatal error", "Emergency stop", "Overfull \\hbox"]
    bad = [token for token in bad_tokens if token in log_text]
    passed = not bad and "Output written on main.pdf" in log_text
    status = "pass" if passed else f"compile warnings/errors requiring cleanup: {bad}"
    return gate("paper_compile", 5, passed, status, str(pdf), not passed)


def audit_rating_workflow(root: Path) -> GateResult:
    files = [
        root / "scripts" / "summarize_project1_expert_ratings.ps1",
        root / "src" / "chorale" / "expert_eval_tools.py",
        root / "paper" / "tables" / "project1_expert_eval_results.tex",
    ]
    passed = all(path.is_file() for path in files)
    status = "pass" if passed else "expert rating workflow files missing"
    return gate("expert_rating_workflow", 0, passed, status, "; ".join(str(path) for path in files), not passed)


def audit_review_issue_workflow(root: Path) -> GateResult:
    files = [
        root / "scripts" / "intake_project1_review_issues.ps1",
        root / "src" / "chorale" / "review_issue_intake.py",
    ]
    report_path = root / "results" / "project1_review_issue_intake_latest.json"
    missing = [str(path) for path in files if not path.is_file()]
    report = read_json(report_path)
    schema_ok = report.get("schema") == "project1_review_issue_intake_v1"
    status_value = str(report.get("status", ""))
    invalid_count = as_int(report.get("invalid_issue_count"))
    unmatched_count = as_int(report.get("unmatched_issue_count"))
    status_ok = status_value in {"no_issue_files", "ready_for_triage"}
    expected_package = expected_package_from_release(root)
    report_package = Path(str(report.get("package_dir", "")))
    package_ok = bool(expected_package) and path_matches_release(root, expected_package, report_package)
    passed = (
        not missing
        and report_path.is_file()
        and schema_ok
        and status_ok
        and invalid_count == 0
        and unmatched_count == 0
        and package_ok
    )
    if passed:
        status = "pass"
    elif missing:
        status = f"review issue intake workflow files missing: {missing}"
    elif not report_path.is_file():
        status = "review issue intake report missing"
    elif not schema_ok:
        status = "review issue intake report has unknown schema"
    elif not package_ok:
        status = (
            "review issue intake report points to a stale package: "
            f"expected={expected_package}, actual={report_package}"
        )
    else:
        status = (
            "review issue intake has rows that must be fixed before commercial triage: "
            f"status={status_value}, invalid={invalid_count}, unmatched={unmatched_count}"
        )
    evidence = "; ".join([*(str(path) for path in files), str(report_path)])
    return gate("review_issue_intake_workflow", 0, passed, status, evidence, not passed)


def audit_issue_evidence_packet_workflow(root: Path) -> GateResult:
    files = [
        root / "scripts" / "build_project1_issue_evidence_packet.ps1",
        root / "src" / "chorale" / "delivery_issue_packet.py",
        root / "src" / "chorale" / "delivery_issue_debugger.py",
    ]
    missing = [str(path) for path in files if not path.is_file()]
    passed = not missing
    status = "pass" if passed else f"issue evidence packet workflow files missing: {missing}"
    return gate("issue_evidence_packet_workflow", 0, passed, status, "; ".join(str(path) for path in files), not passed)


def audit_legal_review_packet(root: Path) -> GateResult:
    path = root / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json"
    report = read_json(path)
    release = read_json(root / "results" / "project1_delivery_release_manifest_latest.json")
    expected_zip = Path(str(release.get("zip_file", "")))
    expected_sha = str(release.get("zip_sha256", "")).strip()
    packet_zip = Path(str(report.get("delivery_zip", "")))
    packet_sha = str(report.get("delivery_zip_sha256", "")).strip()
    schema_ok = report.get("schema") == "project1_commercial_legal_review_packet_v1"
    status_ok = report.get("status") == "manual review required"
    zip_ok = bool(expected_zip) and path_matches_release(root, expected_zip, packet_zip)
    sha_ok = bool(expected_sha) and packet_sha == expected_sha
    passed = path.is_file() and schema_ok and status_ok and zip_ok and sha_ok
    if passed:
        status = "pass"
    elif not path.is_file():
        status = "commercial/legal review packet missing"
    else:
        status = (
            "commercial/legal review packet is missing, stale, or not tied to the current ZIP: "
            f"schema_ok={schema_ok}, status_ok={status_ok}, zip_matches_release={zip_ok}, sha_matches_release={sha_ok}"
        )
    return gate("commercial_legal_review_packet_current", 0, passed, status, str(path), not passed)


def audit_legal_signoff(root: Path) -> GateResult:
    path = root / "results" / "project1_commercial_legal_signoff.json"
    if not path.is_file():
        return gate(
            "commercial_legal_signoff",
            10,
            False,
            "manual legal/commercial redistribution signoff missing",
            str(path),
            True,
        )
    data = read_json(path)
    release = read_json(root / "results" / "project1_delivery_release_manifest_latest.json")
    passed, problems = legal_signoff_is_complete(data, release)
    status = "pass" if passed else f"legal/commercial signoff incomplete: {problems}"
    return gate("commercial_legal_signoff", 10, passed, status, str(path), not passed)


def gate(name: str, weight: int, passed: bool, status: str, evidence: str, blocking: bool = False) -> GateResult:
    return GateResult(name, weight, passed, status, evidence, blocking)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8-sig"))


def as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def expected_package_from_release(root: Path) -> Path | None:
    release = read_json(root / "results" / "project1_delivery_release_manifest_latest.json")
    release_zip = Path(str(release.get("zip_file", "")))
    if release_zip.suffix.lower() != ".zip":
        return None
    return release_zip.with_suffix("")


def path_matches_release(root: Path, expected: Path, observed: Path) -> bool:
    return bool(str(observed)) and (
        same_path(root / expected, observed)
        or same_path(expected, observed)
        or same_path(root / expected, root / observed)
    )


def legal_signoff_is_complete(data: dict[str, object], release: dict[str, object] | None = None) -> tuple[bool, list[str]]:
    problems: list[str] = []
    if data.get("approved_for_commercial_distribution") is not True:
        problems.append("approved_for_commercial_distribution is not true")
    required_checks = data.get("required_checks")
    if not isinstance(required_checks, dict) or not required_checks:
        problems.append("required_checks missing or empty")
    else:
        missing = [str(key) for key, value in required_checks.items() if value is not True]
        if missing:
            problems.append(f"required checks not approved: {missing}")
    for field in ["reviewer_name", "reviewer_role", "review_date"]:
        value = str(data.get(field, "")).strip()
        if not value or "TODO" in value.upper() or value == "YYYY-MM-DD":
            problems.append(f"{field} missing or placeholder")
    if release:
        expected_zip = str(release.get("zip_file", "")).strip()
        expected_sha = str(release.get("zip_sha256", "")).strip()
        signed_zip = str(data.get("delivery_zip", "")).strip()
        signed_sha = str(data.get("delivery_zip_sha256", "")).strip()
        if not expected_zip or signed_zip.replace("\\", "/") != expected_zip.replace("\\", "/"):
            problems.append("delivery_zip does not match current release manifest")
        if not expected_sha or signed_sha != expected_sha:
            problems.append("delivery_zip_sha256 does not match current release manifest")
    return not problems, problems


def write_outputs(summary: dict[str, object], out_json: Path) -> None:
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(summary), encoding="utf-8")


def make_markdown(summary: dict[str, object]) -> str:
    lines = [
        "# Project1 Commercial Readiness Audit",
        "",
        f"Score: {summary['commercial_readiness_score']}/100",
        f"Status: {summary['status']}",
        "",
        "## Gates",
        "",
        "| Gate | Weight | Status | Evidence |",
        "|---|---:|---|---|",
    ]
    for item in summary.get("gates", []):
        if not isinstance(item, dict):
            continue
        mark = "PASS" if item.get("passed") else "PENDING/BLOCKED"
        lines.append(f"| {item.get('gate')} | {item.get('weight')} | {mark}: {item.get('status')} | `{item.get('evidence')}` |")
    blocking = summary.get("blocking_items", [])
    lines.extend(["", "## Blocking Items", ""])
    if blocking:
        for item in blocking:
            lines.append(f"- {item}")
    else:
        lines.append("No blocking items.")
    lines.append("")
    lines.append("This audit is an engineering readiness gate. It does not replace legal advice or real expert evaluation.")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate Project1 commercial-readiness evidence.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-json", default="results/project1_commercial_readiness_audit.json")
    args = parser.parse_args()
    summary = run_readiness_audit(args.root)
    write_outputs(summary, Path(args.out_json))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
