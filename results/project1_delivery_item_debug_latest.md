# Project1 Delivery Item Debug Report

Score ID: `P1S01`
Variant: `stem_alto`
Status: `pass`

## Files

- source_musicxml: `absolute_score_musicxml/P1S01.musicxml` exists=True size=56582
- render_musicxml: `render_xml/absolute/P1S01/P1S01_stem_alto.musicxml` exists=True size=34163
- midi: `midi_pro/absolute/P1S01/P1S01_stem_alto.mid` exists=True size=711
- mp3: `audio_pro/absolute/P1S01/P1S01_stem_alto.mp3` exists=True size=654568

## Issues

No automatic item-level issues found.

## Timepoint Diagnostic

- time_sec: `12.5`
- audio_duration_sec: `27.214`
- estimated_quarter_offset: `20.44`
- estimated_measure: `5`
- estimated_beat: `5.44`
- measure_relative_offset_quarter: `4.44`
- measure_duration_quarter: `5.0`
- time_signature: `4/4`

### Rendered Notes Near Time

| Part | Kind | Pitches | Offset | Duration |
|---|---|---|---:|---:|
| Tenor Muted | rest |  | 18.5 | 1.0 |
| Soprano Muted | rest |  | 19.0 | 1.0 |
| Alto | note | E4 | 19.0 | 1.0 |
| Bass Muted | rest |  | 19.0 | 2.0 |
| Tenor Muted | rest |  | 19.5 | 2.0 |
| Soprano Muted | rest |  | 20.0 | 0.5 |
| Alto | note | F4 | 20.0 | 2.0 |
| Soprano Muted | rest |  | 20.5 | 0.5 |
| Soprano Muted | rest |  | 21.0 | 1.0 |
| Bass Muted | rest |  | 21.0 | 1.0 |

### Source Notes Near Time

| Part | Kind | Pitches | Offset | Duration |
|---|---|---|---:|---:|
| Tenor | note | D4 | 18.5 | 1.0 |
| Soprano | note | A4 | 19.0 | 1.0 |
| Alto | note | E4 | 19.0 | 1.0 |
| Bass | note | B-2 | 19.0 | 2.0 |
| Tenor | note | C4 | 19.5 | 2.0 |
| Soprano | note | B-4 | 20.0 | 0.5 |
| Alto | note | F4 | 20.0 | 2.0 |
| Soprano | note | A4 | 20.5 | 0.5 |
| Soprano | note | G4 | 21.0 | 1.0 |
| Bass | note | A2 | 21.0 | 1.0 |

This is a deterministic score-time estimate based on rendered score duration and MP3 duration. It is intended for triage; final musical judgment should compare the displayed score and playback.

## Manual Check

Open score_audio_player.html, search the score_id, play the requested variant, and compare it with the listed source/render MusicXML files.
