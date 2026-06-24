from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ENGINEERING_CHECKS = [
    "release_manifest",
    "commercial_delivery",
    "folder_integrity",
    "zip_integrity",
    "media_audit",
    "conformance_audit",
    "static_player_audit",
    "recipient_usability_audit",
    "playback_license_audit",
    "traceability_audit",
]


def build_release_candidate_report(root: str | Path = ".") -> dict[str, Any]:
    root_path = Path(root)
    release = read_json(root_path / "results" / "project1_delivery_release_manifest_latest.json")
    delivery = read_json(root_path / "results" / "project1_commercial_delivery_audit_latest.json")
    folder_integrity = read_json(root_path / "results" / "project1_delivery_integrity_report_latest.json")
    zip_integrity = read_json(root_path / "results" / "project1_delivery_zip_integrity_report_latest.json")
    media = read_json(root_path / "results" / "project1_delivery_media_audit_latest.json")
    conformance = read_json(root_path / "results" / "project1_delivery_conformance_audit_latest.json")
    static_player = read_json(root_path / "results" / "project1_delivery_player_static_audit_latest.json")
    chrome_player = read_json(root_path / "results" / "project1_delivery_player_qa_latest.json")
    recipient_usability = read_json(root_path / "results" / "project1_recipient_usability_audit_latest.json")
    license_audit = read_json(root_path / "results" / "project1_playback_license_audit_latest.json")
    traceability = read_json(root_path / "results" / "project1_pro_playback_traceability_audit_latest.json")
    claims = read_json(root_path / "results" / "project1_commercial_claims_audit_latest.json")
    readiness = read_json(root_path / "results" / "project1_commercial_readiness_audit.json")
    acceptance = read_json(root_path / "results" / "project1_commercial_acceptance_report_latest.json")
    release_gate = read_json(root_path / "results" / "project1_commercial_release_gate_latest.json")
    legal_packet = read_json(root_path / "results" / "project1_commercial_legal_review_packet" / "LEGAL_PACKET_SUMMARY.json")

    engineering_checks = [
        check_release_manifest(root_path, release),
        check_delivery(delivery),
        check_integrity("folder_integrity", folder_integrity),
        check_integrity("zip_integrity", zip_integrity),
        check_media(media),
        check_conformance(conformance),
        check_static_player(static_player, release),
        check_recipient_usability(recipient_usability),
        check_license(license_audit),
        check_traceability(traceability),
        check_claims(claims),
        check_legal_packet(legal_packet, release),
    ]
    optional_checks = [check_chrome_player(chrome_player, release)]
    customer_review_checks = [check_real_browser_player(root_path, chrome_player, release)]
    engineering_ready = all(item["passed"] for item in engineering_checks)
    customer_review_ready = engineering_ready and all(item["passed"] for item in customer_review_checks)
    commercial_ready = release_gate.get("commercial_release_ready") is True
    blocking = [item for item in engineering_checks + optional_checks if item["blocking"] and not item["passed"]]
    customer_review_blockers = [item for item in customer_review_checks if item["blocking"] and not item["passed"]]
    external_blockers = list(release_gate.get("blocking_items", [])) if isinstance(release_gate.get("blocking_items"), list) else []

    report = {
        "schema": "project1_commercial_release_candidate_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "engineering_release_candidate_ready": engineering_ready,
        "customer_review_ready": customer_review_ready,
        "commercial_release_ready": commercial_ready,
        "engineering_status": "ready_for_expert_or_customer_review" if engineering_ready else "engineering_blocked",
        "customer_review_status": "ready_for_live_reviewer_delivery" if customer_review_ready else "blocked_until_real_browser_qa",
        "commercial_status": "ready_for_commercial_release" if commercial_ready else "blocked_pending_external_evidence",
        "commercial_readiness_score": readiness.get("commercial_readiness_score"),
        "release_gate_score": release_gate.get("release_score"),
        "deliverable": {
            "zip_file": release.get("zip_file"),
            "zip_name": release.get("zip_name"),
            "zip_size_bytes": release.get("zip_size_bytes"),
            "zip_sha256": release.get("zip_sha256"),
            "zip_regular_file_count": release.get("zip_regular_file_count"),
            "score_count": release.get("score_count"),
            "mp3_count": release.get("mp3_count"),
            "midi_count": release.get("midi_count"),
            "manifest_rows": release.get("manifest_rows"),
        },
        "engineering_checks": engineering_checks,
        "optional_checks": optional_checks,
        "customer_review_checks": customer_review_checks,
        "engineering_blockers": [item["gate"] for item in blocking],
        "customer_review_blockers": [item["gate"] for item in customer_review_blockers],
        "commercial_blockers": external_blockers,
        "acceptance_status": {
            "engineering_acceptance": acceptance.get("engineering_acceptance"),
            "commercial_release": acceptance.get("commercial_release"),
            "all_commercial_gates_pass": acceptance.get("all_commercial_gates_pass"),
        },
        "next_actions": next_actions(
            engineering_ready,
            customer_review_ready,
            commercial_ready,
            blocking,
            customer_review_blockers,
            external_blockers,
        ),
        "claim_boundary": (
            "If engineering_release_candidate_ready is true but commercial_release_ready is false, "
            "the package may be used for expert/customer review but must not be claimed as commercially released."
        ),
    }
    return report


