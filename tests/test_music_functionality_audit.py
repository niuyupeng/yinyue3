from __future__ import annotations

import json
from pathlib import Path

from chorale.data.score_tokenizer import ScoreTokenizer
from chorale.export_musicxml import export_tokens_to_musicxml
from chorale.music_functionality_audit import build_music_functionality_audit
from tests.test_score_tokenizer import tiny_satb_score


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def make_complete_evidence(root: Path) -> None:
    tokenizer = ScoreTokenizer(max_seq_len=32)
    encoded = tokenizer.encode_score(tiny_satb_score(), name="tiny")
    batch_rows = []
    for idx in range(3):
        score_dir = root / "generated_scores" / "batch" / f"score{idx}"
        musicxml = score_dir / "score.musicxml"
        rule_report = score_dir / "rule_report.json"
        summary = score_dir / "summary.json"
        musicxml.parent.mkdir(parents=True, exist_ok=True)
        export_tokens_to_musicxml(
            encoded["tokens"],
            tokenizer,
            musicxml,
            length=int(encoded["length"]),
            title=f"Tiny SATB {idx}",
        )
        for path in [rule_report, summary]:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("{}", encoding="utf-8")
        batch_rows.append(
            {
                "score_id": f"score{idx}",
                "status": "ok",
                "quality_status": "pass",
                "engine": "neural_checkpoint:best.pt",
                "input_preflight_status": "pass",
                "harmonized_musicxml": str(musicxml.relative_to(root)),
                "rule_report_json": str(rule_report.relative_to(root)),
                "summary_json": str(summary.relative_to(root)),
                "score_parse_ok": True,
                "score_part_count": 4,
                "score_note_count": 100,
                "known_voices": "soprano",
                "known_voice_preservation_pass": True,
                "known_voice_mismatches": 0,
                "violations_per_100_timesteps": 6.0,
                "symbolic_repair_enabled": True,
                "symbolic_accepted_repairs": 2,
                "cadential_repair_enabled": True,
                "cadence_type": "tonic_closure_like",
            }
        )
    write_json(
        root / "generated_scores" / "batch" / "summary.json",
        {
            "completed": 3,
            "failed": 0,
            "quality_pass": 3,
            "needs_review": 0,
            "all_quality_pass": True,
            "rows": batch_rows,
        },
    )
    write_json(
        root / "results" / "project1_delivery_media_audit_latest.json",
        {
            "all_pass": True,
            "media_delivery_score": 100,
            "entry_count": 240,
            "mp3_parse_ok_count": 240,
            "midi_parse_ok_count": 240,
            "max_abs_duration_delta_sec": 0.0,
        },
    )
    write_json(
        root / "results" / "project1_delivery_conformance_audit_latest.json",
        {
            "all_pass": True,
            "conformance_score": 100,
            "entry_count": 240,
            "mp3_audible_count": 240,
            "midi_render_pitch_check_pass_count": 240,
            "stem_target_check_pass_count": 240,
            "event_alignment_pass_count": 240,
            "min_pitch_similarity": 0.95,
            "min_event_recall": 1.0,
            "min_event_precision": 1.0,
            "min_duration_similarity": 1.0,
            "min_mp3_rms": 0.1,
        },
    )
    write_json(
        root / "results" / "project1_pro_playback_traceability_audit_latest.json",
        {
            "all_pass": True,
            "score_audio_traceability_score": 100,
            "summary": {
                "entry_count": 240,
                "score_count": 40,
                "fail_count": 0,
                "issue_count": 0,
                "by_variant": {
                    "full_choir": 40,
                    "piano_reference": 40,
                    "stem_soprano": 40,
                    "stem_alto": 40,
                    "stem_tenor": 40,
                    "stem_bass": 40,
                },
            },
        },
    )
    write_json(
        root / "results" / "project1_delivery_player_static_audit_latest.json",
        {
            "all_pass": True,
            "score_count": 40,
            "manifest_rows": 240,
            "missing_reference_count": 0,
            "bad_text_file_count": 0,
            "variant_counts": {
                "full_choir": 40,
                "piano_reference": 40,
                "stem_soprano": 40,
                "stem_alto": 40,
                "stem_tenor": 40,
                "stem_bass": 40,
            },
        },
    )
    screenshot = root / "results" / "browser.png"
    screenshot.write_bytes(b"png")
    write_json(
        root / "results" / "project1_delivery_player_qa_latest.json",
        {
            "status": "pass",
            "browser": "edge",
            "nav_items": 40,
            "audio_controls_initial": 7,
            "audio_controls_after_search": 7,
            "screenshot": str(screenshot.relative_to(root)),
            "issues": [],
        },
    )


def test_music_functionality_audit_reaches_100_when_evidence_is_complete(tmp_path: Path) -> None:
    make_complete_evidence(tmp_path)

    report = build_music_functionality_audit(tmp_path, batch_summary="generated_scores/batch/summary.json")

    assert report["music_functionality_score"] == 100
    assert report["all_pass"] is True
    assert report["blocking_items"] == []


def test_music_functionality_audit_blocks_without_real_browser_screenshot(tmp_path: Path) -> None:
    make_complete_evidence(tmp_path)
    (tmp_path / "results" / "browser.png").unlink()

    report = build_music_functionality_audit(tmp_path, batch_summary="generated_scores/batch/summary.json")

    assert report["music_functionality_score"] == 90
    assert report["all_pass"] is False
    assert "offline_score_audio_player" in report["blocking_items"]
