from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[path.stem] = module
    spec.loader.exec_module(module)
    return module


def test_experiment_matrix_marks_cih_as_pending_without_fake_results(tmp_path: Path) -> None:
    module = load_script("run_experiment_suite.py")
    rows = module.build_experiment_matrix(tmp_path)
    by_id = {row["experiment_id"]: row for row in rows}
    assert by_id["baseline_cih_s2s_bach_s2s"]["status"] == "pending"
    assert by_id["baseline_deepbach_style_pseudogibbs"]["status"] == "todo_not_implemented"
    assert "Do not report results" in by_id["baseline_coconet_style_infilling"]["claim_boundary"]


def test_statistical_summary_requires_paired_seed_data() -> None:
    module = load_script("statistical_tests.py")
    rows = module.comparison_rows(
        [
            {
                "model_family": "current_rule_guided_transformer",
                "seed": "2026",
                "formal_evidence": "true",
                "pitch_accuracy": "0.80",
            },
            {
                "model_family": "current_rule_guided_transformer",
                "seed": "2027",
                "formal_evidence": "true",
                "pitch_accuracy": "0.82",
            },
            {
                "model_family": "current_rule_guided_transformer",
                "seed": "2028",
                "formal_evidence": "true",
                "pitch_accuracy": "0.81",
            },
        ]
    )
    descriptive = [row for row in rows if row["comparison_id"] == "descriptive_current_rule_guided_transformer"]
    assert any(row["metric"] == "pitch_accuracy" and row["status"] == "descriptive_ci" for row in descriptive)
    planned = [row for row in rows if row["comparison_id"] == "current_rule_guided_vs_cih_s2s"]
    assert any(row["status"] == "pending_no_paired_seed_data" for row in planned)


def test_external_protocol_keeps_bcfb_and_cpdl_claim_boundaries() -> None:
    module = load_script("build_external_benchmark_manifest.py")
    text = module.protocol_markdown()
    assert "BCFB is Bach-related material" in text
    assert "Do not claim external-corpus robustness" in text
    assert "license" in text.lower()


def test_expert_packet_protocol_is_pending_until_returned_forms() -> None:
    module = load_script("generate_expert_eval_packet.py")
    text = module.protocol_markdown()
    assert "expert evaluation pending" in text
    assert "internal_key_do_not_send.csv" in text
    assert "Do not write that experts preferred a model" in text
