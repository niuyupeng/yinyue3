from __future__ import annotations

import zipfile
from pathlib import Path

from chorale.delivery_integrity import verify_manifest, verify_zip_manifest, write_manifest


def test_delivery_integrity_manifest_roundtrip(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    (tmp_path / "folder").mkdir()
    (tmp_path / "folder" / "b.txt").write_text("beta", encoding="utf-8")

    write_manifest(tmp_path)
    report = verify_manifest(tmp_path)

    assert report["all_pass"] is True
    assert report["expected_file_count"] == 2
    assert report["checked_file_count"] == 2


def test_delivery_integrity_detects_changed_file(tmp_path: Path) -> None:
    file_path = tmp_path / "a.txt"
    file_path.write_text("alpha", encoding="utf-8")
    write_manifest(tmp_path)
    file_path.write_text("changed", encoding="utf-8")

    report = verify_manifest(tmp_path)

    assert report["all_pass"] is False
    assert report["changed_files"] == ["a.txt"]


def test_delivery_integrity_verifies_zip_with_embedded_manifest(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "a.txt").write_text("alpha", encoding="utf-8")
    write_manifest(package)
    zip_path = tmp_path / "package.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        for item in package.rglob("*"):
            archive.write(item, item.relative_to(package).as_posix())

    report = verify_zip_manifest(zip_path)

    assert report["all_pass"] is True
    assert report["expected_file_count"] == 1
    assert report["checked_file_count"] == 1


def test_delivery_integrity_detects_changed_zip_member(tmp_path: Path) -> None:
    package = tmp_path / "package"
    package.mkdir()
    (package / "a.txt").write_text("alpha", encoding="utf-8")
    write_manifest(package)
    zip_path = tmp_path / "package_changed.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        archive.write(package / "DELIVERY_FILE_MANIFEST.json", "DELIVERY_FILE_MANIFEST.json")
        archive.write(package / "DELIVERY_FILE_MANIFEST.sha256", "DELIVERY_FILE_MANIFEST.sha256")
        archive.writestr("a.txt", "changed")

    report = verify_zip_manifest(zip_path)

    assert report["all_pass"] is False
    assert report["changed_files"] == ["a.txt"]


def test_delivery_integrity_allows_local_open_package_report(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    write_manifest(tmp_path)
    (tmp_path / "OPEN_PACKAGE_REPORT.json").write_text("{}", encoding="utf-8")

    report = verify_manifest(tmp_path)

    assert report["all_pass"] is True
    assert report["extra_files"] == []


def test_delivery_integrity_still_detects_unknown_extra_file(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("alpha", encoding="utf-8")
    write_manifest(tmp_path)
    (tmp_path / "unexpected.txt").write_text("extra", encoding="utf-8")

    report = verify_manifest(tmp_path)

    assert report["all_pass"] is False
    assert report["extra_files"] == ["unexpected.txt"]
