from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import nltk

# The pinned HF revision checks this tagger under ``tokenizers/`` even though
# NLTK installs it under ``taggers/``. Redirect only that lookup while HF's
# pipeline module initializes so an installed asset does not trigger a network
# download on every launch.
_nltk_find = nltk.data.find


def _find_hf_nltk_asset(resource_name: str, *args: Any, **kwargs: Any) -> Any:
    if resource_name == "tokenizers/averaged_perceptron_tagger_eng":
        resource_name = "taggers/averaged_perceptron_tagger_eng"
    return _nltk_find(resource_name, *args, **kwargs)


nltk.data.find = _find_hf_nltk_asset
try:
    from speech_to_speech.api.openai_realtime.audio_client import run_realtime_audio_client
    from speech_to_speech.cli import parse_command, parse_talk_arguments
finally:
    nltk.data.find = _nltk_find

from .backend import register_convfill_backend
from .handler import ConvFillRealtimeHandler

# HF builds its argument dataclasses from the registry while importing the
# pipeline module, so the custom backend must exist before that import.
register_convfill_backend()

nltk.data.find = _find_hf_nltk_asset
try:
    from speech_to_speech import s2s_pipeline
finally:
    nltk.data.find = _nltk_find


def _attach_audio_state(manager: Any) -> Any:
    """Wire each adapter to the response-playing event in its pipeline unit."""
    realtime_server = next((handler for handler in manager.handlers if hasattr(handler, "pool")), None)
    if realtime_server is None:
        raise RuntimeError("Could not locate Hugging Face RealtimeServer in the pipeline manager.")
    for unit in realtime_server.pool:
        adapter = next(
            (handler for handler in unit.handlers if isinstance(handler, ConvFillRealtimeHandler)),
            None,
        )
        if adapter is None:
            raise RuntimeError(f"Pipeline {unit.index} has no ConvFillRealtimeHandler.")
        adapter.set_response_playing_event(unit.response_playing)
    return manager


def main(argv: Sequence[str] | None = None) -> None:
    command, command_args = parse_command(argv)
    if command == "talk":
        run_realtime_audio_client(parse_talk_arguments(command_args))
        return

    # The pinned upstream builder owns the full VAD/STT/TTS/realtime stack. A
    # narrow wrapper adds the one transport signal ConvFill needs to schedule
    # <sil> fillers only while the listener would otherwise hear silence.
    original_build_pipeline = s2s_pipeline.build_pipeline

    def build_pipeline_with_convfill(*args: Any, **kwargs: Any) -> Any:
        return _attach_audio_state(original_build_pipeline(*args, **kwargs))

    s2s_pipeline.build_pipeline = build_pipeline_with_convfill
    s2s_pipeline.run_pipeline_command(command, command_args)


if __name__ == "__main__":
    main()
