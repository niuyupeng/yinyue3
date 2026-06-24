from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
SOUNDFONT_DIR = REPO_ROOT / "external_tools" / "soundfonts"
SOUNDFONT_FILE = SOUNDFONT_DIR / "MuseScore_General.sf3"
SOUNDFONT_LICENSE = SOUNDFONT_DIR / "MuseScore_General_License.md"
SOUNDFONT_README = SOUNDFONT_DIR / "MuseScore_General_Readme.md"


def audit_playback_licenses(package_dir: str | Path | None = None) -> dict[str, object]:
    package = Path(package_dir) if package_dir else None
    issues: list[str] = []
    warnings: list[str] = []

    soundfont_exists = SOUNDFONT_FILE.is_file()
    license_exists = SOUNDFONT_LICENSE.is_file()
    readme_exists = SOUNDFONT_README.is_file()
    license_text = SOUNDFONT_LICENSE.read_text(encoding="utf-8", errors="replace") if license_exists else ""

    if not soundfont_exists:
        issues.append(f"SoundFont not found: {SOUNDFONT_FILE}")
    if not license_exists:
        issues.append(f"SoundFont license not found: {SOUNDFONT_LICENSE}")
    if not readme_exists:
        warnings.append(f"SoundFont README not found: {SOUNDFONT_README}")
    if license_exists and "MIT license" not in license_text and "Permission is hereby granted" not in license_text:
        issues.append("SoundFont license text does not contain expected MIT license indicators")
    if license_exists and "acknowledgements and copyright notices" not in license_text:
        warnings.append("SoundFont license text did not contain the expected attribution reminder")

    package_notice_present = False
    package_license_present = False
    if package is not None:
        package_notice_present = (package / "THIRD_PARTY_PLAYBACK_NOTICES.md").is_file()
        package_license_present = (package / "third_party" / "MuseScore_General_License.md").is_file()
        if not package_notice_present:
            issues.append("Package is missing THIRD_PARTY_PLAYBACK_NOTICES.md")
        if not package_license_present:
            issues.append("Package is missing third_party/MuseScore_General_License.md")

    return {
        "license_audit_score": 100 if not issues else max(0, 100 - len(issues) * 20),
        "all_pass": not issues,
        "soundfont": str(SOUNDFONT_FILE),
        "soundfont_exists": soundfont_exists,
        "soundfont_license": str(SOUNDFONT_LICENSE),
        "soundfont_license_exists": license_exists,
        "soundfont_readme_exists": readme_exists,
        "license_family": "MIT" if license_exists and "Permission is hereby granted" in license_text else "unknown",
        "package_notice_present": package_notice_present,
        "package_license_present": package_license_present,
        "issues": issues,
        "warnings": warnings,
        "note": "This audit checks local attribution files for score-derived playback assets; it is not legal advice.",
    }


def write_package_notices(package_dir: str | Path) -> None:
    package = Path(package_dir)
    third_party = package / "third_party"
    third_party.mkdir(parents=True, exist_ok=True)
    if SOUNDFONT_LICENSE.is_file():
        (third_party / "MuseScore_General_License.md").write_text(SOUNDFONT_LICENSE.read_text(encoding="utf-8"), encoding="utf-8")
    if SOUNDFONT_README.is_file():
        (third_party / "MuseScore_General_Readme.md").write_text(SOUNDFONT_README.read_text(encoding="utf-8"), encoding="utf-8")
    notice = """# Third-Party Playback Notices

This Project1 delivery package contains score-derived MP3 playback rendered from SATB MusicXML files.

The MP3 files were rendered locally for expert/customer review. They are not neural audio generation outputs and are not intended to claim human vocal realism.

## SoundFont

- SoundFont used during rendering: MuseScore_General.sf3
- Local source path during rendering: external_tools/soundfonts/MuseScore_General.sf3
- License family detected from local license file: MIT
- Included notice files:
  - third_party/MuseScore_General_License.md
  - third_party/MuseScore_General_Readme.md

The MuseScore General/FluidR3 notices require copyright acknowledgements to be preserved in derivative work. Keep these notice files with any redistributed expert/customer playback package.

## Rendering Tools

The delivery ZIP includes rendered MP3/MIDI/MusicXML/PDF assets. It does not redistribute FluidSynth, MuseScore, FFmpeg, or the SoundFont binary.

This notice is an engineering compliance aid, not legal advice. For paid commercial redistribution, perform a final legal review of third-party licenses and distribution terms.
"""
    (package / "THIRD_PARTY_PLAYBACK_NOTICES.md").write_text(notice, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit and optionally write third-party playback notices.")
    parser.add_argument("--package-dir", default="")
    parser.add_argument("--write-notices", action="store_true")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()
    if args.write_notices:
        if not args.package_dir:
            raise SystemExit("--write-notices requires --package-dir")
        write_package_notices(args.package_dir)
    summary = audit_playback_licenses(args.package_dir or None)
    if args.out_json:
        out = Path(args.out_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if not summary["all_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