def check_release_manifest(root: Path, release: dict[str, Any]) -> dict[str, Any]:
    zip_file = str(release.get("zip_file", ""))
    zip_path = root / zip_file
    expected_sha = str(release.get("zip_sha256", ""))
    actual_sha = sha256_file(zip_path) if zip_path.is_file() else ""
    passed = (
        zip_path.is_file()
        and bool(expected_sha)
        and expected_sha == actual_sha
        and release.get("commercial_delivery_all_pass") is True
        and release.get("folder_integrity_all_pass") is True
        and release.get("zip_integrity_all_pass") is True
    )
    return make_check(
        "release_manifest",
        passed,
        "pass"
        if passed
        else (
            "release manifest incomplete or hash mismatch: "
            f"exists={zip_path.is_file()}, expected_sha={expected_sha}, actual_sha={actual_sha}"
        ),
        "results/project1_delivery_release_manifest_latest.json",
    )


def check_delivery(delivery: dict[str, Any]) -> dict[str, Any]:
    passed = delivery.get("all_pass") is True and delivery.get("commercial_delivery_score") == 100
    return make_check(
        "commercial_delivery",
        passed,
        "pass" if passed else "commercial delivery audit is missing or not 100/100",
        "results/project1_commercial_delivery_audit_latest.json",
    )


def check_integrity(name: str, data: dict[str, Any]) -> dict[str, Any]:
    passed = data.get("all_pass") is True and int(data.get("checked_file_count", 0) or 0) > 0
    return make_check(
        name,
        passed,
        "pass" if passed else f"{name} missing or failed",
        f"results/project1_delivery_{'zip_' if name == 'zip_integrity' else ''}integrity_report_latest.json",
    )


def check_media(media: dict[str, Any]) -> dict[str, Any]:
    passed = media.get("all_pass") is True and media.get("media_delivery_score") == 100
    return make_check(
        "media_audit",
        passed,
        "pass" if passed else "MP3/MIDI media parseability audit missing or failed",
        "results/project1_delivery_media_audit_latest.json",
    )


def check_conformance(conformance: dict[str, Any]) -> dict[str, Any]:
    passed = conformance.get("all_pass") is True and conformance.get("conformance_score") == 100
    return make_check(
        "conformance_audit",
        passed,
        "pass" if passed else "score-playback conformance audit missing or failed",
        "results/project1_delivery_conformance_audit_latest.json",
    )


