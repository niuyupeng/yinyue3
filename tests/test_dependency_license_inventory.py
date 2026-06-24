from __future__ import annotations

from pathlib import Path

from chorale.dependency_license_inventory import collect_inventory, read_requirements, write_inventory_outputs


def test_read_requirements_extracts_names(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("numpy>=1.23\n# comment\nPyYAML==6.0\n", encoding="utf-8")

    assert read_requirements(req) == ["numpy", "PyYAML"]


def test_collect_inventory_handles_missing_package(tmp_path: Path) -> None:
    req = tmp_path / "requirements.txt"
    req.write_text("definitely_missing_project1_package_zzz>=1\n", encoding="utf-8")

    inventory = collect_inventory(req)

    assert inventory["package_count"] == 1
    package = inventory["packages"][0]
    assert package["version"] == "not installed"
    assert package["license"] == "unknown"


def test_write_inventory_outputs(tmp_path: Path) -> None:
    inventory = {
        "package_count": 1,
        "unknown_license_count": 0,
        "packages": [
            {
                "requirement": "x",
                "distribution_name": "x",
                "version": "1",
                "license": "MIT",
                "license_classifiers": "",
                "summary": "",
                "home_page": "",
            }
        ],
        "note": "test",
    }
    outputs = write_inventory_outputs(inventory, tmp_path / "inventory.json")

    assert Path(outputs["json"]).is_file()
    assert Path(outputs["csv"]).is_file()
    assert Path(outputs["markdown"]).is_file()
