from __future__ import annotations

import threading
from queue import Queue
from types import SimpleNamespace

from speech_to_speech.api.openai_realtime.runtime_config import RuntimeConfig
from speech_to_speech.pipeline.cancel_scope import CancelScope
from speech_to_speech.pipeline.messages import EndOfResponse, LLMResponseChunk

from src.inference.shared.dialogue_state_manager import DialogueStateManager
from web_demo.hf_convfill.backend import register_convfill_backend
from web_demo.hf_convfill.handler import ConvFillRealtimeHandler, latest_user_text


class _FakeChat:
    def __init__(self, messages=None):
        self.messages = messages or [{"role": "user", "content": "What is ConvFill?"}]
        self.provisional = []
        self.trimmed = False

    def to_transformers_chat(self):
        return list(self.messages)

    def add_provisional_generation_items(self, response_key, items):
        self.provisional.append((response_key, items))
        return items

    def trim_if_needed(self):
        self.trimmed = True


class _FakeSystem:
    def __init__(self, **callbacks):
        self.callbacks = callbacks
        self.cancelled = threading.Event()
        self.reset_called = False
        self.backend_transcripts = []
        self.dialogue_state_manager = DialogueStateManager(num_history_turns=1)

    def set_audio_in_flight_fn(self, callback):
        self.audio_in_flight_fn = callback

    def run_turn(self, user_text):
        self.dialogue_state_manager.update_user_state(user_text)
        self.backend_transcripts.append(self.dialogue_state_manager.get_transcript())
        self.callbacks["on_thought"]("<sil>")
        self.callbacks["on_response_fragment"]("Let me think about that.")
        self.callbacks["on_thought"]("ConvFill pairs a Talker with a Reasoner.")
        self.callbacks["on_response_fragment"]("It pairs a local Talker with a cloud Reasoner.")
        self.dialogue_state_manager.update_response_state(
            "Let me think about that. It pairs a local Talker with a cloud Reasoner."
        )
        self.dialogue_state_manager.update_thoughts_state(
            ["<sil>", "ConvFill pairs a Talker with a Reasoner."]
        )
        self.callbacks["on_turn_complete"]("complete", [])
        return not self.cancelled.is_set()

    def cancel_turn(self):
        self.cancelled.set()

    def reset(self):
        self.reset_called = True


def _request(chat):
    return SimpleNamespace(
        # Keep the lightweight fake chat while satisfying the concrete type
        # required by HF's Pydantic pipeline messages.
        runtime_config=RuntimeConfig.model_construct(chat=chat),
        response=None,
        language_code="en",
        turn_id="turn-one",
        turn_revision=0,
        speech_stopped_at_s=1.25,
        response_key="response-one",
        prefetch_transaction=None,
    )


def _handler(system_factory=_FakeSystem, **setup_kwargs):
    return ConvFillRealtimeHandler(
        threading.Event(),
        queue_in=Queue(),
        queue_out=Queue(),
        setup_kwargs={"system_factory": system_factory, **setup_kwargs},
    )


def test_latest_user_text_uses_the_newest_text_turn():
    chat = _FakeChat(
        [
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "answer"},
            {
                "role": "user",
                "content": [
                    {"type": "input_image", "image_url": "data:image/png;base64,abc"},
                    {"type": "input_text", "text": " newest turn "},
                ],
            },
        ]
    )
    assert latest_user_text(chat) == "newest turn"


def test_handler_streams_only_talker_fragments_and_commits_hf_history():
    chat = _FakeChat()
    handler = _handler()

    outputs = list(handler.process(_request(chat)))

    chunks = [item for item in outputs if isinstance(item, LLMResponseChunk)]
    assert [item.text for item in chunks] == [
        "Let me think about that.",
        "It pairs a local Talker with a cloud Reasoner.",
    ]
    assert all("ConvFill pairs" not in item.text for item in chunks)
    assert isinstance(outputs[-1], EndOfResponse)
    assert outputs[-1].error is None
    assert chat.trimmed is True
    assert chat.provisional[0][0] == "response-one"
    assistant = chat.provisional[0][1][0]
    assert assistant.content[0].text == (
        "Let me think about that. It pairs a local Talker with a cloud Reasoner."
    )


def test_backend_transcript_retains_the_spoken_response_across_turns():
    state = DialogueStateManager(num_history_turns=1)
    state.update_user_state("My favorite color is green.")
    state.update_response_state("I will remember that your favorite color is green.")
    state.update_thoughts_state(["The user stated a color preference."])
    state.update_user_state("What color did I say?")

    assert state.get_transcript() == (
        "User: My favorite color is green.\n"
        "You: I will remember that your favorite color is green.\n"
        "User: What color did I say?"
    )
    assert "The user stated a color preference." not in state.get_transcript()


def test_handler_reuses_convfill_history_for_the_next_hf_turn():
    chat = _FakeChat([{"role": "user", "content": "first question"}])
    handler = _handler()

    first_outputs = list(handler.process(_request(chat)))
    assert first_outputs[-1].error is None

    chat.messages.append({"role": "user", "content": "follow-up question"})
    second = _request(chat)
    second.turn_id = "turn-two"
    second.response_key = "response-two"
    second_outputs = list(handler.process(second))

    assert second_outputs[-1].error is None
    assert handler.system.backend_transcripts == [
        "User: first question",
        (
            "User: first question\n"
            "You: Let me think about that. It pairs a local Talker with a cloud Reasoner.\n"
            "User: follow-up question"
        ),
    ]


def test_session_end_resets_the_reused_convfill_system():
    handler = _handler()
    handler.on_session_end()
    assert handler.system.reset_called is True


def test_failed_turn_is_removed_from_convfill_history():
    class FailingSystem(_FakeSystem):
        def run_turn(self, user_text):
            self.dialogue_state_manager.update_user_state(user_text)
            raise RuntimeError("reasoner unavailable")

    handler = _handler(FailingSystem)
    outputs = list(handler.process(_request(_FakeChat())))

    assert isinstance(outputs[-1], EndOfResponse)
    assert "reasoner unavailable" in outputs[-1].error
    assert handler.system.dialogue_state_manager.user_turns == []


def test_cancelled_turn_emits_no_more_audio_and_rolls_back_history():
    class SlowCommittingSystem(_FakeSystem):
        def run_turn(self, user_text):
            self.dialogue_state_manager.update_user_state(user_text)
            self.callbacks["on_response_fragment"]("partial response")
            assert self.cancelled.wait(timeout=1.0)
            self.dialogue_state_manager.update_response_state("partial response")
            self.dialogue_state_manager.update_thoughts_state(["knowledge"])
            return True

    cancel_scope = CancelScope()
    handler = _handler(SlowCommittingSystem, cancel_scope=cancel_scope)
    output = handler.process(_request(_FakeChat()))

    first = next(output)
    assert isinstance(first, LLMResponseChunk)
    cancel_scope.cancel()
    remaining = list(output)

    assert len(remaining) == 1
    assert isinstance(remaining[0], EndOfResponse)
    assert handler.system.dialogue_state_manager.user_turns == []


def test_dialogue_state_rolls_back_pending_and_completed_turns():
    state = DialogueStateManager(num_history_turns=1)
    state.update_user_state("pending")
    assert state.rollback_turn("pending") is True
    assert state.user_turns == []

    state.update_user_state("completed")
    state.update_response_state("spoken response")
    state.update_thoughts_state(["knowledge"])
    assert state.rollback_turn("completed") is True
    assert state.user_turns == []
    assert state.responses == []
    assert state.thoughts == []


def test_backend_registration_is_idempotent():
    register_convfill_backend()
    register_convfill_backend()
