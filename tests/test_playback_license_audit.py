from __future__ import annotations

from pathlib import Path

import chorale.playback_license_audit as license_audit


def test_playback_license_audit_writes_required_notices(tmp_path: Path, monkeypatch) -> None:
    soundfont_dir = tmp_path / "soundfonts"
    soundfont_dir.mkdir()
    soundfont = soundfont_dir / "MuseScore_General.sf3"
    license_file = soundfont_dir / "MuseScore_General_License.md"
    readme_file = soundfont_dir / "MuseScore_General_Readme.md"
    soundfont.write_bytes(b"sf3")
    license_file.write_text(
        "MuseScore_General is shared under the MIT license. Permission is hereby granted. "
        "The acknowledgements and copyright notices above must be included.",
        encoding="utf-8",
    )
    readme_file.write_text("MuseScore General README", encoding="utf-8")
    monkeypatch.setattr(license_audit, "SOUNDFONT_FILE", soundfont)
    monkeypatch.setattr(license_audit, "SOUNDFONT_LICENSE", license_file)
    monkeypatch.setattr(license_audit, "SOUNDFONT_README", readme_file)

    license_audit.write_package_notices(tmp_path)
    summary = license_audit.audit_playback_licenses(tmp_path)

    assert summary["all_pass"] is True
    assert summary["license_family"] == "MIT"
    assert (tmp_path / "THIRD_PARTY_PLAYBACK_NOTICES.md").is_file()
    assert (tmp_path / "third_party" / "MuseScore_General_License.md").is_file()


def test_playback_license_audit_fails_without_package_notice(tmp_path: Path, monkeypatch) -> None:
    soundfont_dir = tmp_path / "soundfonts"
    soundfont_dir.mkdir()
    soundfont = soundfont_dir / "MuseScore_General.sf3"
    license_file = soundfont_dir / "MuseScore_General_License.md"
    readme_file = soundfont_dir / "MuseScore_General_Readme.md"
    soundfont.write_bytes(b"sf3")
    license_file.write_text("Permission is hereby granted.", encoding="utf-8")
    readme_file.write_text("readme", encoding="utf-8")
    monkeypatch.setattr(license_audit, "SOUNDFONT_FILE", soundfont)
    monkeypatch.setattr(license_audit, "SOUNDFONT_LICENSE", license_file)
    monkeypatch.setattr(license_audit, "SOUNDFONT_README", readme_file)

    summary = license_audit.audit_playback_licenses(tmp_path)

    assert summary["all_pass"] is False
    assert "Package is missing THIRD_PARTY_PLAYBACK_NOTICES.md" in summary["issues"]
