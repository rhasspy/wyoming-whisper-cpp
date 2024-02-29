"""Tests for wyoming-whisper-cpp"""
import asyncio
import re
import sys
import wave
from asyncio.subprocess import PIPE
from pathlib import Path

import pytest
from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioStart, AudioStop, wav_to_chunks
from wyoming.event import async_read_event, async_write_event
from wyoming.info import Describe, Info

_DIR = Path(__file__).parent
_PROGRAM_DIR = _DIR.parent
_LOCAL_DIR = _PROGRAM_DIR / "local"
_MODEL = "tiny-q5_1"
_SAMPLES_PER_CHUNK = 1024

# Need to give time for the model to download
_TRANSCRIBE_TIMEOUT = 60

_TEST_PHRASE = {
    "en": "turn on the living room lamp",
    "fr": "pouvez-vous me parli en français",
    "uk": "верозмовляєте українською",
}


@pytest.mark.parametrize("language", ["en", "uk", "fr"])
@pytest.mark.asyncio
async def test_whisper_cpp(language: str) -> None:
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "wyoming_whisper_cpp",
        "--uri",
        "stdio://",
        "--whisper-cpp-dir",
        str(_PROGRAM_DIR / "whisper.cpp"),
        "--model",
        _MODEL,
        "--data-dir",
        str(_LOCAL_DIR),
        "--language",
        "en",
        stdin=PIPE,
        stdout=PIPE,
    )
    assert proc.stdin is not None
    assert proc.stdout is not None

    # Check info
    await async_write_event(Describe().event(), proc.stdin)
    while True:
        event = await asyncio.wait_for(async_read_event(proc.stdout), timeout=1)
        assert event is not None

        if not Info.is_type(event.type):
            continue

        info = Info.from_event(event)
        assert len(info.asr) == 1, "Expected one asr service"
        asr = info.asr[0]
        assert len(asr.models) > 0, "Expected at least one model"
        assert any(m.name == _MODEL for m in asr.models), f"Expected {_MODEL} model"
        break

    # We want to use a specific language
    await async_write_event(
        Transcribe(name=_MODEL, language=language).event(), proc.stdin
    )

    # Test known WAV
    with wave.open(str(_DIR / f"{language}.wav"), "rb") as example_wav:
        await async_write_event(
            AudioStart(
                rate=example_wav.getframerate(),
                width=example_wav.getsampwidth(),
                channels=example_wav.getnchannels(),
            ).event(),
            proc.stdin,
        )
        for chunk in wav_to_chunks(example_wav, _SAMPLES_PER_CHUNK):
            await async_write_event(chunk.event(), proc.stdin)

        await async_write_event(AudioStop().event(), proc.stdin)

    while True:
        event = await asyncio.wait_for(
            async_read_event(proc.stdout), timeout=_TRANSCRIBE_TIMEOUT
        )
        assert event is not None

        if not Transcript.is_type(event.type):
            continue

        transcript = Transcript.from_event(event)
        text = transcript.text.lower().strip()
        text = re.sub(r"[.!?]", "", text)
        assert text == _TEST_PHRASE[language]
        break

    # Need to close stdin for graceful termination
    proc.stdin.close()
    _, stderr = await proc.communicate()

    assert proc.returncode == 0, stderr.decode()
