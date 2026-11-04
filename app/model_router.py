"""Automatic model selection.

The router is a pure function of (request, installed models, machine state,
preferences) so it is easy to test and reason about. It never triggers a
download: if the ideal model is missing it picks the best installed
alternative, and if nothing compatible is installed it says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .model_manager import ModelEntry

# Words that signal a request needs more reasoning or longer output.
_HEAVY_PATTERNS = [
    r"\b(explain|why|how does|how do|analy[sz]e|compare|contrast|evaluate|reason|prove|derive)\b",
    r"\b(step[- ]by[- ]step|in detail|detailed|thorough|comprehensive|pros and cons)\b",
    r"\b(code|function|class|bug|debug|refactor|algorithm|regex|sql|python|javascript|"
    r"typescript|rust|swift|java|c\+\+|compile|stack ?trace|exception)\b",
    r"\b(math|equation|integral|derivative|calculate|solve|probability|statistics|proof)\b",
    r"\b(essay|article|report|story|poem|letter|summari[sz]e|translate|outline|plan)\b",
]
_LIGHT_PATTERNS = [
    r"^(hi|hello|hey|yo|thanks|thank you|ok|okay|good (morning|evening|night)|bye)\b",
    r"^(what is|who is|define|when (is|was)|where is)\b",
]
_DOCUMENT_PATTERNS = [
    r"\b(document|page|pdf|invoice|receipt|form|table|scan|scanned|ocr|transcribe|extract text)\b",
]
_CODE_FENCE = re.compile(r"```|^\s{4,}\S", re.M)


@dataclass(frozen=True)
class RouteRequest:
    text: str
    has_images: bool = False
    history_turns: int = 0


@dataclass(frozen=True)
class SystemState:
    available_bytes: int
    total_bytes: int
    loaded_model_id: str | None = None
    loaded_model_bytes: int = 0


@dataclass(frozen=True)
class RouteDecision:
    model_id: str | None
    task: str  # "chat" | "vision" | "document"
    complexity: float  # 0..1
    reason: str

    @property
    def ok(self) -> bool:
        return self.model_id is not None


def classify(request: RouteRequest) -> tuple[str, float]:
    """Return ``(task, complexity)`` for a request."""
    text = request.text.strip()
    lowered = text.lower()

    task = "chat"
    if request.has_images:
        task = "vision"
        if any(re.search(p, lowered) for p in _DOCUMENT_PATTERNS):
            task = "document"

    words = len(text.split())
    score = min(words / 120.0, 0.45)
    heavy_hits = sum(1 for p in _HEAVY_PATTERNS if re.search(p, lowered))
    score += 0.22 * heavy_hits
    if _CODE_FENCE.search(text):
        score += 0.3
    if text.count("\n") >= 4:
        score += 0.1
    if words <= 8 and any(re.search(p, lowered) for p in _LIGHT_PATTERNS):
        score -= 0.25
    score += min(request.history_turns, 10) * 0.015
    return task, max(0.0, min(1.0, score))


def target_quality(complexity: float, preference: str) -> float:
    """Map complexity (0..1) to the registry ``quality`` scale (~1 .. 4.5)."""
    target = 1.3 + complexity * 3.4
    if preference == "speed":
        target -= 1.0
    elif preference == "quality":
        target += 1.2
    return target


def _fits(entry: ModelEntry, state: SystemState, context_length: int) -> bool:
    need = entry.estimated_ram_bytes(context_length)
    # Unloading the current model frees its memory before the new one loads.
    usable = state.available_bytes + state.loaded_model_bytes
    hard_cap = state.total_bytes * 0.7
    return need <= max(usable, 0) * 1.25 and need <= hard_cap


def route(
    request: RouteRequest,
    installed: list[ModelEntry],
    state: SystemState,
    preference: str = "balanced",
    context_length: int = 4096,
) -> RouteDecision:
    task, complexity = classify(request)
    needed_cap = {"chat": "chat", "vision": "vision", "document": "vision"}[task]

    candidates = [m for m in installed if m.supported and needed_cap in m.capabilities]
    if task == "document":
        doc_models = [m for m in candidates if "document" in m.capabilities]
        candidates = doc_models or candidates

    if not candidates:
        if task == "chat":
            reason = "No chat model is downloaded yet. Open the Model Library to download one."
        else:
            reason = (
                "This message includes an image, but no installed model understands images. "
                "Download a SmolVLM model from the Model Library."
            )
        return RouteDecision(None, task, complexity, reason)

    fitting = [m for m in candidates if _fits(m, state, context_length)]
    memory_note = ""
    if not fitting:
        smallest = min(candidates, key=lambda m: m.estimated_ram_bytes(context_length))
        fitting = [smallest]
        memory_note = " Memory is tight, so the smallest compatible model was chosen."

    target = target_quality(complexity, preference)

    def score(m: ModelEntry) -> float:
        diff = m.quality - target
        # Being under-powered hurts answer quality more than being over-powered
        # hurts speed, so undershooting costs more.
        s = -abs(diff) * (1.0 if diff < 0 else 0.6)
        if task == "chat" and "vision" in m.capabilities:
            s -= 1.0  # VLMs are weaker at pure-text chat than LMs of the same size
        if m.id == state.loaded_model_id:
            s += 0.35  # avoid a reload when the resident model is good enough
        return s

    best = max(fitting, key=score)
    size_word = (
        "lightweight" if best.quality < 2 else "balanced" if best.quality < 3.2 else "most capable"
    )
    label = {"chat": "Simple question" if complexity < 0.35 else "Detailed request",
             "vision": "Image question",
             "document": "Document question"}[task]
    reason = f"{label} → {best.name} ({size_word} installed model).{memory_note}"
    if task == "document" and "document" not in best.capabilities:
        reason = f"Document question → {best.name}. No document model is installed, so a vision model is used.{memory_note}"
    return RouteDecision(best.id, task, complexity, reason)
