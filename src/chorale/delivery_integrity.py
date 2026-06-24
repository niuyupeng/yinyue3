from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import zipfile
from typing import Protocol


MANIFEST_JSON = "DELIVERY_FILE_MANIFEST.json"
MANIFEST_SHA256 = "DELIVERY_FILE_MANIFEST.sha256"
REPORT_JSON = "DELIVERY_INTEGRITY_REPORT.json"
REPORT_MD = "DELIVERY_INTEGRITY_REPORT.md"
RECIPIENT_REPORT_JSON = "DELIVERY_INTEGRITY_RECIPIENT_REPORT.json"
RECIPIENT_REPORT_MD = "DELIVERY_INTEGRITY_RECIPIENT_REPORT.md"
OPEN_PACKAGE_REPORT_JSON = "OPEN_PACKAGE_REPORT.json"
PACKAGE_SELF_TEST_REPORT_JSON = "PACKAGE_SELF_TEST_REPORT.json"
PACKAGE_SELF_TEST_REPORT_MD = "PACKAGE_SELF_TEST_REPORT.md"
EXCLUDED_NAMES = {
    MANIFEST_JSON,
    MANIFEST_SHA256,
    REPORT_JSON,
    REPORT_MD,
    RECIPIENT_REPORT_JSON,
    RECIPIENT_REPORT_MD,
    OPEN_PACKAGE_REPORT_JSON,
    PACKAGE_SELF_TEST_REPORT_JSON,
    PACKAGE_SELF_TEST_REPORT_MD,
}


class PackageReader(Protocol):
    label: str

    def exists(self, path: str) -> bool: ...

    def read_bytes(self, path: str) -> bytes: ...

    def list_files(self) -> list[str]: ...


class DirReader:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.label = str(self.root)
        if not self.root.is_dir():
            raise NotADirectoryError(f"Package directory not found: {self.root}")

    def exists(self, path: str) -> bool:
        return (self.root / path).is_file()

    def read_bytes(self, path: str) -> bytes:
        return (self.root / path).read_bytes()

    def list_files(self) -> list[str]:
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in self.root.rglob("*")
            if path.is_file() and path.name not in EXCLUDED_NAMES
        )


class ZipReader:
    def __init__(self, zip_file: str | Path):
        self.zip_file = Path(zip_file)
        self.label = str(self.zip_file)
        if not self.zip_file.is_file():
            raise FileNotFoundError(f"ZIP file not found: {self.zip_file}")
        with zipfile.ZipFile(self.zip_file) as archive:
            names = [item.filename.replace("\\", "/") for item in archive.infolist() if not item.is_dir()]
        roots = {name.split("/", 1)[0] for name in names if "/" in name}
        prefix = ""
        if len(roots) == 1 and all(name.startswith(next(iter(roots)) + "/") for name in names):
            prefix = next(iter(roots)) + "/"
        self._prefix = prefix
        self._names = {self._strip_prefix(name) for name in names}

    def _strip_prefix(self, name: str) -> str:
        return name[len(self._prefix) :] if self._prefix and name.startswith(self._prefix) else name

    def _archive_name(self, path: str) -> str:
        return self._prefix + path.replace("\\", "/")

    def exists(self, path: str) -> bool:
        return path.replace("\\", "/") in self._names

    def read_bytes(self, path: str) -> bytes:
        with zipfile.ZipFile(self.zip_file) as archive:
            return archive.read(self._archive_name(path))

    def list_files(self) -> list[str]:
        return sorted(name for name in self._names if Path(name).name not in EXCLUDED_NAMES)


def build_manifest(package_dir: str | Path) -> dict[str, object]:
    package = Path(package_dir)
    if not package.is_dir():
        raise NotADirectoryError(f"Package directory not found: {package}")
    files = []
    for path in sorted(package.rglob("*")):
        if not path.is_file() or path.name in EXCLUDED_NAMES:
            continue
        rel = path.relative_to(package).as_posix()
        files.append(
            {
                "path": rel,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return {
        "schema": "project1_delivery_file_manifest_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "package_dir_name": package.name,
        "file_count": len(files),
        "files": files,
    }


def write_manifest(package_dir: str | Path) -> dict[str, str]:
    package = Path(package_dir)
    manifest = build_manifest(package)
    json_path = package / MANIFEST_JSON
    sha_path = package / MANIFEST_SHA256
    json_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"{item['sha256']}  {item['path']}" for item in manifest["files"] if isinstance(item, dict)]
    sha_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"manifest_json": str(json_path), "manifest_sha256": str(sha_path)}


