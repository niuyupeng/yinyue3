from __future__ import annotations

from chorale.playback_render import (
    musicxml_to_midi,
    normalize_wav_peak,
    pad_wav_to_duration,
    synthesize_musicxml_to_wav_additive,
    validate_wav_file,
)
from chorale.delivery_conformance_audit import event_alignment_scores, get_signature
from chorale.verify_expert_playback_package import audit_package
from tests.test_score_tokenizer import tiny_satb_score


def test_additive_playback_renders_non_silent_wav(tmp_path) -> None:
    musicxml_path = tmp_path / "tiny.musicxml"
    wav_path = tmp_path / "tiny.wav"
    tiny_satb_score().write("musicxml", fp=str(musicxml_path))

    synthesize_musicxml_to_wav_additive(musicxml_path, wav_path)
    validation = validate_wav_file(wav_path)

    assert validation.ok
    assert validation.duration_sec > 0.5
    assert validation.rms > 1.0
    assert validation.peak > 0


def test_musicxml_to_midi_preserves_score_events(tmp_path) -> None:
    musicxml_path = tmp_path / "tiny.musicxml"
    midi_path = tmp_path / "tiny.mid"
    tiny_satb_score().write("musicxml", fp=str(musicxml_path))

    musicxml_to_midi(musicxml_path, midi_path)

    issues: list[str] = []
    cache = {}
    score_sig = get_signature(musicxml_path, cache, issues, "musicxml")
    midi_sig = get_signature(midi_path, cache, issues, "midi")
    assert not issues
    assert score_sig is not None
    assert midi_sig is not None
    recall, precision, f1 = event_alignment_scores(score_sig.flat_events, midi_sig.flat_events, quantum=0.25)
    assert recall == 1.0
    assert precision == 1.0
    assert f1 == 1.0


def test_normalize_wav_peak_keeps_headroom(tmp_path) -> None:
    musicxml_path = tmp_path / "tiny.musicxml"
    wav_path = tmp_path / "tiny.wav"
    tiny_satb_score().write("musicxml", fp=str(musicxml_path))
    synthesize_musicxml_to_wav_additive(musicxml_path, wav_path)

    validation = normalize_wav_peak(wav_path, target_peak=0.5)

    assert validation.ok
    assert 15000 <= validation.peak <= 17000


def test_pad_wav_to_duration_adds_silence_without_muting(tmp_path) -> None:
    musicxml_path = tmp_path / "tiny.musicxml"
    wav_path = tmp_path / "tiny.wav"
    tiny_satb_score().write("musicxml", fp=str(musicxml_path))
    synthesize_musicxml_to_wav_additive(musicxml_path, wav_path)
    before = validate_wav_file(wav_path)

    after = pad_wav_to_duration(wav_path, before.duration_sec + 1.0)

    assert after.ok
    assert after.duration_sec >= before.duration_sec + 0.9
    assert after.peak > 0


def test_expert_package_audit_checks_score_audio_correspondence(tmp_path) -> None:
    package = make_minimal_playback_package(tmp_path / "package")

    audit = audit_package(package)

    assert audit["summary"]["all_entries_ok"]
    assert audit["summary"]["all_same_stem"]
    assert audit["summary"]["all_entries_have_four_parts"]
    assert audit["summary"]["all_four_parts_have_notes"]
    assert audit["summary"]["all_midi_parseable"]
    assert audit["summary"]["all_playback_backends_current"]


def test_expert_package_audit_rejects_legacy_fluidsynth_without_musescore_midi(tmp_path) -> None:
    package = make_minimal_playback_package(tmp_path / "legacy_package")
    (package / "playback_midi" / "playback_midi_manifest.csv").write_text(
        "source_musicxml,output_midi,status,message\n"
        "absolute_score_musicxml/P1S01.musicxml,playback_midi/absolute_score_midi/P1S01.mid,ok,\n",
        encoding="utf-8",
    )
    (package / "playback_audio" / "playback_audio_manifest.csv").write_text(
        "source_musicxml,output_wav,output_mp3,wav_status,mp3_status,backend,duration_sec,rms,peak,message\n"
        "absolute_score_musicxml/P1S01.musicxml,playback_audio/absolute_score_wav/P1S01.wav,"
        "playback_audio/absolute_score_mp3/P1S01.mp3,ok,ok,fluidsynth,1.0,2.0,10,\n",
        encoding="utf-8",
    )

    audit = audit_package(package)

    assert not audit["summary"]["all_entries_ok"]
    assert not audit["summary"]["all_playback_backends_current"]
    assert "legacy playback chain" in audit["errors"][0]


def make_minimal_playback_package(package):
    for folder in [
        "absolute_score_musicxml",
        "absolute_score_pdfs",
        "playback_midi/absolute_score_midi",
        "playback_audio/absolute_score_wav",
        "playback_audio/absolute_score_mp3",
    ]:
        (package / folder).mkdir(parents=True)
    (package / "paired_comparison_musicxml").mkdir()
    (package / "paired_comparison_pdfs").mkdir()
    (package / "playback_midi" / "paired_comparison_midi").mkdir(parents=True)
    (package / "playback_audio" / "paired_comparison_wav").mkdir(parents=True)
    (package / "playback_audio" / "paired_comparison_mp3").mkdir(parents=True)

    stem = "P1S01"
    musicxml_path = package / "absolute_score_musicxml" / f"{stem}.musicxml"
    midi_path = package / "playback_midi" / "absolute_score_midi" / f"{stem}.mid"
    wav_path = package / "playback_audio" / "absolute_score_wav" / f"{stem}.wav"
    tiny_satb_score().write("musicxml", fp=str(musicxml_path))
    musicxml_to_midi(musicxml_path, midi_path)
    synthesize_musicxml_to_wav_additive(musicxml_path, wav_path)
    (package / "absolute_score_pdfs" / f"{stem}.pdf").write_bytes(b"%PDF-1.4\n")
    (package / "playback_audio" / "absolute_score_mp3" / f"{stem}.mp3").write_bytes(bytes(2048))
    (package / "playback_midi" / "playback_midi_manifest.csv").write_text(
        "source_musicxml,output_midi,backend,status,message\n"
        "absolute_score_musicxml/P1S01.musicxml,playback_midi/absolute_score_midi/P1S01.mid,musescore,ok,\n",
        encoding="utf-8",
    )
    (package / "playback_audio" / "playback_audio_manifest.csv").write_text(
        "source_musicxml,output_wav,output_mp3,wav_status,mp3_status,backend,duration_sec,rms,peak,message\n"
        "absolute_score_musicxml/P1S01.musicxml,playback_audio/absolute_score_wav/P1S01.wav,"
        "playback_audio/absolute_score_mp3/P1S01.mp3,ok,ok,musescore_midi_fluidsynth,1.0,2.0,10,\n",
        encoding="utf-8",
    )
    return package
