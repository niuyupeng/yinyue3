from __future__ import annotations

from music21 import converter
from music21 import instrument

from chorale.pro_playback_package import DEFAULT_VARIANTS, make_render_variant_score, write_variant_musicxml_file
from tests.test_score_tokenizer import tiny_satb_score


def test_pro_playback_piano_reference_keeps_four_parts_with_piano_instruments() -> None:
    score = tiny_satb_score()
    variant = next(item for item in DEFAULT_VARIANTS if item.name == "piano_reference")

    rendered = make_render_variant_score(score, variant)

    assert len(rendered.parts) == 4
    for part in rendered.parts:
        instruments = list(part.recurse().getElementsByClass(instrument.Instrument))
        assert any(isinstance(item, instrument.Piano) for item in instruments)


def test_pro_playback_soprano_stem_keeps_only_soprano_part() -> None:
    score = tiny_satb_score()
    variant = next(item for item in DEFAULT_VARIANTS if item.name == "stem_soprano")

    rendered = make_render_variant_score(score, variant)

    assert len(rendered.parts) == 4
    assert rendered.parts[0].partName == "Soprano"
    assert len(rendered.parts[0].flatten().notes) == len(score.parts[0].flatten().notes)
    assert rendered.parts[1].partName == "Alto Muted"
    assert len(rendered.parts[1].flatten().notes) == 0
    assert len(rendered.parts[2].flatten().notes) == 0
    assert len(rendered.parts[3].flatten().notes) == 0
    assert float(rendered.highestTime) == float(score.highestTime)


def test_raw_musicxml_stem_preserves_duration_and_mutes_other_parts(tmp_path) -> None:
    source_path = tmp_path / "source.musicxml"
    output_path = tmp_path / "stem_alto.musicxml"
    score = tiny_satb_score()
    score.write("musicxml", fp=str(source_path))
    variant = next(item for item in DEFAULT_VARIANTS if item.name == "stem_alto")

    write_variant_musicxml_file(source_path, output_path, variant)
    rendered = converter.parse(str(output_path))

    assert float(rendered.highestTime) == float(converter.parse(str(source_path)).highestTime)
    assert len(rendered.parts) == 4
    assert len(rendered.parts[0].flatten().notes) == 0
    assert len(rendered.parts[1].flatten().notes) == len(score.parts[1].flatten().notes)
    assert len(rendered.parts[2].flatten().notes) == 0
    assert len(rendered.parts[3].flatten().notes) == 0
