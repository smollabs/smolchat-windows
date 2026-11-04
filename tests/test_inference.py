import os
from pathlib import Path

import pytest

from app.inference import (
    SMOLVLM_CHAT_FORMAT,
    ChatMessage,
    GenerationParams,
    InferenceEngine,
    InferenceError,
    LoadSpec,
    RuntimeManager,
)


class FakeEngine(InferenceEngine):
    """Records lifecycle calls; used to test RuntimeManager in isolation."""

    log: list[str] = []

    def __init__(self):
        self._id = None

    @property
    def loaded_model_id(self):
        return self._id

    def load(self, spec):
        if spec.model_id == "broken":
            raise InferenceError("cannot load")
        FakeEngine.log.append(f"load:{spec.model_id}")
        self._id = spec.model_id

    def unload(self):
        FakeEngine.log.append(f"unload:{self._id}")
        self._id = None

    def generate(self, messages, params, on_token, should_stop):
        from app.inference import GenerationResult

        out = []
        for word in ["Hello", " from", " ", self._id]:
            if should_stop():
                return GenerationResult("".join(out), len(out), 0.01, stopped=True)
            on_token(word)
            out.append(word)
        return GenerationResult("".join(out), len(out), 0.01)


def spec(model_id):
    return LoadSpec(model_id=model_id, model_path=Path("/dev/null"))


@pytest.fixture
def runtime():
    FakeEngine.log = []
    return RuntimeManager(lambda backend: FakeEngine())


def test_only_one_model_resident_and_switching_unloads(runtime):
    assert runtime.ensure_loaded(spec("a"), "fake") is True
    assert runtime.ensure_loaded(spec("a"), "fake") is False  # already loaded: no-op
    runtime.ensure_loaded(spec("b"), "fake")
    assert FakeEngine.log == ["load:a", "unload:a", "load:b"]
    assert runtime.loaded_model_id == "b"
    runtime.unload()
    assert runtime.loaded_model_id is None


def test_failed_load_leaves_runtime_empty_and_usable(runtime):
    runtime.ensure_loaded(spec("a"), "fake")
    with pytest.raises(InferenceError):
        runtime.ensure_loaded(spec("broken"), "fake")
    assert runtime.loaded_model_id is None
    runtime.ensure_loaded(spec("c"), "fake")
    assert runtime.loaded_model_id == "c"


def test_generate_streams_and_stops(runtime):
    with pytest.raises(InferenceError):
        runtime.generate([], GenerationParams(), lambda t: None, lambda: False)
    runtime.ensure_loaded(spec("m"), "fake")
    tokens = []
    result = runtime.generate([ChatMessage("user", "hi")], GenerationParams(), tokens.append, lambda: False)
    assert "".join(tokens) == result.text == "Hello from m"
    assert not runtime.is_generating
    stopped = runtime.generate([], GenerationParams(), tokens.append, lambda: len(tokens) > 5)
    assert stopped.stopped


def test_smolvlm_template_matches_reference_format():
    from jinja2.sandbox import ImmutableSandboxedEnvironment

    template = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True).from_string(
        SMOLVLM_CHAT_FORMAT
    )
    text = template.render(
        messages=[
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "file:///x.png"}},
                {"type": "text", "text": "What is this?"},
            ]},
            {"role": "assistant", "content": "A cat."},
            {"role": "user", "content": "Thanks"},
        ],
        add_generation_prompt=True,
    )
    # Same shape as Hugging Face's "User:<image>What is this?" – the URL is later
    # swapped for libmtmd's media marker.
    assert text == (
        "<|im_start|>User:file:///x.pngWhat is this?<end_of_utterance>\n"
        "Assistant: A cat.<end_of_utterance>\n"
        "User: Thanks<end_of_utterance>\n"
        "Assistant:"
    )


@pytest.mark.skipif(not os.environ.get("SMOLCHAT_TEST_GGUF"), reason="set SMOLCHAT_TEST_GGUF=/path/model.gguf")
def test_real_llama_cpp_generation():
    """Integration test against a real GGUF (e.g. SmolLM2-135M-Instruct)."""
    from app.inference import LlamaCppEngine

    engine = LlamaCppEngine()
    engine.load(LoadSpec("real", Path(os.environ["SMOLCHAT_TEST_GGUF"]), context_length=1024))
    try:
        pieces = []
        result = engine.generate(
            [ChatMessage("user", "What is the capital of France? Answer in one word.")],
            GenerationParams(temperature=0.0, max_tokens=16),
            pieces.append,
            lambda: False,
        )
        assert result.tokens > 0 and "".join(pieces) == result.text
        assert "paris" in result.text.lower()
    finally:
        engine.unload()
    assert engine.loaded_model_id is None
