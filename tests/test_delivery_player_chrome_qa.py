from __future__ import annotations

from pathlib import Path

import pytest

import chorale.delivery_player_chrome_qa as chrome_qa
from chorale.delivery_player_chrome_qa import fallback_static_report, file_url, main, static_player_qa_report
from chorale.pro_playback_index import build_playback_index
from tests.test_delivery_player_static_audit import make_player_package


def test_file_url_uses_standard_local_file_uri(tmp_path: Path) -> None:
    html = tmp_path / "score_audio_player.html"
    html.write_text("<html></html>", encoding="utf-8")

    url = file_url(html)

    assert url.startswith("file:///")
    assert "%3A" not in url
    assert "score_audio_player.html" in url


def test_chrome_qa_fallback_reports_static_pass_without_browser_claim(tmp_path: Path) -> None:
    package = make_player_package(tmp_path)
    build_playback_index(package)

    report = fallback_static_report(package, package / "score_audio_player.html", Path("chrome.exe"), RuntimeError("boom"))

    assert report["status"] == "fallback_static_pass"
    assert report["browser_status"] == "failed"
    assert report["nav_items"] == 40
    assert report["audio_controls_initial"] == 6
    assert "not a screenshot-based" in str(report["fallback_note"])


def test_static_only_qa_reports_current_package_without_browser_claim(tmp_path: Path) -> None:
    package = make_player_package(tmp_path)
    build_playback_index(package)

    report = static_player_qa_report(package)

    assert report["status"] == "fallback_static_pass"
    assert report["browser_status"] == "not_run"
    assert report["package_dir"] == str(package)
    assert report["nav_items"] == 40
    assert "not a browser screenshot pass" in str(report["fallback_note"])


def test_strict_browser_mode_rejects_static_fallback(tmp_path: Path, monkeypatch) -> None:
    package = make_player_package(tmp_path)
    build_playback_index(package)
    out_json = tmp_path / "qa.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "delivery_player_chrome_qa",
            "--package-dir",
            str(package),
            "--out-json",
            str(out_json),
            "--static-only",
            "--strict-browser",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        main()

    assert exc.value.code == 1
    assert out_json.is_file()


def test_chrome_qa_tries_next_browser_before_static_fallback(tmp_path: Path, monkeypatch) -> None:
    package = make_player_package(tmp_path)
    build_playback_index(package)
    html = (
        "<html><head><title>Project1 SATB 乐谱-音频审阅台</title></head><body>"
        + "".join('<button class="nav-item">x</button>' for _ in range(40))
        + "".join("<audio></audio>" for _ in range(6))
        + "<span>QC score: 100/100</span></body></html>"
    )
    screenshot = tmp_path / "qa.png"

    monkeypatch.setattr(
        chrome_qa,
        "resolve_chrome_candidates",
        lambda chrome_path: [Path("unstable-chrome.exe"), Path("stable-edge.exe")],
    )

    def fake_dump_dom(chrome: Path, url: str) -> str:
        if chrome.name.startswith("unstable"):
            raise RuntimeError("gpu crash")
        return html

    monkeypatch.setattr(chrome_qa, "dump_dom", fake_dump_dom)
    monkeypatch.setattr(chrome_qa, "capture_screenshot", lambda chrome, url, path: Path(path).write_bytes(b"png"))

    report = chrome_qa.run_chrome_player_qa(package, screenshot_path=screenshot)

    assert report["status"] == "pass"
    assert report["browser"] == "stable-edge.exe"
    assert screenshot.is_file()
