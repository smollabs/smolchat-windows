"""Local inference runtime.

The desktop app talks only to :class:`InferenceEngine` (an abstract interface)
and :class:`RuntimeManager` (lifecycle: load / generate / unload, one model in
memory at a time). The llama.cpp implementation is one engine among possibly
many – a future ``smol-runtime`` package can register its own engine with
:func:`register_engine` without touching the UI or backend.
"""

from __future__ import annotations

import functools
import gc
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .config import available_memory_bytes

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- types


@dataclass
class ChatMessage:
    role: str  # "system" | "user" | "assistant"
    content: str
    images: list[str] = field(default_factory=list)  # absolute file paths


@dataclass
class GenerationParams:
    temperature: float = 0.7
    max_tokens: int = 1024
    top_p: float = 0.9
    repeat_penalty: float = 1.1


@dataclass
class GenerationResult:
    text: str
    tokens: int
    seconds: float
    stopped: bool = False
    finish_reason: str = ""

    @property
    def tokens_per_second(self) -> float:
        return self.tokens / self.seconds if self.seconds > 0 else 0.0


@dataclass
class LoadSpec:
    model_id: str
    model_path: Path
    mmproj_path: Path | None = None
    context_length: int = 4096
    use_gpu: bool = True
    chat_style: str = ""  # registry family, lets engines pick model-specific handling


class InferenceError(Exception):
    """A user-presentable runtime failure."""


TokenCallback = Callable[[str], None]
StopCheck = Callable[[], bool]


class InferenceEngine(ABC):
    """Interface every inference backend implements."""

    name: str = "engine"

    @abstractmethod
    def load(self, spec: LoadSpec) -> None: ...

    @abstractmethod
    def unload(self) -> None: ...

    @property
    @abstractmethod
    def loaded_model_id(self) -> str | None: ...

    @property
    def supports_images(self) -> bool:
        return False

    @abstractmethod
    def generate(
        self,
        messages: list[ChatMessage],
        params: GenerationParams,
        on_token: TokenCallback,
        should_stop: StopCheck,
    ) -> GenerationResult: ...


# ------------------------------------------------------------------ llama.cpp


def llama_cpp_available() -> tuple[bool, str]:
    try:
        import llama_cpp  # noqa: F401
    except Exception as exc:  # ImportError or a broken native library
        return False, str(exc)
    return True, getattr(llama_cpp, "__version__", "")


