from __future__ import annotations

import math
import os
import shutil
import struct
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from music21 import converter, stream


REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass
class AudioValidation:
    ok: bool
    duration_sec: float = 0.0
    rms: float = 0.0
    peak: int = 0
    message: str = ""


@dataclass
class PlaybackRenderSettings:
    backend: str = "auto"
    sample_rate: int = 44100
    bpm: float = 84.0
    mp3_bitrate: str = "192k"
    min_rms: float = 1.0
    musescore_path: str | None = None
    fluidsynth_path: str | None = None
    soundfont_path: str | None = None


@dataclass
class PlaybackRenderResult:
    wav_status: str
    mp3_status: str
    backend: str
    message: str = ""
    duration_sec: float = 0.0
    rms: float = 0.0
    peak: int = 0


def render_musicxml_to_audio(
    musicxml_path: str | Path,
    wav_path: str | Path,
    mp3_path: str | Path,
    settings: PlaybackRenderSettings | None = None,
) -> PlaybackRenderResult:
    settings = settings or PlaybackRenderSettings()
    musicxml_path = Path(musicxml_path)
    wav_path = Path(wav_path)
    mp3_path = Path(mp3_path)

    errors: list[str] = []
    for backend in backend_order(settings.backend):
        if wav_path.exists():
            wav_path.unlink()
        result = _render_wav_with_backend(musicxml_path, wav_path, backend, settings)
        if result.ok:
            mp3_message = convert_wav_to_mp3(wav_path, mp3_path, settings.mp3_bitrate)
            mp3_status = "ok" if not mp3_message else "failed"
            if "skipped" in mp3_message.lower():
                mp3_status = "skipped"
            return PlaybackRenderResult(
                wav_status="ok",
                mp3_status=mp3_status,
                backend=backend,
                message=mp3_message,
                duration_sec=result.duration_sec,
                rms=result.rms,
                peak=result.peak,
            )
        errors.append(f"{backend}: {result.message}")

    return PlaybackRenderResult(
        wav_status="failed",
        mp3_status="skipped",
        backend="none",
        message="; ".join(errors),
    )


def backend_order(backend: str) -> list[str]:
    backend = backend.lower().strip()
    if backend == "auto":
        return ["musescore", "musescore_midi_fluidsynth", "fluidsynth", "additive"]
    if backend not in {"musescore", "musescore_midi_fluidsynth", "fluidsynth", "additive"}:
        raise ValueError(f"Unknown playback backend: {backend}")
    return [backend]


def _render_wav_with_backend(
    musicxml_path: Path,
    wav_path: Path,
    backend: str,
    settings: PlaybackRenderSettings,
) -> AudioValidation:
    if backend == "musescore":
        message = render_with_musescore(musicxml_path, wav_path, settings)
    elif backend == "musescore_midi_fluidsynth":
        message = render_with_musescore_midi_fluidsynth(musicxml_path, wav_path, settings)
    elif backend == "fluidsynth":
        message = render_with_fluidsynth(musicxml_path, wav_path, settings)
    elif backend == "additive":
        message = ""
        try:
            synthesize_musicxml_to_wav_additive(musicxml_path, wav_path, settings.sample_rate, settings.bpm)
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
    else:
        message = f"Unknown backend: {backend}"

    if message:
        return AudioValidation(False, message=message)
    return validate_wav_file(wav_path, settings.min_rms)


