from __future__ import annotations

import csv
from pathlib import Path

from chorale.review_issue_intake import intake_review_issues, write_outputs
from tests.test_delivery_issue_debugger import make_package, write_simple_satb_score


def test_review_issue_intake_matches_returned_issue_to_delivery_manifest(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")
    write_simple_satb_score(package / "absolute_score_musicxml" / "P1S01.musicxml")
    write_simple_satb_score(package / "render_xml" / "absolute" / "P1S01" / "P1S01_stem_alto.musicxml")
    issues_dir = tmp_path / "returned_issues"
    write_issue_csv(
        issues_dir / "rater01_issues.csv",
        [
            {
                "问题编号": "I001",
                "谱例编号(score_id)": "P1S01",
                "材料类型(absolute/paired)": "absolute",
                "音频版本": "stem_alto",
                "问题时间点(秒)": "12.5",
                "问题类别": "音频与谱面疑似不一致",
                "严重程度(1-5)": "4",
                "具体描述": "女低声部听起来需要复核",
                "是否影响评分": "是",
                "反馈人": "Rater01",
                "备注": "第8小节附近",
            }
        ],
    )

    report = intake_review_issues(issues_dir, package_dir=package)

    assert report["status"] == "ready_for_triage"
    assert report["accepted_issue_count"] == 1
    assert report["matched_issue_count"] == 1
    assert report["high_severity_count"] == 1
    row = report["rows"][0]
    assert row["manifest_match"] is True
    assert row["automatic_item_status"] == "pass"
    assert row["mp3"].endswith("P1S01_stem_alto.mp3")
    assert row["estimated_measure"] == 1
    assert row["estimated_beat"] == 5.0
    assert "G4" in row["render_nearby_pitches"]
    assert row["timepoint_issues"]


def test_review_issue_intake_flags_invalid_values(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")
    issues_dir = tmp_path / "returned_issues"
    write_issue_csv(
        issues_dir / "bad.csv",
        [
            {
                "问题编号": "I002",
                "谱例编号(score_id)": "P1S01",
                "音频版本": "alto",
                "严重程度(1-5)": "9",
                "具体描述": "",
            }
        ],
    )

    report = intake_review_issues(issues_dir, package_dir=package)

    assert report["status"] == "has_invalid_rows"
    assert report["invalid_issue_count"] == 1
    issues = " ".join(report["rows"][0]["validation_issues"])
    assert "invalid variant" in issues
    assert "severity must be 1-5" in issues
    assert "missing description" in issues


def test_review_issue_intake_handles_empty_issue_folder(tmp_path: Path) -> None:
    package = make_package(tmp_path, conformance_status="pass", media_status="pass")

    report = intake_review_issues(tmp_path / "missing_returned_issues", package_dir=package)
    outputs = write_outputs(report, tmp_path / "out" / "issues.json")

    assert report["status"] == "no_issue_files"
    assert report["accepted_issue_count"] == 0
    assert Path(outputs["json"]).is_file()
    assert Path(outputs["csv"]).is_file()
    assert Path(outputs["markdown"]).is_file()


def write_issue_csv(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "问题编号",
        "谱例编号(score_id)",
        "材料类型(absolute/paired)",
        "音频版本",
        "问题时间点(秒)",
        "问题类别",
        "严重程度(1-5)",
        "具体描述",
        "是否影响评分",
        "反馈人",
        "备注",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