class LlamaCppEngine(InferenceEngine):
    """GGUF inference through llama-cpp-python (Metal on Apple Silicon).

    The chat template embedded in each GGUF is used verbatim, so every model
    keeps its own tokenizer and prompt format.
    """

    name = "llama.cpp"

    def __init__(self) -> None:
        self._llm = None
        self._spec: LoadSpec | None = None
        self._vision = False

    @property
    def loaded_model_id(self) -> str | None:
        return self._spec.model_id if self._llm is not None and self._spec else None

    @property
    def supports_images(self) -> bool:
        return self._vision

    def load(self, spec: LoadSpec) -> None:
        try:
            from llama_cpp import Llama
        except Exception as exc:
            raise InferenceError(
                "The llama.cpp runtime (llama-cpp-python) is not installed or failed to load."
            ) from exc
        if not spec.model_path.is_file():
            raise InferenceError(f"Model file is missing: {spec.model_path.name}")
        chat_handler = None
        if spec.mmproj_path is not None:
            chat_handler = _vision_chat_handler(spec)
        threads = max(1, (os.cpu_count() or 4) - 2)
        try:
            self._llm = Llama(
                model_path=str(spec.model_path),
                n_ctx=spec.context_length,
                n_gpu_layers=-1 if spec.use_gpu else 0,
                n_threads=threads,
                chat_handler=chat_handler,
                verbose=False,
            )
        except Exception as exc:
            self._llm = None
            raise InferenceError(f"llama.cpp could not load the model: {exc}") from exc
        self._spec = spec
        self._vision = chat_handler is not None

    def unload(self) -> None:
        llm, self._llm = self._llm, None
        self._spec = None
        self._vision = False
        if llm is not None:
            close = getattr(llm, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - best-effort cleanup
                    log.exception("Error while closing llama.cpp model")
            del llm
            gc.collect()

    def generate(
        self,
        messages: list[ChatMessage],
        params: GenerationParams,
        on_token: TokenCallback,
        should_stop: StopCheck,
    ) -> GenerationResult:
        if self._llm is None or self._spec is None:
            raise InferenceError("No model is loaded.")
        payload = self._fit_context(messages, params.max_tokens)
        start = time.monotonic()
        pieces: list[str] = []
        tokens = 0
        stopped = False
        finish = ""
        try:
            stream = self._llm.create_chat_completion(
                messages=payload,
                stream=True,
                temperature=params.temperature,
                top_p=params.top_p,
                repeat_penalty=params.repeat_penalty,
                max_tokens=params.max_tokens,
                stop=SMOLVLM_STOP if self._vision else None,
            )
            for chunk in stream:
                if should_stop():
                    stopped = True
                    break
                choice = chunk["choices"][0]
                piece = choice.get("delta", {}).get("content") or ""
                if piece:
                    tokens += 1
                    pieces.append(piece)
                    on_token(piece)
                finish = choice.get("finish_reason") or finish
            if stopped:
                close = getattr(stream, "close", None)
                if callable(close):
                    close()
        except Exception as exc:
            raise InferenceError(f"Generation failed: {exc}") from exc
        return GenerationResult("".join(pieces), tokens, time.monotonic() - start, stopped, finish)

    def _fit_context(self, messages: list[ChatMessage], max_tokens: int) -> list[dict]:
        """Drop the oldest turns until the prompt fits the context window."""
        assert self._llm is not None and self._spec is not None
        budget = self._spec.context_length - max_tokens - 64
        system = [m for m in messages if m.role == "system"]
        rest = [m for m in messages if m.role != "system"]

        def cost(m: ChatMessage) -> int:
            n = len(self._llm.tokenize(m.content.encode("utf-8"), add_bos=False, special=False))
            return n + 8 + 600 * len(m.images)  # role markers + image embedding budget

        used = sum(cost(m) for m in system)
        kept: list[ChatMessage] = []
        for m in reversed(rest):
            c = cost(m)
            if kept and used + c > budget:
                break
            kept.append(m)
            used += c
        kept.reverse()
        return [self._to_payload(m) for m in system + kept]

    def _to_payload(self, m: ChatMessage) -> dict:
        if m.images and self._vision:
            parts: list[dict] = [
                {"type": "image_url", "image_url": {"url": Path(p).resolve().as_uri()}}
                for p in m.images
            ]
            parts.append({"type": "text", "text": m.content})
            return {"role": m.role, "content": parts}
        return {"role": m.role, "content": m.content}


@functools.cache
def vision_supported() -> bool:
    """Whether the installed llama-cpp-python exposes libmtmd, llama.cpp's
    multimodal library (which implements SmolVLM's Idefics3 projector)."""
    try:
        import llama_cpp.mtmd_cpp  # noqa: F401
        from llama_cpp.llama_chat_format import Llava15ChatHandler  # noqa: F401
    except Exception:
        return False
    return True


# SmolVLM / SmolVLM2 chat format, mirroring the template shipped in the
# HuggingFaceTB processor config. Image URLs are rendered inline and replaced
# with libmtmd's media marker by the base handler.
SMOLVLM_CHAT_FORMAT = (
    "<|im_start|>"
    "{% for message in messages %}"
    "{{ message.role | capitalize }}"
    "{% if message.content is string %}"
    ": {{ message.content }}"
    "{% else %}"
    "{% if message.content[0].type == 'image_url' %}:{% else %}: {% endif %}"
    "{% for part in message.content %}"
    "{% if part.type == 'text' %}{{ part.text }}"
    "{% elif part.type == 'image_url' %}"
    "{% if part.image_url is string %}{{ part.image_url }}{% else %}{{ part.image_url.url }}{% endif %}"
    "{% endif %}"
    "{% endfor %}"
    "{% endif %}"
    "<end_of_utterance>\n"
    "{% endfor %}"
    "{% if add_generation_prompt %}Assistant:{% endif %}"
)
SMOLVLM_STOP = ["<end_of_utterance>"]


def _vision_chat_handler(spec: LoadSpec):
    """Create a libmtmd chat handler for a SmolVLM-family projector."""
    if not vision_supported() or spec.mmproj_path is None:
        raise InferenceError("Image understanding is not available in this llama.cpp build.")
    if not spec.mmproj_path.is_file():
        raise InferenceError(f"Vision projector is missing: {spec.mmproj_path.name}")
    import ctypes

    import llama_cpp.mtmd_cpp as mtmd_cpp
    from llama_cpp._logger import llama_log_callback
    from llama_cpp.llama_chat_format import Llava15ChatHandler

    # libmtmd logs to stderr by default; route it through llama-cpp-python's
    # logger so it honours verbose=False like the rest of llama.cpp.
    for setter in ("mtmd_log_set", "mtmd_helper_log_set"):
        try:
            getattr(mtmd_cpp, setter)(llama_log_callback, ctypes.c_void_p(0))
        except Exception:  # pragma: no cover - older bindings
            pass

    class SmolVLMChatHandler(Llava15ChatHandler):
        DEFAULT_SYSTEM_MESSAGE = None
        CHAT_FORMAT = SMOLVLM_CHAT_FORMAT

    return SmolVLMChatHandler(clip_model_path=str(spec.mmproj_path), verbose=False)


# ------------------------------------------------------------- engine registry

EngineFactory = Callable[[], InferenceEngine]
_ENGINES: dict[str, EngineFactory] = {
    "llama_cpp": LlamaCppEngine,
    "llama_cpp_vision": LlamaCppEngine,
}


def register_engine(backend: str, factory: EngineFactory) -> None:
    """Let an external runtime (e.g. ``smol-runtime``) serve a registry backend."""
    _ENGINES[backend] = factory


def create_engine(backend: str) -> InferenceEngine:
    try:
        return _ENGINES[backend]()
    except KeyError:
        raise InferenceError(f"No inference engine is available for backend '{backend}'.")


# ------------------------------------------------------------- runtime manager


class RuntimeManager:
    """Owns the single in-memory model and serialises access to it.

    * Only one model is resident at a time; loading a new one unloads the old.
    * ``load`` and ``generate`` hold the same lock, so a model can never be
      swapped out or deleted mid-generation, and concurrent loads cannot race.
    """

    def __init__(self, engine_factory: Callable[[str], InferenceEngine] = create_engine):
        self._factory = engine_factory
        self._lock = threading.RLock()
        self._engine: InferenceEngine | None = None
        self._backend: str | None = None
        self._generating = threading.Event()
        self._loading_id: str | None = None

    @property
    def loaded_model_id(self) -> str | None:
        engine = self._engine
        return engine.loaded_model_id if engine else None

    @property
    def loading_model_id(self) -> str | None:
        return self._loading_id

    @property
    def is_generating(self) -> bool:
        return self._generating.is_set()

    @property
    def supports_images(self) -> bool:
        engine = self._engine
        return bool(engine and engine.supports_images)

    def is_busy_with(self, model_id: str) -> bool:
        return model_id in (self.loaded_model_id, self._loading_id) and (
            self.is_generating or self._loading_id == model_id
        )

    def ensure_loaded(self, spec: LoadSpec, backend: str, estimated_bytes: int = 0) -> bool:
        """Load ``spec`` unless it is already resident. Returns True if a load happened."""
        with self._lock:
            if self.loaded_model_id == spec.model_id and self._backend == backend:
                return False
            self._loading_id = spec.model_id
            try:
                self._unload_locked()
                if estimated_bytes:
                    free = available_memory_bytes()
                    if estimated_bytes > free * 1.5:
                        log.warning(
                            "Loading %s needs ~%.1f GB but only ~%.1f GB is free",
                            spec.model_id, estimated_bytes / 1e9, free / 1e9,
                        )
                engine = self._factory(backend)
                t0 = time.monotonic()
                engine.load(spec)
                log.info("Loaded %s in %.2fs", spec.model_id, time.monotonic() - t0)
                self._engine, self._backend = engine, backend
                return True
            finally:
                self._loading_id = None

    def unload(self) -> None:
        with self._lock:
            self._unload_locked()

    def _unload_locked(self) -> None:
        if self._engine is not None:
            model_id = self._engine.loaded_model_id
            self._engine.unload()
            log.info("Unloaded %s", model_id)
        self._engine, self._backend = None, None

    def generate(
        self,
        messages: list[ChatMessage],
        params: GenerationParams,
        on_token: TokenCallback,
        should_stop: StopCheck,
    ) -> GenerationResult:
        with self._lock:
            if self._engine is None:
                raise InferenceError("No model is loaded.")
            self._generating.set()
            try:
                return self._engine.generate(messages, params, on_token, should_stop)
            finally:
                self._generating.clear()
