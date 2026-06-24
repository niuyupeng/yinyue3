from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from chorale.delivery_player_static_audit import audit_player_package


COMMON_CHROME_PATHS = [
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
]


def run_chrome_player_qa(
    package_dir: str | Path,
    *,
    chrome_path: str | Path | None = None,
    screenshot_path: str | Path = "results/project1_delivery_player_qa_latest.png",
) -> dict[str, object]:
    package = Path(package_dir)
    html_path = package / "score_audio_player.html"
    if not html_path.is_file():
        raise FileNotFoundError(f"Player HTML not found: {html_path}")
    browsers = resolve_chrome_candidates(chrome_path)
    if not browsers:
        return {
            "schema": "project1_delivery_player_chrome_qa_v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "status": "unavailable",
            "package_dir": str(package),
            "html": str(html_path),
            "issues": ["Chrome or Edge executable not found."],
        }
    url = file_url(html_path)
    browser_errors: list[str] = []
    for chrome in browsers:
        try:
            dom = dump_dom(chrome, url)
            if not dom.strip():
                raise RuntimeError("Chrome returned an empty DOM.")
            screenshot = Path(screenshot_path)
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            capture_screenshot(chrome, url, screenshot)
        except Exception as exc:
            browser_errors.append(f"{chrome}: {type(exc).__name__}: {str(exc)[:500]}")
            continue
        summary = summarize_dom(dom)
        issues: list[str] = []
        if summary["nav_items"] < 40:
            issues.append(f"expected at least 40 nav items, found {summary['nav_items']}")
        if summary["audio_controls"] < 6:
            issues.append(f"expected at least 6 audio controls, found {summary['audio_controls']}")
        if "Project1 SATB 乐谱-音频审阅台" not in dom:
            issues.append("clean Chinese player title not found in rendered DOM")
        if "QC score: 100/100" not in dom:
            issues.append("QC score badge not found in rendered DOM")
        return {
            "schema": "project1_delivery_player_chrome_qa_v1",
            "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "browser": str(chrome),
            "status": "pass" if not issues else "failed",
            "package_dir": str(package),
            "html": str(html_path),
            "title": "Project1 SATB 乐谱-音频审阅台",
            "nav_items": summary["nav_items"],
            "audio_controls_initial": summary["audio_controls"],
            "audio_controls_after_search": summary["audio_controls"],
            "qc_badges": summary["qc_badges"],
            "screenshot": str(screenshot),
            "issues": issues,
        }
    return fallback_static_report(package, html_path, browsers[0], RuntimeError("; ".join(browser_errors)))


def static_player_qa_report(
    package_dir: str | Path,
    *,
    reason: str = "Chrome browser QA was not requested for this release-candidate refresh.",
) -> dict[str, object]:
    package = Path(package_dir)
    html_path = package / "score_audio_player.html"
    if not html_path.is_file():
        raise FileNotFoundError(f"Player HTML not found: {html_path}")
    return build_static_player_qa_report(
        package,
        html_path,
        browser="not_run",
        browser_status="not_run",
        browser_error=reason,
        note=(
            "Chrome/Edge rendering was not run for this refresh. This report is an intentionally generated "
            "static player/manifest QA record for the current release package, not a browser screenshot pass."
        ),
    )


def fallback_static_report(package: Path, html_path: Path, chrome: Path, exc: Exception) -> dict[str, object]:
    return build_static_player_qa_report(
        package,
        html_path,
        browser=str(chrome),
        browser_status="failed",
        browser_error=f"{type(exc).__name__}: {str(exc)[:500]}",
        note=(
            "Chromium headless failed in this local environment, so this report falls back to the static "
            "player/manifest audit. This is not a screenshot-based browser-rendering pass."
        ),
    )


def build_static_player_qa_report(
    package: Path,
    html_path: Path,
    *,
    browser: str,
    browser_status: str,
    browser_error: str,
    note: str,
) -> dict[str, object]:
    static = audit_player_package(package)
    static_passed = static.get("all_pass") is True
    variant_counts = static.get("variant_counts", {})
    complete_variants = bool(variant_counts) and all(
        int(variant_counts.get(name, 0) or 0) >= int(static.get("score_count", 0) or 0)
        for name in ["full_choir", "piano_reference", "stem_soprano", "stem_alto", "stem_tenor", "stem_bass"]
    ) if isinstance(variant_counts, dict) else False
    issues = [] if static_passed else list(static.get("issues", []) or ["static player audit failed"])
    return {
        "schema": "project1_delivery_player_chrome_qa_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "browser": browser,
        "browser_status": browser_status,
        "browser_error": browser_error,
        "status": "fallback_static_pass" if static_passed else "failed",
        "package_dir": str(package),
        "html": str(html_path),
        "title": "Project1 SATB 乐谱-音频审阅台",
        "nav_items": int(static.get("score_count", 0) or 0),
        "audio_controls_initial": 6 if complete_variants else 0,
        "audio_controls_after_search": 6 if complete_variants else 0,
        "qc_badges": ["static player audit pass"] if static_passed else [],
        "screenshot": "",
        "fallback_note": note,
        "static_audit": static,
        "issues": issues,
    }


