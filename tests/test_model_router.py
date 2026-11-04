from app.config import AppPaths
from app.model_manager import ModelRegistry
from app.model_router import RouteRequest, SystemState, classify, route

REGISTRY = ModelRegistry.load(AppPaths.default().registry_file)
GB = 1024**3


def models(*ids):
    return [REGISTRY.get(i) for i in ids]


ROOMY = SystemState(available_bytes=12 * GB, total_bytes=16 * GB)
TEXT_MODELS = models("smollm2-135m-instruct", "smollm2-360m-instruct", "smollm2-1.7b-instruct", "smollm3-3b")


def test_classify():
    assert classify(RouteRequest("hi"))[0] == "chat"
    assert classify(RouteRequest("hi"))[1] < 0.1
    task, c = classify(RouteRequest("Explain step by step how to debug this Python function and compare approaches"))
    assert task == "chat" and c > 0.6
    assert classify(RouteRequest("what is this?", has_images=True))[0] == "vision"
    assert classify(RouteRequest("extract the table from this invoice", has_images=True))[0] == "document"


def test_simple_question_gets_light_model():
    d = route(RouteRequest("hello!"), TEXT_MODELS, ROOMY)
    assert d.model_id in ("smollm2-135m-instruct", "smollm2-360m-instruct")


def test_complex_question_gets_large_model():
    d = route(
        RouteRequest("Explain in detail why this Python code raises an exception and refactor the function:\n```python\nx = 1\n```"),
        TEXT_MODELS, ROOMY,
    )
    assert d.model_id == "smollm3-3b"


def test_preference_shifts_choice():
    req = RouteRequest("Summarize the plot of Hamlet")
    fast = route(req, TEXT_MODELS, ROOMY, preference="speed")
    best = route(req, TEXT_MODELS, ROOMY, preference="quality")
    assert REGISTRY.get(fast.model_id).quality < REGISTRY.get(best.model_id).quality


def test_only_installed_models_are_considered():
    d = route(RouteRequest("Explain quantum computing in detail"), models("smollm-135m-instruct"), ROOMY)
    assert d.model_id == "smollm-135m-instruct"  # best available, never triggers a download


def test_no_models_explains():
    d = route(RouteRequest("hello"), [], ROOMY)
    assert not d.ok and "Model Library" in d.reason


def test_image_requires_vision_model():
    d = route(RouteRequest("what's in this picture?", has_images=True), TEXT_MODELS, ROOMY)
    assert not d.ok and "SmolVLM" in d.reason
    d = route(
        RouteRequest("what's in this picture?", has_images=True),
        TEXT_MODELS + models("smolvlm2-500m-instruct"), ROOMY,
    )
    assert d.model_id == "smolvlm2-500m-instruct" and d.task == "vision"


def test_text_chat_prefers_language_models_over_vlms():
    d = route(RouteRequest("Tell me a joke"), models("smollm2-360m-instruct", "smolvlm2-500m-instruct"), ROOMY)
    assert d.model_id == "smollm2-360m-instruct"


def test_unsupported_models_are_never_routed():
    d = route(RouteRequest("read this page", has_images=True), models("smoldocling-256m", "colsmol-256m"), ROOMY)
    assert not d.ok


def test_memory_pressure_falls_back_to_smaller_model():
    tight = SystemState(available_bytes=int(0.6 * GB), total_bytes=4 * GB)
    d = route(RouteRequest("Explain in detail how compilers optimise code step by step"), TEXT_MODELS, tight)
    assert REGISTRY.get(d.model_id).params_b < 1.0


def test_loaded_model_is_preferred_when_close():
    req = RouteRequest("What's a good name for a cat?")
    base = route(req, TEXT_MODELS, ROOMY)
    other = "smollm2-360m-instruct" if base.model_id != "smollm2-360m-instruct" else "smollm2-135m-instruct"
    sticky = route(req, TEXT_MODELS, SystemState(12 * GB, 16 * GB, loaded_model_id=other, loaded_model_bytes=GB // 2))
    assert sticky.model_id == other
