"""Reasoner web search through Anthropic's server-side tool, driven by a fake stream."""
from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from src.inference.convfill_stack.convfill_backend_multi import ConvFillBackend
from src.inference.convfill_stack.model_inference_functions_conversational import ClaudeInference

WEB_SEARCH_TEMPLATE = "configs/convfill_backend_prompts/convfill_backend_template_web_search_conv.txt"
TOOL = {"type": "web_search_20250305", "name": "web_search", "max_uses": 3}


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _search(query):
    block = SimpleNamespace(type="server_tool_use", input={"query": query})
    return SimpleNamespace(type="content_block_stop", content_block=block)


def _results(content):
    block = SimpleNamespace(type="web_search_tool_result", content=content)
    return SimpleNamespace(type="content_block_stop", content_block=block)


class _FakeStream:
    def __init__(self, events, stop_reason, content):
        self._events = events
        self._final = SimpleNamespace(stop_reason=stop_reason, content=content)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.closed = True
        return False

    def __iter__(self):
        return iter(self._events)

    def get_final_message(self):
        return self._final


class _FakeMessages:
    def __init__(self, streams):
        self._streams = list(streams)
        self.calls = []

    def stream(self, **kwargs):
        self.calls.append(kwargs)
        return self._streams.pop(0)


def _claude(streams):
    claude = ClaudeInference.__new__(ClaudeInference)
    claude.model_name = "claude-haiku-4-5-20251001"
    claude.reasoning_effort = None
    claude.client = SimpleNamespace(messages=_FakeMessages(streams))
    return claude


def test_streams_sentences_and_reports_searches():
    stream = _FakeStream(
        [
            _text("Let me check"),
            _search("Mariners score"),
            _results([SimpleNamespace(type="web_search_result")]),
            _text("The Mariners beat the Astros five to three. "),
            _text("It was on Sunday"),
        ],
        stop_reason="end_turn",
        content=[],
    )
    claude = _claude([stream])

    events = list(claude.generate_with_web_search("prompt", TOOL))

    assert events == [
        ("sentence", "Let me check"),  # flushed at the search, not glued to the answer
        ("search", "Mariners score"),
        ("sentence", "The Mariners beat the Astros five to three."),
        ("sentence", "It was on Sunday"),
    ]
    call = claude.client.messages.calls[0]
    assert call["tools"] == [TOOL]
    assert call["messages"] == [{"role": "user", "content": "prompt"}]
    assert stream.closed


def test_reports_search_errors():
    error = SimpleNamespace(type="web_search_tool_result_error", error_code="max_uses_exceeded")
    stream = _FakeStream(
        [_search("score"), _results(error), _text("I could not find that. ")],
        stop_reason="end_turn",
        content=[],
    )

    events = list(_claude([stream]).generate_with_web_search("prompt", TOOL))

    assert ("search_error", "max_uses_exceeded") in events
    assert events[-1] == ("sentence", "I could not find that.")


def test_pause_turn_resumes_with_the_paused_assistant_turn():
    paused_content = [SimpleNamespace(type="server_tool_use")]
    first = _FakeStream([_search("score")], stop_reason="pause_turn", content=paused_content)
    second = _FakeStream([_text("The final was two to one. ")], stop_reason="end_turn", content=[])
    claude = _claude([first, second])

    events = list(claude.generate_with_web_search("prompt", TOOL))

    assert events == [("search", "score"), ("sentence", "The final was two to one.")]
    resumed = claude.client.messages.calls[1]["messages"]
    assert resumed == [
        {"role": "user", "content": "prompt"},
        {"role": "assistant", "content": paused_content},
    ]


def test_pause_turn_continuations_are_capped():
    streams = [_FakeStream([], stop_reason="pause_turn", content=[]) for _ in range(3)]
    claude = _claude(streams)

    assert list(claude.generate_with_web_search("prompt", TOOL, max_continuations=1)) == []
    assert len(claude.client.messages.calls) == 2


def test_closing_the_generator_closes_the_stream():
    stream = _FakeStream(
        [_text("One. "), _text("Two. "), _text("Three. ")],
        stop_reason="end_turn",
        content=[],
    )
    gen = _claude([stream]).generate_with_web_search("prompt", TOOL)

    assert next(gen) == ("sentence", "One.")
    gen.close()  # what ConvFillSystem.backend_fn does on cancel
    assert stream.closed


class _FakeModelBackend:
    def __init__(self, events):
        self.events = events
        self.calls = []

    def infer_with_web_search(self, prompt, web_search_tool, max_continuations):
        self.calls.append((prompt, web_search_tool, max_continuations))
        yield from self.events


def _backend(model_backend, task_specific_config=None):
    dsm = SimpleNamespace(get_transcript=lambda: "User: who won the Mariners game last night")
    return ConvFillBackend(
        dsm,
        WEB_SEARCH_TEMPLATE,
        model_backend,
        mode="web_search",
        task_specific_config=task_specific_config,
    )


def test_web_search_mode_yields_only_sentences():
    model_backend = _FakeModelBackend([
        ("search", "Mariners score"),
        ("search_error", "unavailable"),
        ("sentence", "The Mariners won."),
    ])
    backend = _backend(model_backend, {"max_uses": 2, "max_continuations": 1})

    assert list(backend.backend_infer()) == ["The Mariners won."]
    prompt, tool, max_continuations = model_backend.calls[0]
    assert tool == {"type": "web_search_20250305", "name": "web_search", "max_uses": 2}
    assert max_continuations == 1
    assert "User: who won the Mariners game last night" in prompt


def test_web_search_mode_defaults_and_user_location():
    location = {"type": "approximate", "city": "Seattle", "region": "Washington", "country": "US"}
    backend = _backend(_FakeModelBackend([]), {"user_location": location})

    assert backend.web_search_tool == {
        "type": "web_search_20250305",
        "name": "web_search",
        "max_uses": 3,
        "user_location": location,
    }
    assert backend.max_continuations == 2


def test_web_search_prompt_includes_todays_date():
    backend = _backend(_FakeModelBackend([]))

    prompt = backend.build_prompt_web_search("User: hi", today=datetime.date(2026, 9, 7))

    assert "Today is Monday, September 7, 2026." in prompt
    assert prompt.rstrip().endswith("User: hi")


def test_web_search_requires_a_claude_reasoner():
    from src.inference.convfill_stack.model_inference_functions_conversational import BackendInference

    inference = BackendInference(api_key="unused", model_name="gpt-5", model_mode="openai")
    with pytest.raises(ValueError, match="Claude Reasoner"):
        list(inference.infer_with_web_search("prompt", TOOL))