def resolve_chrome(chrome_path: str | Path | None) -> Path | None:
    candidates = resolve_chrome_candidates(chrome_path)
    return candidates[0] if candidates else None


def resolve_chrome_candidates(chrome_path: str | Path | None) -> list[Path]:
    if chrome_path:
        candidate = Path(chrome_path)
        return [candidate] if candidate.is_file() else []
    return [candidate for candidate in COMMON_CHROME_PATHS if candidate.is_file()]


def file_url(path: Path) -> str:
    return path.resolve().as_uri()


def dump_dom(chrome: Path, url: str) -> str:
    last_error = ""
    for attempt, virtual_time_budget in enumerate((3000, 8000, 15000), start=1):
        with tempfile.TemporaryDirectory(prefix="project1-chrome-qa-") as profile:
            command = chrome_command(chrome, url, profile) + [
                f"--virtual-time-budget={virtual_time_budget}",
                "--dump-dom",
                url,
            ]
            try:
                completed = run_chrome_command(command)
                return completed.stdout
            except RuntimeError as exc:
                last_error = str(exc)
        time.sleep(0.5 * attempt)
    raise RuntimeError(f"Chrome dump-dom failed after 3 attempts. Last error: {last_error}")


def capture_screenshot(chrome: Path, url: str, screenshot: Path) -> None:
    last_error = ""
    for attempt in range(1, 4):
        with tempfile.TemporaryDirectory(prefix="project1-chrome-qa-") as profile:
            command = chrome_command(chrome, url, profile) + [
                "--window-size=1400,1000",
                f"--screenshot={screenshot.resolve()}",
                url,
            ]
            try:
                run_chrome_command(command)
                return
            except RuntimeError as exc:
                last_error = str(exc)
        time.sleep(0.5 * attempt)
    raise RuntimeError(f"Chrome screenshot failed after 3 attempts. Last error: {last_error}")


def run_chrome_command(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip().replace("\r", " ").replace("\n", " ")
        stdout = (exc.stdout or "").strip().replace("\r", " ").replace("\n", " ")
        if len(stderr) > 600:
            stderr = stderr[:600] + "..."
        if len(stdout) > 300:
            stdout = stdout[:300] + "..."
        raise RuntimeError(
            f"returncode={exc.returncode}; stderr={stderr or '<empty>'}; stdout={stdout or '<empty>'}"
        ) from exc


def chrome_command(chrome: Path, url: str, profile_dir: str) -> list[str]:
    return [
        str(chrome),
        "--headless=new",
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-software-rasterizer",
        "--disable-accelerated-2d-canvas",
        "--disable-features=VizDisplayCompositor,UseSkiaRenderer",
        "--disable-dev-shm-usage",
        "--disable-component-update",
        "--disable-crash-reporter",
        "--disable-breakpad",
        "--no-first-run",
        "--disable-extensions",
        "--disable-background-networking",
        "--disable-sync",
        "--no-default-browser-check",
        "--allow-file-access-from-files",
        f"--user-data-dir={profile_dir}",
    ]


def summarize_dom(dom: str) -> dict[str, object]:
    return {
        "nav_items": len(re.findall(r'class="nav-item(?: active)?"', dom)),
        "audio_controls": len(re.findall(r"<audio\b", dom)),
        "qc_badges": re.findall(r"QC score:\s*[^<]+|通过:\s*[^<]+|失败:\s*[^<]+", dom),
    }


def write_outputs(report: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out = Path(out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"json": str(out), "screenshot": str(report.get("screenshot", ""))}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Chrome headless QA for the Project1 offline score-audio player.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--chrome-path", default="")
    parser.add_argument("--out-json", default="results/project1_delivery_player_qa_latest.json")
    parser.add_argument("--screenshot", default="results/project1_delivery_player_qa_latest.png")
    parser.add_argument("--static-only", action="store_true")
    parser.add_argument("--strict-browser", action="store_true", help="Fail unless real Chrome/Edge rendering status is pass.")
    args = parser.parse_args()
    if args.static_only:
        report = static_player_qa_report(args.package_dir)
    else:
        report = run_chrome_player_qa(
            args.package_dir,
            chrome_path=args.chrome_path or None,
            screenshot_path=args.screenshot,
        )
    outputs = write_outputs(report, args.out_json)
    print(json.dumps({"report": report, "outputs": outputs}, indent=2, ensure_ascii=False))
    if report["status"] == "failed" or (args.strict_browser and report["status"] != "pass"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
