from app.config import AppPaths
from app.model_manager import (
    DeviceProfile,
    ModelRegistry,
    assess_compatibility,
    best_matches,
    format_eta,
)

REGISTRY = ModelRegistry.load(AppPaths.default().registry_file)
GIB = 1024**3


def mac(ram_gb=8, free_gb=200, apple_silicon=True, os_major=15) -> DeviceProfile:
    return DeviceProfile(
        os_name=f"macOS {os_major}.0", os_major=os_major, chip="Apple M1",
        total_ram_bytes=ram_gb * GIB, free_disk_bytes=free_gb * GIB, apple_silicon=apple_silicon,
    )


def level(model_id, device, **kw):
    return assess_compatibility(REGISTRY.get(model_id), device, **kw).level


def test_small_models_are_recommended_everywhere():
    for ram in (8, 16, 32):
        assert level("smollm2-360m-instruct", mac(ram)) == "recommended"


def test_3b_is_borderline_on_8gb_and_fine_on_16gb():
    assert level("smollm3-3b", mac(8)) == "compatible"
    assert level("smollm3-3b", mac(16)) == "recommended"


def test_models_that_would_slow_the_mac_are_blocked():
    small_intel = mac(ram_gb=4, apple_silicon=False, os_major=12)
    for model_id in ("smollm3-3b", "smolvlm2-2.2b-instruct", "smollm-1.7b-instruct"):
        c = assess_compatibility(REGISTRY.get(model_id), small_intel)
        assert c.level == "not_recommended" and not c.can_download
        assert "slow" in c.reason.lower()
    assert level("smollm2-135m-instruct", small_intel) in ("recommended", "compatible")


def test_cpu_only_macs_avoid_large_models():
    intel = mac(ram_gb=16, apple_silicon=False)
    assert level("smollm3-3b", intel) == "not_recommended"
    assert level("smollm2-1.7b-instruct", intel) == "compatible"


def test_low_storage_blocks_download_but_partial_counts():
    entry = REGISTRY.get("smollm2-1.7b-instruct")  # ~1.06 GB
    tight = mac(free_gb=2)
    c = assess_compatibility(entry, tight)
    assert c.level == "not_recommended" and "storage" in c.label.lower()
    # With most of it already downloaded, resuming fits.
    roomy_enough = DeviceProfile("macOS 15", 15, "M1", 8 * GIB, int(2.2 * GIB), True)
    assert assess_compatibility(entry, roomy_enough, partial_bytes=entry.download_size - 10_000_000).can_download


def test_larger_context_raises_memory_estimate():
    entry = REGISTRY.get("smollm3-3b")
    assert entry.estimated_ram_bytes(8192) > entry.estimated_ram_bytes(2048)


def test_unsupported_models_report_unsupported():
    c = assess_compatibility(REGISTRY.get("colsmol-256m"), mac(32))
    assert c.level == "unsupported" and not c.can_download


def test_best_matches_pick_strongest_recommended_model():
    best8 = best_matches(REGISTRY.all(), mac(8))
    assert best8["chat"] == "smollm2-1.7b-instruct"  # 3B is only "compatible" on 8 GB
    assert "vision" in best8
    best16 = best_matches(REGISTRY.all(), mac(16))
    assert best16["chat"] == "smollm3-3b"


def test_format_eta():
    assert format_eta(30) == "less than a minute left"
    assert format_eta(600) == "about 10 min left"
    assert format_eta(0) == ""
