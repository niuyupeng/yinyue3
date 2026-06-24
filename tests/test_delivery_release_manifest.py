from __future__ import annotations

import json
import zipfile
from pathlib import Path

from chorale.delivery_release_manifest import build_release_manifest, verify_release_manifest, write_release_outputs


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_delivery_release_manifest_roundtrip(tmp_path: Path) -> None:
    zip_path = tmp_path / "delivery.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("a.txt", "alpha")
    _write_json(tmp_path / "folder.json", {"all_pass": True, "checked_file_count": 1})
    _write_json(tmp_path / "zip.json", {"all_pass": True, "checked_file_count": 1})
    _write_json(tmp_path / "audit.json", {"all_pass": True, "commercial_delivery_score": 100, "mp3_count": 1})

    manifest = build_release_manifest(
        zip_path,
        folder_integrity_report=tmp_path / "folder.json",
        zip_integrity_report=tmp_path / "zip.json",
        commercial_delivery_audit=tmp_path / "audit.json",
    )
    outputs = write_release_outputs(manifest, tmp_path / "release.json")
    result = verify_release_manifest(outputs["json"])

    assert result["all_pass"] is True
    assert manifest["zip_regular_file_count"] == 1
    assert (tmp_path / "release.sha256").is_file()


def test_delivery_release_manifest_detects_changed_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "delivery.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.writestr("a.txt", "alpha")
    _write_json(tmp_path / "folder.json", {"all_pass": True, "checked_file_count": 1})
    _write_json(tmp_path / "zip.json", {"all_pass": True, "checked_file_count": 1})
    _write_json(tmp_path / "audit.json", {"all_pass": True, "commercial_delivery_score": 100})
    manifest = build_release_manifest(
        zip_path,
        folder_integrity_report=tmp_path / "folder.json",
        zip_integrity_report=tmp_path / "zip.json",
        commercial_delivery_audit=tmp_path / "audit.json",
    )
    outputs = write_release_outputs(manifest, tmp_path / "release.json")
    with zipfile.ZipFile(zip_path, "a") as archive:
        archive.writestr("b.txt", "beta")

    result = verify_release_manifest(outputs["json"])

    assert result["all_pass"] is False
    assert any("SHA256" in issue or "size" in issue for issue in result["issues"])
