import hashlib
import io
import json
import threading
import urllib.error

import pytest

from app.config import AppPaths
from app.model_manager import (
    DownloadCancelled,
    DownloadError,
    ModelDownloader,
    ModelEntry,
    ModelRegistry,
    ModelStore,
)


# --------------------------------------------------------------- registry


def test_bundled_registry_is_well_formed():
    registry = ModelRegistry.load(AppPaths.default().registry_file)
    ids = [m.id for m in registry.all()]
    assert len(ids) == len(set(ids)) == 16
    families = {m.family for m in registry.all()}
    assert families == {"SmolLM", "SmolLM2", "SmolLM3", "SmolVLM", "SmolVLM2", "SmolDocling", "ColSmol"}
    for m in registry.all():
        assert len(m.revision) == 40, f"{m.id} must pin a commit"
        if m.supported:
            assert m.files and all(len(f.sha256 or "") == 64 for f in m.files)
            assert all(f.filename.endswith(".gguf") for f in m.files)
            if "vision" in m.capabilities:
                assert {f.role for f in m.files} == {"model", "mmproj"}
        else:
            assert m.unsupported_reason, f"{m.id} must explain why it is unsupported"
        # Never advertise vision on text-only models.
        if m.family in ("SmolLM", "SmolLM2", "SmolLM3"):
            assert m.capabilities == ("chat",)


# ------------------------------------------------------------ fake server

BLOB = bytes(range(256)) * 4096  # 1 MiB of deterministic data
BLOB2 = b"projector" * 10_000


class FakeResponse(io.BytesIO):
    def __init__(self, data: bytes, status: int):
        super().__init__(data)
        self.status = status


class FakeHub:
    """Serves files by name, honouring Range headers like Hugging Face does."""

    def __init__(self, files: dict[str, bytes], honour_range: bool = True):
        self.files = files
        self.honour_range = honour_range
        self.requests: list[tuple[str, str | None]] = []
        self.fail_after: int | None = None

    def __call__(self, req):
        name = req.full_url.rsplit("/", 1)[-1]
        rng = req.get_header("Range")
        self.requests.append((name, rng))
        data = self.files[name]
        if rng and self.honour_range:
            start = int(rng.split("=")[1].rstrip("-"))
            if start >= len(data):
                raise urllib.error.HTTPError(req.full_url, 416, "range", {}, None)
            body, status = data[start:], 206
        else:
            body, status = data, 200
        if self.fail_after is not None:
            body = body[: self.fail_after]
        return FakeResponse(body, status)


def make_entry(files: dict[str, bytes], sha_override: str | None = None) -> ModelEntry:
    raw = {
        "id": "test-model",
        "name": "Test Model",
        "family": "SmolLM2",
        "parameters": "1M",
        "params_b": 0.001,
        "capabilities": ["chat"],
        "backend": "llama_cpp",
        "repo": "org/test",
        "revision": "a" * 40,
        "files": [
            {
                "role": "model" if i == 0 else "mmproj",
                "filename": name,
                "size": len(data),
                "sha256": sha_override or hashlib.sha256(data).hexdigest(),
            }
            for i, (name, data) in enumerate(files.items())
        ],
    }
    return ModelEntry.from_dict(raw)


@pytest.fixture
def setup(paths):
    files = {"model.gguf": BLOB, "mmproj.gguf": BLOB2}
    entry = make_entry(files)
    store = ModelStore(paths, ModelRegistry([entry]))
    return paths, files, entry, store


def test_download_installs_and_registers(setup):
    paths, files, entry, store = setup
    hub = FakeHub(files)
    progress = []
    installed = ModelDownloader(store, entry, progress.append, opener=hub).download()
    assert installed.path_for("model").read_bytes() == BLOB
    assert installed.path_for("mmproj").read_bytes() == BLOB2
    assert store.is_installed("test-model")
    manifest = json.loads(store.manifest_path("test-model").read_text())
    assert manifest["revision"] == "a" * 40
    assert progress[-1].stage == "verifying"
    assert progress[-1].downloaded == entry.download_size
    assert not store.partial_dir("test-model").exists()
    assert hub.requests[0] == ("model.gguf", None)


