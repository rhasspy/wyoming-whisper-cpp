"""Event handler for clients of the server."""
import argparse
import asyncio
import io
import json
import logging
import wave
from asyncio.subprocess import Process

from wyoming.asr import Transcribe, Transcript
from wyoming.audio import AudioChunk, AudioChunkConverter, AudioStop
from wyoming.event import Event
from wyoming.info import Describe, Info
from wyoming.server import AsyncEventHandler

_LOGGER = logging.getLogger(__name__)


class WhisperCppEventHandler(AsyncEventHandler):
    """Event handler for clients."""

    def __init__(
        self,
        wyoming_info: Info,
        cli_args: argparse.Namespace,
        model_proc: Process,
        model_proc_lock: asyncio.Lock,
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.cli_args = cli_args
        self.wyoming_info_event = wyoming_info.event()
        self.model_proc = model_proc
        self.model_proc_lock = model_proc_lock
        self.audio = bytes()
        self.audio_converter = AudioChunkConverter(
            rate=16000,
            width=2,
            channels=1,
        )
        self._language = self.cli_args.language

    async def handle_event(self, event: Event) -> bool:
        if AudioChunk.is_type(event.type):
            if not self.audio:
                _LOGGER.debug("Receiving audio")

            chunk = AudioChunk.from_event(event)
            chunk = self.audio_converter.convert(chunk)
            self.audio += chunk.audio

            return True

        if AudioStop.is_type(event.type):
            _LOGGER.debug("Audio stopped")
            text = ""
            with io.BytesIO() as wav_io:
                wav_file: wave.Wave_write = wave.open(wav_io, "wb")
                with wav_file:
                    wav_file.setframerate(16000)
                    wav_file.setsampwidth(2)
                    wav_file.setnchannels(1)
                    wav_file.writeframes(self.audio)

                wav_io.seek(0)
                wav_bytes = wav_io.getvalue()

                assert self.model_proc.stdin is not None
                assert self.model_proc.stdout is not None

                async with self.model_proc_lock:
                    request_str = json.dumps(
                        {"size": len(wav_bytes), "language": self._language}
                    )
                    request_line = f"{request_str}\n".encode("utf-8")
                    self.model_proc.stdin.write(request_line)
                    self.model_proc.stdin.write(wav_bytes)
                    await self.model_proc.stdin.drain()

                    lines = []
                    line = (await self.model_proc.stdout.readline()).decode().strip()
                    while line != "<|endoftext|>":
                        if line:
                            lines.append(line)
                        line = (
                            (await self.model_proc.stdout.readline()).decode().strip()
                        )

                text = " ".join(lines)
                text = text.replace("[BLANK_AUDIO]", "").strip()

            _LOGGER.info(text)

            await self.write_event(Transcript(text=text).event())
            _LOGGER.debug("Completed request")

            # Reset
            self.audio = bytes()
            self._language = self.cli_args.language

            return False

        if Transcribe.is_type(event.type):
            transcribe = Transcribe.from_event(event)
            if transcribe.language:
                self._language = transcribe.language
                _LOGGER.debug("Language set to %s", transcribe.language)
            return True

        if Describe.is_type(event.type):
            await self.write_event(self.wyoming_info_event)
            _LOGGER.debug("Sent info")
            return True

        return True