def verify_manifest(package_dir: str | Path, manifest_path: str | Path | None = None) -> dict[str, object]:
    package = DirReader(package_dir)
    manifest_file = str(manifest_path) if manifest_path else MANIFEST_JSON
    return verify_reader(package, manifest_file)


def verify_zip_manifest(zip_file: str | Path, manifest_path: str = MANIFEST_JSON) -> dict[str, object]:
    package = ZipReader(zip_file)
    return verify_reader(package, manifest_path)


def verify_reader(package: PackageReader, manifest_path: str = MANIFEST_JSON) -> dict[str, object]:
    manifest_file = manifest_path.replace("\\", "/")
    if not package.exists(manifest_file):
        return {
            "all_pass": False,
            "status": "manifest missing",
            "package": package.label,
            "manifest": manifest_file,
            "expected_file_count": 0,
            "checked_file_count": 0,
            "missing_files": [manifest_file],
            "changed_files": [],
            "extra_files": [],
        }
    manifest = json.loads(package.read_bytes(manifest_file).decode("utf-8-sig"))
    expected = manifest.get("files", [])
    expected_paths: set[str] = set()
    missing: list[str] = []
    changed: list[str] = []
    checked = 0
    for item in expected if isinstance(expected, list) else []:
        if not isinstance(item, dict):
            continue
        rel = str(item.get("path", ""))
        expected_paths.add(rel)
        if not package.exists(rel):
            missing.append(rel)
            continue
        checked += 1
        size = int(item.get("size_bytes", -1))
        digest = str(item.get("sha256", ""))
        data = package.read_bytes(rel)
        if len(data) != size or sha256_bytes(data) != digest:
            changed.append(rel)
    actual_paths = set(package.list_files())
    extra = sorted(actual_paths - expected_paths)
    all_pass = not missing and not changed and not extra and checked == len(expected_paths)
    return {
        "all_pass": all_pass,
        "status": "pass" if all_pass else "failed",
        "package": package.label,
        "manifest": manifest_file,
        "expected_file_count": len(expected_paths),
        "checked_file_count": checked,
        "missing_files": missing,
        "changed_files": changed,
        "extra_files": extra,
    }


def write_report(report: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(report), encoding="utf-8")
    return {"json": str(out_json), "markdown": str(out_md)}


def make_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Delivery Integrity Verification",
        "",
        f"Status: {report.get('status')}",
        f"All pass: {report.get('all_pass')}",
        f"Package: `{report.get('package') or report.get('package_dir')}`",
        f"Manifest: `{report.get('manifest')}`",
        f"Expected files: {report.get('expected_file_count')}",
        f"Checked files: {report.get('checked_file_count')}",
        "",
    ]
    for label, key in [("Missing files", "missing_files"), ("Changed files", "changed_files"), ("Extra files", "extra_files")]:
        values = report.get(key, [])
        if isinstance(values, list) and values:
            lines.extend([f"## {label}", ""])
            lines.extend(f"- {value}" for value in values[:200])
            lines.append("")
    if report.get("all_pass"):
        lines.append("No delivery integrity issues detected.")
    return "\n".join(lines) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or verify Project1 delivery file integrity manifests.")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--package-dir")
    src.add_argument("--zip-file")
    parser.add_argument("--write", action="store_true", help="Write DELIVERY_FILE_MANIFEST files into the package.")
    parser.add_argument("--verify", action="store_true", help="Verify package files against DELIVERY_FILE_MANIFEST.json.")
    parser.add_argument("--manifest-json", default="")
    parser.add_argument("--out-json", default="")
    args = parser.parse_args()
    if not args.write and not args.verify:
        parser.error("Choose --write and/or --verify.")
    if args.write and args.zip_file:
        parser.error("--write is only supported with --package-dir.")

    result: dict[str, object] = {}
    if args.write:
        result["written"] = write_manifest(args.package_dir)
    if args.verify:
        if args.package_dir:
            report = verify_manifest(args.package_dir, args.manifest_json or None)
        else:
            report = verify_zip_manifest(args.zip_file, args.manifest_json or MANIFEST_JSON)
        result["verification"] = report
        if args.out_json:
            result["report"] = write_report(report, args.out_json)
        if not report["all_pass"]:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            raise SystemExit(1)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