def test_url_uses_pinned_revision(setup):
    _, _, entry, _ = setup
    assert entry.file_url(entry.files[0]) == (
        "https://huggingface.co/org/test/resolve/" + "a" * 40 + "/model.gguf"
    )


def test_interrupted_download_resumes_with_range(setup):
    paths, files, entry, store = setup
    hub = FakeHub(files)
    hub.fail_after = 300_000
    with pytest.raises(DownloadError):
        ModelDownloader(store, entry, opener=hub).download()
    assert store.partial_bytes("test-model") == 300_000
    assert not store.is_installed("test-model")

    hub.fail_after = None
    ModelDownloader(store, entry, opener=hub).download()
    assert ("model.gguf", "bytes=300000-") in hub.requests
    assert store.is_installed("test-model")
    assert (store.model_dir("test-model") / "model.gguf").read_bytes() == BLOB


def test_resume_restarts_when_server_ignores_range(setup):
    paths, files, entry, store = setup
    partial = store.partial_dir("test-model")
    partial.mkdir(parents=True)
    (partial / "model.gguf.part").write_bytes(BLOB[:1000])
    ModelDownloader(store, entry, opener=FakeHub(files, honour_range=False)).download()
    assert (store.model_dir("test-model") / "model.gguf").read_bytes() == BLOB


def test_checksum_mismatch_is_rejected(paths):
    files = {"model.gguf": BLOB}
    entry = make_entry(files, sha_override="0" * 64)
    store = ModelStore(paths, ModelRegistry([entry]))
    with pytest.raises(DownloadError, match="Checksum"):
        ModelDownloader(store, entry, opener=FakeHub(files)).download()
    assert not store.is_installed("test-model")
    assert store.partial_bytes("test-model") == 0  # corrupt partial removed


def test_cancel_keeps_partial_for_resume(setup):
    paths, files, entry, store = setup
    downloader = ModelDownloader(store, entry, opener=FakeHub(files))
    seen = threading.Event()

    def on_progress(p):
        if p.downloaded > 0:
            downloader.cancel()
            seen.set()

    downloader.on_progress = on_progress
    with pytest.raises(DownloadCancelled):
        downloader.download()
    assert seen.is_set()
    assert 0 < store.partial_bytes("test-model") < entry.download_size
    assert not store.is_installed("test-model")


def test_network_error_is_friendly(setup):
    paths, files, entry, store = setup

    def offline(req):
        raise urllib.error.URLError("no route to host")

    with pytest.raises(DownloadError, match="internet"):
        ModelDownloader(store, entry, opener=offline).download()


def test_unsupported_model_cannot_download(paths):
    entry = ModelEntry.from_dict({
        "id": "colsmol", "name": "ColSmol", "family": "ColSmol", "parameters": "256M",
        "params_b": 0.256, "capabilities": ["retrieval"], "backend": None,
        "repo": "vidore/colSmol-256M", "files": [], "unsupported_reason": "nope",
    })
    store = ModelStore(paths, ModelRegistry([entry]))
    with pytest.raises(DownloadError):
        ModelDownloader(store, entry, opener=FakeHub({})).download()


def test_scan_ignores_incomplete_and_delete_removes_everything(setup):
    paths, files, entry, store = setup
    ModelDownloader(store, entry, opener=FakeHub(files)).download()
    # Truncated weights => not installed
    (store.model_dir("test-model") / "model.gguf").write_bytes(b"short")
    assert not store.is_installed("test-model")
    # Delete cleans weights, manifest and partials
    store.partial_dir("test-model").mkdir(parents=True, exist_ok=True)
    (store.partial_dir("test-model") / "x.part").write_bytes(b"1")
    store.delete("test-model")
    assert not store.model_dir("test-model").exists()
    assert not store.manifest_path("test-model").exists()
    assert not store.partial_dir("test-model").exists()


def test_installed_scan_works_offline_from_disk_only(setup):
    paths, files, entry, store = setup
    ModelDownloader(store, entry, opener=FakeHub(files)).download()
    fresh = ModelStore(paths, ModelRegistry([entry]))  # e.g. after restart, no network
    assert list(fresh.installed()) == ["test-model"]
