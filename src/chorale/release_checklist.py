from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def build_release_checklist(root: str | Path = ".") -> dict[str, object]:
    root_path = Path(root)
    manifest = read_json(root_path / "results" / "project1_delivery_release_manifest_latest.json")
    readiness = read_json(root_path / "results" / "project1_commercial_readiness_audit.json")
    release_gate = read_json(root_path / "results" / "project1_commercial_release_gate_latest.json")
    release_candidate = read_json(root_path / "results" / "project1_commercial_release_candidate_latest.json")
    acceptance = read_json(root_path / "results" / "project1_commercial_acceptance_report_latest.json")
    intake = read_json(root_path / "results" / "project1_expert_return_intake_report_latest.json")

    gates = readiness.get("gates", [])
    if not isinstance(gates, list):
        gates = []
    passed_gates = [gate for gate in gates if isinstance(gate, dict) and gate.get("passed") is True]
    blocked_gates = [
        gate
        for gate in gates
        if isinstance(gate, dict) and gate.get("blocking") is True and gate.get("passed") is not True
    ]

    status = {
        "engineering_delivery_score": manifest.get("commercial_delivery_score", "not available"),
        "engineering_release_candidate_ready": release_candidate.get("engineering_release_candidate_ready", "not available"),
        "customer_review_ready": release_candidate.get("customer_review_ready", "not available"),
        "commercial_readiness_score": readiness.get("commercial_readiness_score", "not available"),
        "release_status": release_gate.get("release_status", "not available"),
        "commercial_release_ready": release_gate.get("commercial_release_ready", False),
        "engineering_acceptance": acceptance.get("engineering_acceptance", "not available"),
        "commercial_release": acceptance.get("commercial_release", "not available"),
    }
    return {
        "schema": "project1_release_checklist_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "manifest": manifest,
        "readiness": readiness,
        "release_candidate": release_candidate,
        "release_gate": release_gate,
        "expert_intake": intake,
        "passed_gates": passed_gates,
        "blocked_gates": blocked_gates,
    }