def check_static_player(static_player: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    zip_file = Path(str(release.get("zip_file", "")))
    expected_package = zip_file.with_suffix("") if zip_file.suffix.lower() == ".zip" else Path("")
    package_dir = Path(str(static_player.get("package_dir", "")))
    package_matches = bool(expected_package) and normalize_path(package_dir) == normalize_path(expected_package)
    passed = (
        static_player.get("all_pass") is True
        and int(static_player.get("score_count", 0) or 0) >= 40
        and int(static_player.get("manifest_rows", 0) or 0) >= 240
        and not static_player.get("bad_text_files")
        and package_matches
    )
    return make_check(
        "static_player_audit",
        passed,
        "pass"
        if passed
        else (
            "offline player static audit missing, failed, or points to a stale package: "
            f"package_matches_release={package_matches}"
        ),
        "results/project1_delivery_player_static_audit_latest.json",
    )


def check_recipient_usability(recipient_usability: dict[str, Any]) -> dict[str, Any]:
    passed = (
        recipient_usability.get("all_pass") is True
        and recipient_usability.get("recipient_usability_score") == 100
    )
    return make_check(
        "recipient_usability_audit",
        passed,
        "pass" if passed else "recipient-facing usability audit missing or failed",
        "results/project1_recipient_usability_audit_latest.json",
    )


def check_chrome_player(chrome_player: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    zip_file = Path(str(release.get("zip_file", "")))
    expected_package = zip_file.with_suffix("") if zip_file.suffix.lower() == ".zip" else Path("")
    package_dir = Path(str(chrome_player.get("package_dir", "")))
    package_matches = bool(expected_package) and normalize_path(package_dir) == normalize_path(expected_package)
    passed = (
        chrome_player.get("status") in {"pass", "fallback_static_pass"}
        and int(chrome_player.get("nav_items", 0) or 0) >= 40
        and int(chrome_player.get("audio_controls_initial", 0) or 0) >= 6
        and package_matches
    )
    check = make_check(
        "chrome_player_qa",
        passed,
        str(chrome_player.get("status") or "missing")
        if passed
        else f"Chrome player QA missing, failed, or stale: package_matches_release={package_matches}",
        "results/project1_delivery_player_qa_latest.json",
    )
    check["blocking"] = False
    return check


def check_real_browser_player(root: Path, chrome_player: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    zip_file = Path(str(release.get("zip_file", "")))
    expected_package = zip_file.with_suffix("") if zip_file.suffix.lower() == ".zip" else Path("")
    package_dir = Path(str(chrome_player.get("package_dir", "")))
    package_matches = bool(expected_package) and normalize_path(package_dir) == normalize_path(expected_package)
    screenshot = Path(str(chrome_player.get("screenshot", "")))
    screenshot_path = screenshot if screenshot.is_absolute() else root / screenshot
    screenshot_ok = bool(str(screenshot)) and screenshot_path.is_file()
    passed = (
        chrome_player.get("status") == "pass"
        and str(chrome_player.get("browser_status", "pass")) not in {"failed", "not_run", "unavailable"}
        and int(chrome_player.get("nav_items", 0) or 0) >= 40
        and int(chrome_player.get("audio_controls_initial", 0) or 0) >= 6
        and int(chrome_player.get("audio_controls_after_search", 0) or 0) >= 6
        and package_matches
        and screenshot_ok
    )
    return make_check(
        "real_browser_player_qa",
        passed,
        "pass"
        if passed
        else (
            "real Chrome/Edge player QA has not passed for the current package: "
            f"status={chrome_player.get('status')}, browser_status={chrome_player.get('browser_status')}, "
            f"package_matches_release={package_matches}, screenshot_ok={screenshot_ok}. "
            "Run scripts/qa_project1_delivery_player_chrome.ps1 without -StaticOnly."
        ),
        "results/project1_delivery_player_qa_latest.json",
    )


def check_license(license_audit: dict[str, Any]) -> dict[str, Any]:
    passed = license_audit.get("all_pass") is True and license_audit.get("license_audit_score") == 100
    return make_check(
        "playback_license_audit",
        passed,
        "pass" if passed else "playback license audit missing or failed",
        "results/project1_playback_license_audit_latest.json",
    )


def check_traceability(traceability: dict[str, Any]) -> dict[str, Any]:
    passed = traceability.get("all_pass") is True and traceability.get("score_audio_traceability_score") == 100
    return make_check(
        "traceability_audit",
        passed,
        "pass" if passed else "score-audio traceability audit missing or failed",
        "results/project1_pro_playback_traceability_audit_latest.json",
    )


def check_claims(claims: dict[str, Any]) -> dict[str, Any]:
    passed = claims.get("all_pass") is True and int(claims.get("violation_count", -1) or 0) == 0
    return make_check(
        "commercial_claims_audit",
        passed,
        "pass" if passed else "unsupported public-facing commercial claims detected or audit missing",
        "results/project1_commercial_claims_audit_latest.json",
    )


def check_legal_packet(legal_packet: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    expected_zip = str(release.get("zip_file", "")).replace("\\", "/").strip()
    actual_zip = str(legal_packet.get("delivery_zip", "")).replace("\\", "/").strip()
    expected_sha = str(release.get("zip_sha256", "")).strip()
    actual_sha = str(legal_packet.get("delivery_zip_sha256", "")).strip()
    schema_ok = legal_packet.get("schema") == "project1_commercial_legal_review_packet_v1"
    status_ok = legal_packet.get("status") == "manual review required"
    zip_ok = bool(expected_zip) and actual_zip == expected_zip
    sha_ok = bool(expected_sha) and actual_sha == expected_sha
    passed = schema_ok and status_ok and zip_ok and sha_ok
    return make_check(
        "commercial_legal_review_packet",
        passed,
        "pass"
        if passed
        else (
            "legal review packet missing, stale, or not tied to current ZIP: "
            f"schema_ok={schema_ok}, status_ok={status_ok}, zip_matches_release={zip_ok}, sha_matches_release={sha_ok}"
        ),
        "results/project1_commercial_legal_review_packet/LEGAL_PACKET_SUMMARY.json",
    )


def make_check(gate: str, passed: bool, status: str, evidence: str) -> dict[str, Any]:
    return {"gate": gate, "passed": bool(passed), "status": status, "evidence": evidence, "blocking": True}


def next_actions(
    engineering_ready: bool,
    customer_review_ready: bool,
    commercial_ready: bool,
    engineering_blockers: list[dict[str, Any]],
    customer_review_blockers: list[dict[str, Any]],
    commercial_blockers: list[Any],
) -> list[str]:
    actions: list[str] = []
    if engineering_blockers:
        actions.append("Fix failed engineering audits, regenerate affected reports, and rerun the release-candidate audit.")
    if engineering_ready and not customer_review_ready and customer_review_blockers:
        actions.append(
            "Run real Chrome/Edge QA for the current package before sending it to live reviewers: "
            "scripts/qa_project1_delivery_player_chrome.ps1 without -StaticOnly, then rerun the release-candidate audit."
        )
    if engineering_ready and not commercial_ready:
        actions.append("Use the current package for expert/customer review, not as a final commercial-release claim.")
    if "returned_expert_evaluation" in commercial_blockers:
        actions.append("Collect at least three real expert rating workbooks and summarize them.")
    if "commercial_legal_signoff" in commercial_blockers:
        actions.append("Complete the real legal/commercial review and signoff.")
    if not actions:
        actions.append("All release-candidate gates are clear.")
    return actions


def normalize_path(path: Path) -> str:
    return str(path).replace("\\", "/").rstrip("/").lower()


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
        "# Project1 Commercial Release-Candidate Audit",
        "",
        f"Engineering release candidate ready: **{report.get('engineering_release_candidate_ready')}**",
        f"Customer review ready: **{report.get('customer_review_ready')}**",
        f"Commercial release ready: **{report.get('commercial_release_ready')}**",
        f"Commercial readiness score: **{report.get('commercial_readiness_score')}/100**",
        f"Release gate score: **{report.get('release_gate_score')}/100**",
        "",
        "## Engineering Checks",
        "",
        "| Gate | Status | Evidence |",
        "|---|---|---|",
    ]
    for item in report.get("engineering_checks", []):
        if isinstance(item, dict):
            mark = "PASS" if item.get("passed") else "BLOCKED"
            lines.append(f"| {item.get('gate')} | {mark}: {item.get('status')} | `{item.get('evidence')}` |")
    lines.extend(["", "## Optional Checks", "", "| Gate | Status | Evidence |", "|---|---|---|"])
    for item in report.get("optional_checks", []):
        if isinstance(item, dict):
            mark = "PASS" if item.get("passed") else "WARN"
            lines.append(f"| {item.get('gate')} | {mark}: {item.get('status')} | `{item.get('evidence')}` |")
    lines.extend(["", "## Customer Review Checks", "", "| Gate | Status | Evidence |", "|---|---|---|"])
    for item in report.get("customer_review_checks", []):
        if isinstance(item, dict):
            mark = "PASS" if item.get("passed") else "BLOCKED"
            lines.append(f"| {item.get('gate')} | {mark}: {item.get('status')} | `{item.get('evidence')}` |")
    lines.extend(["", "## Customer Review Blockers", ""])
    customer_blockers = report.get("customer_review_blockers", [])
    if customer_blockers:
        lines.extend(f"- {item}" for item in customer_blockers)
    else:
        lines.append("No customer-review blockers.")
    lines.extend(["", "## Commercial Blockers", ""])
    blockers = report.get("commercial_blockers", [])
    if blockers:
        lines.extend(f"- {item}" for item in blockers)
    else:
        lines.append("No commercial blockers.")
    lines.extend(["", "## Next Actions", ""])
    actions = report.get("next_actions", [])
    lines.extend(f"- {item}" for item in actions)
    lines.extend(["", str(report.get("claim_boundary", "")), ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Project1 release-candidate evidence.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out-json", default="results/project1_commercial_release_candidate_latest.json")
    args = parser.parse_args()
    report = build_release_candidate_report(args.root)
    outputs = write_report(report, args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