def render_with_musescore(musicxml_path: Path, wav_path: Path, settings: PlaybackRenderSettings) -> str:
    exe = find_musescore(settings.musescore_path)
    if not exe:
        return "MuseScore executable not found"
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    command = [exe, "-f", "-o", str(wav_path), str(musicxml_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0:
        return (result.stderr or result.stdout or f"MuseScore exited {result.returncode}").strip()
    return ""


def export_midi_with_musescore(musicxml_path: Path, midi_path: Path, settings: PlaybackRenderSettings) -> str:
    exe = find_musescore(settings.musescore_path)
    if not exe:
        return "MuseScore executable not found"
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    command = [exe, "-f", "-o", str(midi_path), str(musicxml_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0:
        return (result.stderr or result.stdout or f"MuseScore exited {result.returncode}").strip()
    if not midi_path.is_file() or midi_path.stat().st_size < 128:
        return "MuseScore MIDI output is missing or too small"
    return ""


def export_pdf_with_musescore(musicxml_path: Path, pdf_path: Path, settings: PlaybackRenderSettings) -> str:
    exe = find_musescore(settings.musescore_path)
    if not exe:
        return "MuseScore executable not found"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    command = [exe, "-f", "-o", str(pdf_path), str(musicxml_path)]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0:
        return (result.stderr or result.stdout or f"MuseScore exited {result.returncode}").strip()
    if not pdf_path.is_file() or pdf_path.stat().st_size < 1024:
        return "MuseScore PDF output is missing or too small"
    return ""


def render_with_musescore_midi_fluidsynth(
    musicxml_path: Path,
    wav_path: Path,
    settings: PlaybackRenderSettings,
) -> str:
    with tempfile.TemporaryDirectory(prefix="chorale_musescore_midi_") as tmp:
        midi_path = Path(tmp) / f"{musicxml_path.stem}.mid"
        midi_message = export_midi_with_musescore(musicxml_path, midi_path, settings)
        if midi_message:
            return midi_message
        return render_midi_with_fluidsynth(midi_path, wav_path, settings)


def render_with_fluidsynth(musicxml_path: Path, wav_path: Path, settings: PlaybackRenderSettings) -> str:
    with tempfile.TemporaryDirectory(prefix="chorale_playback_") as tmp:
        midi_path = Path(tmp) / f"{musicxml_path.stem}.mid"
        musicxml_to_midi(musicxml_path, midi_path)
        return render_midi_with_fluidsynth(midi_path, wav_path, settings)


def render_midi_with_fluidsynth(midi_path: Path, wav_path: Path, settings: PlaybackRenderSettings) -> str:
    exe = find_fluidsynth(settings.fluidsynth_path)
    if not exe:
        return "FluidSynth executable not found"
    soundfont = find_soundfont(settings.soundfont_path)
    if not soundfont:
        return "SoundFont not found; set CHORALE_SOUNDFONT or run scripts/setup_playback_tools.ps1"
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        exe,
        "-ni",
        "-T",
        "wav",
        "-F",
        str(wav_path),
        "-g",
        "0.85",
        "-r",
        str(settings.sample_rate),
        str(soundfont),
        str(midi_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=90)
    if result.returncode != 0:
        return (result.stderr or result.stdout or f"FluidSynth exited {result.returncode}").strip()
    return ""


def musicxml_to_midi(musicxml_path: Path, midi_path: Path, bpm: float = 84.0) -> None:
    score = converter.parse(str(musicxml_path))
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    write_score_aligned_midi(score, midi_path, bpm=bpm)


def write_score_aligned_midi(
    score: stream.Score,
    midi_path: str | Path,
    *,
    bpm: float = 84.0,
    ticks_per_quarter: int = 480,
) -> None:
    midi_path = Path(midi_path)
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    events = collect_midi_note_events(score, ticks_per_quarter=ticks_per_quarter)
    tempo = max(1, int(round(60_000_000 / max(float(bpm), 1.0))))
    track_events: list[tuple[int, int, bytes]] = [
        (0, 0, b"\xff\x51\x03" + tempo.to_bytes(3, "big")),
        (0, 1, b"\xff\x58\x04\x04\x02\x18\x08"),
    ]
    used_channels = sorted({channel for channel, _, _, _ in events})
    for channel in used_channels:
        program = choose_midi_program_for_channel(score, channel)
        track_events.append((0, 2 + channel, bytes([0xC0 | channel, program])))
    for channel, pitch, start_tick, end_tick in events:
        velocity = 72 if channel < 4 else 64
        track_events.append((start_tick, 20, bytes([0x90 | channel, pitch, velocity])))
        track_events.append((end_tick, 10, bytes([0x80 | channel, pitch, 0])))
    track_events.sort(key=lambda item: (item[0], item[1], item[2]))
    track = bytearray()
    last_tick = 0
    for tick, _, payload in track_events:
        track.extend(write_varlen(max(0, tick - last_tick)))
        track.extend(payload)
        last_tick = tick
    track.extend(write_varlen(0))
    track.extend(b"\xff\x2f\x00")
    header = b"MThd" + struct.pack(">IHHH", 6, 0, 1, ticks_per_quarter)
    chunk = b"MTrk" + struct.pack(">I", len(track)) + bytes(track)
    midi_path.write_bytes(header + chunk)


def collect_midi_note_events(score: stream.Score, *, ticks_per_quarter: int) -> list[tuple[int, int, int, int]]:
    events: list[tuple[int, int, int, int]] = []
    parts = list(score.parts) if getattr(score, "parts", None) else [score]
    for part_idx, part in enumerate(parts[:16]):
        channel = part_idx if part_idx < 9 else part_idx + 1
        if channel > 15:
            break
        for element in part.recurse().notes:
            start_tick = int(round(global_quarter_offset(element, score) * ticks_per_quarter))
            duration_tick = max(1, int(round(float(element.duration.quarterLength or 0.0) * ticks_per_quarter)))
            end_tick = start_tick + duration_tick
            pitches = getattr(element, "pitches", None)
            if not pitches:
                pitch = getattr(element, "pitch", None)
                pitches = [pitch] if pitch is not None else []
            for pitch in pitches:
                midi_pitch = int(getattr(pitch, "midi"))
                if 0 <= midi_pitch <= 127:
                    events.append((channel, midi_pitch, max(0, start_tick), max(1, end_tick)))
    return events


def global_quarter_offset(element: object, score: stream.Score) -> float:
    try:
        return float(element.getOffsetInHierarchy(score))  # type: ignore[attr-defined]
    except Exception:
        try:
            return float(element.offset)  # type: ignore[attr-defined]
        except Exception:
            return 0.0


def choose_midi_program_for_channel(score: stream.Score, channel: int) -> int:
    parts = list(score.parts) if getattr(score, "parts", None) else [score]
    part_name = ""
    if channel < len(parts):
        part = parts[channel]
        part_name = f"{part.partName or ''} {part.partAbbreviation or ''} {part.id or ''}".lower()
    if "piano" in part_name:
        return 0
    return 52


def write_varlen(value: int) -> bytes:
    value = max(0, int(value))
    buffer = value & 0x7F
    value >>= 7
    out = [buffer]
    while value:
        out.insert(0, (value & 0x7F) | 0x80)
        value >>= 7
    return bytes(out)


def find_musescore(explicit: str | None = None) -> str | None:
    candidates = [
        explicit,
        os.environ.get("CHORALE_MUSESCORE_EXE"),
        shutil.which("MuseScore4.exe"),
        shutil.which("mscore"),
        shutil.which("musescore"),
        r"C:\Program Files\MuseScore 4\bin\MuseScore4.exe",
        r"C:\Program Files\MuseScore 3\bin\MuseScore3.exe",
    ]
    return first_existing_file(candidates)


def find_fluidsynth(explicit: str | None = None) -> str | None:
    candidates: list[str | None] = [
        explicit,
        os.environ.get("CHORALE_FLUIDSYNTH_EXE"),
        shutil.which("fluidsynth"),
        shutil.which("fluidsynth.exe"),
    ]
    candidates.extend(str(path) for path in (REPO_ROOT / "external_tools").glob("**/fluidsynth.exe"))
    return first_existing_file(candidates)


def find_soundfont(explicit: str | None = None) -> str | None:
    candidates = [
        explicit,
        os.environ.get("CHORALE_SOUNDFONT"),
        str(REPO_ROOT / "external_tools" / "soundfonts" / "MuseScore_General.sf3"),
        str(REPO_ROOT / "external_tools" / "soundfonts" / "MuseScore_General.sf2"),
        r"C:\Program Files\MuseScore 4\sound\MS Basic.sf3",
        r"C:\Program Files\MuseScore 3\sound\MuseScore_General.sf3",
    ]
    return first_existing_file(candidates)


def first_existing_file(candidates: list[str | None]) -> str | None:
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if path.is_file():
            return str(path)
    return None


def validate_wav_file(wav_path: str | Path, min_rms: float = 1.0) -> AudioValidation:
    wav_path = Path(wav_path)
    if not wav_path.is_file():
        return AudioValidation(False, message=f"WAV not created: {wav_path}")
    if wav_path.stat().st_size < 2048:
        return AudioValidation(False, message=f"WAV too small: {wav_path.stat().st_size} bytes")
    try:
        with wave.open(str(wav_path), "rb") as handle:
            frames = handle.readframes(handle.getnframes())
            data = np.frombuffer(frames, dtype=np.int16)
            duration = handle.getnframes() / float(handle.getframerate())
    except Exception as exc:
        return AudioValidation(False, message=f"Invalid WAV: {type(exc).__name__}: {exc}")
    if data.size == 0:
        return AudioValidation(False, duration_sec=duration, message="WAV has no samples")
    rms = float(np.sqrt(np.mean(data.astype(np.float64) ** 2)))
    peak = int(np.max(np.abs(data)))
    if rms < min_rms or peak == 0:
        return AudioValidation(False, duration_sec=duration, rms=rms, peak=peak, message="WAV appears silent")
    return AudioValidation(True, duration_sec=duration, rms=rms, peak=peak)


def normalize_wav_peak(wav_path: str | Path, target_peak: float = 0.88) -> AudioValidation:
    wav_path = Path(wav_path)
    with wave.open(str(wav_path), "rb") as handle:
        params = handle.getparams()
        frames = handle.readframes(handle.getnframes())
    if params.sampwidth != 2:
        return validate_wav_file(wav_path)
    data = np.frombuffer(frames, dtype=np.int16)
    if data.size == 0:
        return AudioValidation(False, message="WAV has no samples")
    peak = float(np.max(np.abs(data)))
    if peak <= 0:
        return AudioValidation(False, message="WAV appears silent")
    target = min(max(float(target_peak), 0.01), 0.98) * 32767.0
    scale = target / peak
    normalized = np.asarray(np.clip(data.astype(np.float64) * scale, -32767, 32767), dtype=np.int16)
    with wave.open(str(wav_path), "wb") as handle:
        handle.setparams(params)
        handle.writeframes(normalized.tobytes())
    return validate_wav_file(wav_path)


def pad_wav_to_duration(wav_path: str | Path, target_duration_sec: float) -> AudioValidation:
    wav_path = Path(wav_path)
    with wave.open(str(wav_path), "rb") as handle:
        params = handle.getparams()
        frames = handle.readframes(handle.getnframes())
        current_frames = handle.getnframes()
        sample_rate = handle.getframerate()
    target_frames = int(math.ceil(float(target_duration_sec) * sample_rate))
    if target_frames <= current_frames:
        return validate_wav_file(wav_path)
    sample_width = params.sampwidth
    channels = params.nchannels
    silence = bytes((target_frames - current_frames) * sample_width * channels)
    with wave.open(str(wav_path), "wb") as handle:
        handle.setparams(params)
        handle.writeframes(frames)
        handle.writeframes(silence)
    return validate_wav_file(wav_path)


def convert_wav_to_mp3(wav_path: Path, mp3_path: Path, bitrate: str = "192k") -> str:
    ffmpeg = os.environ.get("CHORALE_FFMPEG_EXE") or shutil.which("ffmpeg") or shutil.which("ffmpeg.exe")
    if not ffmpeg:
        return "ffmpeg not found; MP3 skipped"
    if not Path(ffmpeg).is_file():
        return f"ffmpeg not found at configured path: {ffmpeg}"
    mp3_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(wav_path),
        "-codec:a",
        "libmp3lame",
        "-b:a",
        bitrate,
        str(mp3_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return (result.stderr or result.stdout or f"ffmpeg exited {result.returncode}").strip()
    if not mp3_path.exists() or mp3_path.stat().st_size < 1024:
        return "MP3 output is missing or too small"
    return ""


def synthesize_musicxml_to_wav_additive(
    musicxml_path: Path,
    wav_path: Path,
    sample_rate: int = 44100,
    bpm: float = 84.0,
) -> None:
    score = converter.parse(str(musicxml_path))
    seconds_per_quarter = 60.0 / bpm
    events = collect_note_events(score, seconds_per_quarter)
    if not events:
        raise ValueError("No note events found")
    end_time = max(start + duration for start, duration, _, _, _ in events) + 0.75
    left = np.zeros(int(end_time * sample_rate) + 1, dtype=np.float32)
    right = np.zeros_like(left)
    for start, duration, midi_pitch, gain, pan in events:
        add_tone(left, right, start, duration, midi_pitch, sample_rate, gain, pan)
    stereo = np.stack([left, right], axis=1)
    stereo = add_simple_reverb(stereo, sample_rate)
    peak = float(np.max(np.abs(stereo)))
    if peak > 0:
        stereo = 0.90 * stereo / peak
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = np.asarray(np.clip(stereo, -1.0, 1.0) * 32767, dtype=np.int16)
    with wave.open(str(wav_path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())


def collect_note_events(score: stream.Score, seconds_per_quarter: float) -> list[tuple[float, float, int, float, float]]:
    events: list[tuple[float, float, int, float, float]] = []
    parts = list(score.parts) if getattr(score, "parts", None) else [score]
    part_count = max(len(parts), 1)
    base_gain = 0.16 / math.sqrt(part_count)
    pans = np.linspace(-0.35, 0.35, part_count)
    for part_idx, part in enumerate(parts):
        pan = float(pans[part_idx]) if part_idx < len(pans) else 0.0
        for element in part.flatten().notes:
            start = float(element.offset) * seconds_per_quarter
            duration = max(float(element.duration.quarterLength) * seconds_per_quarter, 0.08)
            pitches = getattr(element, "pitches", None)
            if not pitches:
                continue
            for pitch in pitches:
                events.append((start, duration, int(pitch.midi), base_gain, pan))
    return events


def add_tone(
    left: np.ndarray,
    right: np.ndarray,
    start: float,
    duration: float,
    midi_pitch: int,
    sample_rate: int,
    gain: float,
    pan: float,
) -> None:
    start_idx = max(int(start * sample_rate), 0)
    tone_len = max(int(duration * sample_rate), 1)
    end_idx = min(start_idx + tone_len, len(left))
    if end_idx <= start_idx:
        return
    n = end_idx - start_idx
    t = np.arange(n, dtype=np.float32) / sample_rate
    freq = 440.0 * (2.0 ** ((midi_pitch - 69) / 12.0))
    # Gentle choir-like additive spectrum for fallback playback only.
    wave_data = (
        np.sin(2 * np.pi * freq * t)
        + 0.32 * np.sin(2 * np.pi * freq * 2.0 * t)
        + 0.14 * np.sin(2 * np.pi * freq * 3.0 * t)
        + 0.05 * np.sin(2 * np.pi * freq * 4.0 * t)
    )
    wave_data *= gain
    attack = min(int(0.035 * sample_rate), max(n // 3, 1))
    release = min(int(0.120 * sample_rate), max(n // 3, 1))
    envelope = np.ones(n, dtype=np.float32)
    if attack > 0:
        envelope[:attack] = np.sin(np.linspace(0.0, math.pi / 2, attack, dtype=np.float32)) ** 2
    if release > 0:
        envelope[-release:] *= np.cos(np.linspace(0.0, math.pi / 2, release, dtype=np.float32)) ** 2
    vibrato = 1.0 + 0.004 * np.sin(2 * np.pi * 5.2 * t)
    rendered = wave_data.astype(np.float32) * envelope * vibrato.astype(np.float32)
    left_gain = math.sqrt((1.0 - pan) / 2.0)
    right_gain = math.sqrt((1.0 + pan) / 2.0)
    left[start_idx:end_idx] += rendered * left_gain
    right[start_idx:end_idx] += rendered * right_gain


def add_simple_reverb(stereo: np.ndarray, sample_rate: int) -> np.ndarray:
    output = stereo.copy()
    for delay_sec, gain in [(0.045, 0.16), (0.083, 0.10), (0.137, 0.06)]:
        delay = int(delay_sec * sample_rate)
        if delay <= 0 or delay >= len(output):
            continue
        output[delay:] += stereo[:-delay] * gain
    return output