def make_markdown(report: dict[str, object]) -> str:
    manifest = ensure_dict(report.get("manifest"))
    readiness = ensure_dict(report.get("readiness"))
    release_gate = ensure_dict(report.get("release_gate"))
    status = ensure_dict(report.get("status"))
    passed_gates = [item for item in report.get("passed_gates", []) if isinstance(item, dict)]
    blocked_gates = [item for item in report.get("blocked_gates", []) if isinstance(item, dict)]

    lines = [
        "# Project1 商用 100/100 发布清单",
        "",
        "本清单由当前审计证据自动生成，用于确认 Project1 是否可以从工程交付候选进入正式商用发布。不得用自动生成文件替代真实专家评分或真实法务/商业签核。",
        "",
        "## 当前状态",
        "",
        f"- 工程交付包：`{status.get('engineering_delivery_score')}/100`",
        f"- 工程候选包就绪：`{status.get('engineering_release_candidate_ready')}`",
        f"- 真实浏览器客户评审就绪：`{status.get('customer_review_ready')}`",
        f"- 总商业就绪：`{status.get('commercial_readiness_score')}/100`",
        f"- 最终发布门禁：`{status.get('release_status')}`",
        f"- 商业发布就绪：`{status.get('commercial_release_ready')}`",
        f"- 工程验收：`{status.get('engineering_acceptance')}`",
        f"- 商业验收：`{status.get('commercial_release')}`",
        f"- 最新交付 ZIP：`{manifest.get('zip_file', 'not available')}`",
        f"- ZIP SHA256：`{manifest.get('zip_sha256', 'not available')}`",
        f"- ZIP 普通文件数：`{manifest.get('zip_regular_file_count', 'not available')}`",
        f"- 完整性 manifest 校验：`{manifest.get('zip_integrity_checked_file_count', 'not available')}/{manifest.get('zip_integrity_checked_file_count', 'not available')}`",
        f"- MP3/MIDI/WAV：`{manifest.get('mp3_count', 'not available')}/{manifest.get('midi_count', 'not available')}/{manifest.get('wav_count', 'not available')}`",
        f"- 谱例数与播放清单行数：`{manifest.get('score_count', 'not available')}` / `{manifest.get('manifest_rows', 'not available')}`",
        "",
        "## 已通过的证据门",
        "",
    ]
    if passed_gates:
        for gate in passed_gates:
            lines.append(
                f"- `{gate.get('gate')}` ({gate.get('weight')} 分): {gate.get('status')}；证据 `{gate.get('evidence')}`"
            )
    else:
        lines.append("- 当前没有可读取的通过项。")

    lines.extend(["", "## 未通过或仍需外部证据的门", ""])
    if blocked_gates:
        for gate in blocked_gates:
            lines.append(
                f"- `{gate.get('gate')}` ({gate.get('weight')} 分): {gate.get('status')}；证据 `{gate.get('evidence')}`"
            )
    else:
        lines.append("- 当前没有阻塞项。")

    release_blockers = release_gate.get("blocking_items", [])
    if not isinstance(release_blockers, list):
        release_blockers = []
    lines.extend(["", "## 最终 release gate 阻塞项", ""])
    if release_blockers:
        lines.extend(f"- `{item}`" for item in release_blockers)
    else:
        lines.append("- 无。")

    lines.extend(
        [
            "",
            "## 专家评分回收要求",
            "",
            "回收文件放入：",
            "",
            "```text",
            "expert_eval/project1/returned_ratings/",
            "```",
            "",
            "正式汇总前必须满足：",
            "",
            "- 至少 3 份有效专家评分工作簿。",
            "- 每份工作簿来自不同的 `rater_id`。",
            "- 每份工作簿同时包含完整的逐首评分和 A/B 配对比较。",
            "- 不得把 `-AllowPreliminary` 生成的 pending 表当作正式专家结果。",
            "",
            "运行：",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\validate_project1_expert_returns.ps1",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\summarize_project1_expert_ratings.ps1",
            "```",
            "",
            "## 法务/商业签核要求",
            "",
            "完成 `results/project1_commercial_legal_review_packet/` 中的人工审查后，才可以根据模板创建：",
            "",
            "```text",
            "results/project1_commercial_legal_signoff.json",
            "```",
            "",
            "First write a release-bound unapproved draft:",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\write_project1_commercial_legal_signoff_draft.ps1",
            "```",
            "",
            "The draft is only a prefilled review aid. It must remain unapproved until a real responsible reviewer completes the manual checks, copies the completed final file to `results/project1_commercial_legal_signoff.json`, and signs it.",
            "",
            "The signoff must also bind to the immutable release artifact:",
            "",
            f"- `delivery_zip`: `{manifest.get('zip_file', 'not available')}`",
            f"- `delivery_zip_sha256`: `{manifest.get('zip_sha256', 'not available')}`",
            "",
            "该文件必须真实填写 `reviewer_name`、`reviewer_role`、`review_date`，且 `approved_for_commercial_distribution` 和所有 `required_checks` 均为 `true`。",
            "",
            "Validate the completed final signoff before release:",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\validate_project1_commercial_legal_signoff.ps1 -Strict",
            "```",
            "",
            "## 最终放行命令",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\audit_project1_commercial_readiness.ps1",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\write_project1_commercial_acceptance_report.ps1",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\check_project1_commercial_release_gate.ps1 -Strict",
            "```",
            "",
            "只有最后一条命令成功退出，才可以声明：",
            "",
            "```text",
            "commercial_release_ready = true",
            "release_score = 100/100",
            "```",
            "",
            "## 禁止表述",
            "",
            "在专家评分和法务/商业签核完成前，不得对外写：",
            "",
            "- “已经商用发布”",
            "- “专家验证通过”",
            "- “法务审核通过”",
            "- “世界顶级音乐生成”",
            "- “真人合唱音频生成”",
            "",
            "当前可诚实表述为：",
            "",
            "```text",
            "Project1 已形成可审查的 score-level SATB 和声化工程交付包，包含 MusicXML/PDF 谱例、谱面派生 MP3/MIDI 辅助试听、谱面-播放一致性审计、离线播放器、专家评分材料和法律审查包。工程交付审计为 100/100；商业发布仍需真实专家评分回收和法务/商业签核。",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def make_clean_markdown(report: dict[str, object]) -> str:
    manifest = ensure_dict(report.get("manifest"))
    readiness = ensure_dict(report.get("readiness"))
    release_gate = ensure_dict(report.get("release_gate"))
    status = ensure_dict(report.get("status"))
    passed_gates = [item for item in report.get("passed_gates", []) if isinstance(item, dict)]
    blocked_gates = [item for item in report.get("blocked_gates", []) if isinstance(item, dict)]

    lines = [
        "# Project1 商用 100/100 发布清单",
        "",
        "本清单由当前审计证据自动生成，用于判断 Project1 是否可以从工程交付候选进入正式商业发布。"
        "自动生成文件不能替代真实专家评分、真实法务/商业签核或人工验收。",
        "",
        "## 当前状态",
        "",
        f"- 工程交付包：`{status.get('engineering_delivery_score')}/100`",
        f"- 工程候选包就绪：`{status.get('engineering_release_candidate_ready')}`",
        f"- 真实浏览器客户评审就绪：`{status.get('customer_review_ready')}`",
        f"- 总商用准备度：`{status.get('commercial_readiness_score')}/100`",
        f"- 最终发布门状态：`{status.get('release_status')}`",
        f"- 商业发布就绪：`{status.get('commercial_release_ready')}`",
        f"- 工程验收：`{status.get('engineering_acceptance')}`",
        f"- 商业验收：`{status.get('commercial_release')}`",
        f"- 最新交付 ZIP：`{manifest.get('zip_file', 'not available')}`",
        f"- ZIP SHA256：`{manifest.get('zip_sha256', 'not available')}`",
        f"- ZIP 普通文件数：`{manifest.get('zip_regular_file_count', 'not available')}`",
        f"- 完整性 manifest 校验：`{manifest.get('zip_integrity_checked_file_count', 'not available')}/{manifest.get('zip_integrity_checked_file_count', 'not available')}`",
        f"- MP3/MIDI/WAV：`{manifest.get('mp3_count', 'not available')}/{manifest.get('midi_count', 'not available')}/{manifest.get('wav_count', 'not available')}`",
        f"- 谱例数 / 播放清单行数：`{manifest.get('score_count', 'not available')}` / `{manifest.get('manifest_rows', 'not available')}`",
        "",
        "## 已通过的证据门",
        "",
    ]
    if passed_gates:
        for gate in passed_gates:
            lines.append(
                f"- `{gate.get('gate')}` ({gate.get('weight')} 分)：{gate.get('status')}；证据 `{gate.get('evidence')}`"
            )
    else:
        lines.append("- 当前没有可读取的通过项。")

    lines.extend(["", "## 未通过或仍需外部证据的门", ""])
    if blocked_gates:
        for gate in blocked_gates:
            lines.append(
                f"- `{gate.get('gate')}` ({gate.get('weight')} 分)：{gate.get('status')}；证据 `{gate.get('evidence')}`"
            )
    else:
        lines.append("- 当前没有阻塞项。")

    release_blockers = release_gate.get("blocking_items", [])
    if not isinstance(release_blockers, list):
        release_blockers = []
    lines.extend(["", "## 最终 Release Gate 阻塞项", ""])
    if release_blockers:
        lines.extend(f"- `{item}`" for item in release_blockers)
    else:
        lines.append("- 无。")

    lines.extend(
        [
            "",
            "## 专家评分回收要求",
            "",
            "回收文件放入：",
            "",
            "```text",
            "expert_eval/project1/returned_ratings/",
            "```",
            "",
            "正式汇总前必须满足：",
            "",
            "- 至少 3 份有效专家评分工作簿。",
            "- 每份工作簿来自不同的 `rater_id`。",
            "- 每份工作簿同时包含完整的逐首评分和 A/B 配对比较。",
            "- 不得把 `-AllowPreliminary` 生成的 pending 表当作正式专家结果。",
            "",
            "运行：",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\validate_project1_expert_returns.ps1",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\summarize_project1_expert_ratings.ps1",
            "```",
            "",
            "## 法务/商业签核要求",
            "",
            "完成 `results/project1_commercial_legal_review_packet/` 中的人工审查后，才可以根据模板创建：",
            "",
            "```text",
            "results/project1_commercial_legal_signoff.json",
            "```",
            "",
            "先写入绑定当前 release 的未批准草稿：",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\write_project1_commercial_legal_signoff_draft.ps1",
            "```",
            "",
            "草稿只是预填审核材料。只有真实责任人完成手工检查、复制最终文件到 "
            "`results/project1_commercial_legal_signoff.json` 并签署后，才能视为有效签核。",
            "",
            "签核文件必须绑定不可变 release artifact：",
            "",
            f"- `delivery_zip`: `{manifest.get('zip_file', 'not available')}`",
            f"- `delivery_zip_sha256`: `{manifest.get('zip_sha256', 'not available')}`",
            "",
            "该文件必须真实填写 `reviewer_name`、`reviewer_role`、`review_date`，且 "
            "`approved_for_commercial_distribution` 和所有 `required_checks` 均为 `true`。",
            "",
            "正式发布前校验最终签核：",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\validate_project1_commercial_legal_signoff.ps1 -Strict",
            "```",
            "",
            "## 最终放行命令",
            "",
            "```powershell",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\audit_project1_commercial_readiness.ps1",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\write_project1_commercial_acceptance_report.ps1",
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\check_project1_commercial_release_gate.ps1 -Strict",
            "```",
            "",
            "只有最后一条命令成功退出，才可以声明：",
            "",
            "```text",
            "commercial_release_ready = true",
            "release_score = 100/100",
            "```",
            "",
            "## 禁止表述",
            "",
            "在专家评分和法务/商业签核完成前，不得对外写：",
            "",
            "- 已经商业发布",
            "- 专家验证通过",
            "- 法务审核通过",
            "- 世界顶级音乐生成",
            "- 真人合唱音频生成",
            "",
            "当前可以诚实表述为：",
            "",
            "```text",
            "Project1 已形成可审查的 score-level SATB 和声化工程交付包，包含 MusicXML/PDF 谱例、"
            "谱面派生 MP3/MIDI 辅助试听、谱面/播放一致性审计、离线播放器、专家评分材料和法务审查包。"
            "工程交付审计通过；商业发布仍需真实专家评分回收和法务/商业签核。",
            "```",
        ]
    )
    return "\n".join(lines) + "\n"


def write_release_checklist(root: str | Path = ".", out_path: str | Path = "docs/project1_100_point_release_checklist.md") -> dict[str, str]:
    report = build_release_checklist(root)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(make_clean_markdown(report), encoding="utf-8-sig")
    json_path = out.with_suffix(".json")
    json_path.write_text(json.dumps(strip_large_fields(report), indent=2, ensure_ascii=False), encoding="utf-8")
    return {"markdown": str(out), "json": str(json_path)}


def strip_large_fields(report: dict[str, object]) -> dict[str, object]:
    return {
        "schema": report.get("schema"),
        "generated_at_utc": report.get("generated_at_utc"),
        "status": report.get("status"),
        "zip_file": ensure_dict(report.get("manifest")).get("zip_file"),
        "zip_sha256": ensure_dict(report.get("manifest")).get("zip_sha256"),
        "commercial_readiness_score": ensure_dict(report.get("readiness")).get("commercial_readiness_score"),
        "release_status": ensure_dict(report.get("release_gate")).get("release_status"),
        "blocking_items": ensure_dict(report.get("release_gate")).get("blocking_items", []),
    }


def read_json(path: Path) -> dict[str, object]:
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    return value if isinstance(value, dict) else {}


def ensure_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the current Project1 commercial 100/100 release checklist.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--out", default="docs/project1_100_point_release_checklist.md")
    args = parser.parse_args()
    outputs = write_release_checklist(args.root, args.out)
    print(json.dumps({"outputs": outputs}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
