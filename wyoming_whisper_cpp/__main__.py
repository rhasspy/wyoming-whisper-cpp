#!/usr/bin/env python3
import argparse
import asyncio
import logging
import shlex
from functools import partial
from pathlib import Path
from typing import Optional

from wyoming.info import AsrModel, AsrProgram, Attribution, Info
from wyoming.server import AsyncServer

from . import __version__
from .const import WHISPER_LANGUAGES
from .download import WHISPER_CPP_MODELS, download_model, model_name_to_path
from .handler import WhisperCppEventHandler

_LOGGER = logging.getLogger(__name__)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--whisper-cpp-dir", required=True, help="Path to directory with whisper.cpp"
    )
    parser.add_argument(
        "--model",
        required=True,
        choices=WHISPER_CPP_MODELS,
        help="Name of whisper.cpp model to use",
    )
    parser.add_argument("--uri", required=True, help="unix:// or tcp://")
    parser.add_argument(
        "--data-dir",
        required=True,
        action="append",
        help="Data directory to check for downloaded models",
    )
    parser.add_argument(
        "--download-dir",
        help="Directory to download models into (default: first data dir)",
    )
    parser.add_argument(
        "--language",
        choices=["auto"] + WHISPER_LANGUAGES,
        default="auto",
        help="Default language to set for transcription",
    )
    parser.add_argument(
        "--beam-size",
        type=int,
        default=5,
    )
    parser.add_argument(
        "--audio-context-base", type=int, default=300, help="Base length of audio_ctx"
    )
    parser.add_argument(
        "--whisper-cpp-args",
        help="Additional arguments to pass to whisper cpp executable",
    )
    #
    parser.add_argument("--debug", action="store_true", help="Log DEBUG messages")
    parser.add_argument(
        "--log-format", default=logging.BASIC_FORMAT, help="Format for log messages"
    )
    parser.add_argument(
        "--version",
        action="version",
        version=__version__,
        help="Print version and exit",
    )
    args = parser.parse_args()

    if not args.download_dir:
        # Download to first data dir by default
        args.download_dir = args.data_dir[0]

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO, format=args.log_format
    )
    _LOGGER.debug(args)

    args.whisper_cpp_dir = Path(args.whisper_cpp_dir)
    model_path: Optional[Path] = None

    for data_dir in args.data_dir:
        maybe_model_path = model_name_to_path(args.model, data_dir)
        if maybe_model_path.exists():
            model_path = maybe_model_path
            break

    if model_path is None:
        _LOGGER.debug("Downloading model %s to %s", args.model, args.download_dir)
        download_model(args.whisper_cpp_dir, args.model, args.download_dir)
        model_path = model_name_to_path(args.model, args.download_dir)

    assert model_path is not None

    if ".en" in args.model:
        # English-only model
        model_languages = ["en"]
        args.language = "en"
    else:
        model_languages = WHISPER_LANGUAGES

    wyoming_info = Info(
        asr=[
            AsrProgram(
                name="whisper.cpp",
                description="Port of OpenAI's Whisper model in C/C++",
                attribution=Attribution(
                    name="Georgi Gerganov",
                    url="https://github.com/ggerganov/whisper.cpp",
                ),
                installed=True,
                version=__version__,
                models=[
                    AsrModel(
                        name=args.model,
                        description=args.model,
                        attribution=Attribution(
                            name="rhasspy",
                            url="https://github.com/rhasspy/models/",
                        ),
                        installed=True,
                        languages=model_languages,
                        version="1.0",
                    )
                ],
            )
        ],
    )

    server = AsyncServer.from_uri(args.uri)
    _LOGGER.info("Ready")

    optional_args = ["--audio-context-base", str(args.audio_context_base)]
    if args.whisper_cpp_args:
        optional_args.extend(shlex.split(args.whisper_cpp_args))

    model_args = [
        str(args.whisper_cpp_dir / "main"),
        "--model",
        str(model_path),
        "--language",
        str(args.language),
        "--beam-size",
        str(args.beam_size),
        *optional_args,
    ]

    _LOGGER.debug(model_args)
    model_proc = await asyncio.create_subprocess_exec(
        *model_args,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
    )
    assert model_proc.stdin is not None
    assert model_proc.stdout is not None

    model_proc_lock = asyncio.Lock()

    await server.run(
        partial(
            WhisperCppEventHandler,
            wyoming_info,
            args,
            model_proc,
            model_proc_lock,
        )
    )


# -----------------------------------------------------------------------------


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    try:
        run()
    except KeyboardInterrupt:
        pass
