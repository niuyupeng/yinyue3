from __future__ import annotations

import argparse
import csv
import importlib.metadata as metadata
import json
from pathlib import Path


def read_requirements(path: str | Path = "requirements.txt") -> list[str]:
    req_path = Path(path)
    if not req_path.is_file():
        return []
    names: list[str] = []
    for raw in req_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(";", 1)[0].strip()
        for marker in ["==", ">=", "<=", "~=", ">", "<"]:
            if marker in name:
                name = name.split(marker, 1)[0].strip()
                break
        if name:
            names.append(name)
    return names


def collect_inventory(requirements_path: str | Path = "requirements.txt") -> dict[str, object]:
    rows = [collect_distribution(name) for name in read_requirements(requirements_path)]
    return {
        "schema": "project1_dependency_license_inventory_v1",
        "requirements_path": str(requirements_path),
        "package_count": len(rows),
        "unknown_license_count": sum(1 for row in rows if row["license"] == "unknown"),
        "packages": rows,
        "note": "License metadata is collected from installed Python package metadata. Unknown values require manual review and are not inferred.",
    }


def collect_distribution(name: str) -> dict[str, str]:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        return {
            "requirement": name,
            "distribution_name": name,
            "version": "not installed",
            "license": "unknown",
            "license_classifiers": "",
            "summary": "",
            "home_page": "",
        }
    meta = dist.metadata
    license_value = clean_metadata_value(meta.get("License") or "")
    classifiers = [
        classifier
        for classifier in meta.get_all("Classifier") or []
        if classifier.lower().startswith("license")
    ]
    return {
        "requirement": name,
        "distribution_name": meta.get("Name") or name,
        "version": dist.version,
        "license": license_value or infer_license_from_classifiers(classifiers) or "unknown",
        "license_classifiers": " | ".join(classifiers),
        "summary": clean_metadata_value(meta.get("Summary") or ""),
        "home_page": clean_metadata_value(meta.get("Home-page") or meta.get("Project-URL") or ""),
    }


def infer_license_from_classifiers(classifiers: list[str]) -> str:
    if not classifiers:
        return ""
    values = []
    for classifier in classifiers:
        values.append(classifier.split("::")[-1].strip())
    return "; ".join(sorted(set(values)))


def clean_metadata_value(value: str) -> str:
    return " ".join(str(value).split())


def write_inventory_outputs(inventory: dict[str, object], out_json: str | Path) -> dict[str, str]:
    out_json = Path(out_json)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    out_csv = out_json.with_suffix(".csv")
    packages = inventory.get("packages", [])
    if isinstance(packages, list):
        with out_csv.open("w", newline="", encoding="utf-8-sig") as handle:
            fieldnames = [
                "requirement",
                "distribution_name",
                "version",
                "license",
                "license_classifiers",
                "summary",
                "home_page",
            ]
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(row for row in packages if isinstance(row, dict))
    out_md = out_json.with_suffix(".md")
    out_md.write_text(make_markdown(inventory), encoding="utf-8")
    return {"json": str(out_json), "csv": str(out_csv), "markdown": str(out_md)}


def make_markdown(inventory: dict[str, object]) -> str:
    packages = inventory.get("packages", [])
    lines = [
        "# Project1 Dependency License Inventory",
        "",
        f"Package count: {inventory.get('package_count')}",
        f"Unknown license count: {inventory.get('unknown_license_count')}",
        "",
        "| Package | Version | License Metadata |",
        "|---|---:|---|",
    ]
    if isinstance(packages, list):
        for row in packages:
            if not isinstance(row, dict):
                continue
            lines.append(f"| {row.get('distribution_name')} | {row.get('version')} | {row.get('license')} |")
    lines.extend(["", str(inventory.get("note", "")), ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect Python dependency license metadata for Project1.")
    parser.add_argument("--requirements", default="requirements.txt")
    parser.add_argument("--out-json", default="results/project1_dependency_license_inventory.json")
    args = parser.parse_args()
    inventory = collect_inventory(args.requirements)
    outputs = write_inventory_outputs(inventory, args.out_json)
    print(json.dumps({"inventory": inventory, "outputs": outputs}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
