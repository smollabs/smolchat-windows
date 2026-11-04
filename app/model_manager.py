"""Model registry, local model storage and resumable downloads.

This module is deliberately Qt-free so it can be unit-tested and reused by a
future ``smol-runtime`` package. The Qt bridge lives in :mod:`app.backend`.

Layout on disk::

    <data>/models/<model-id>/<file>.gguf     – verified weights
    <data>/metadata/<model-id>.json          – install manifest
    <cache>/downloads/<model-id>/<file>.part – partial downloads (resumable)
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable

from .config import APP_NAME, APP_VERSION, AppPaths

log = logging.getLogger(__name__)

HF_BASE_URL = "https://huggingface.co"
CHUNK_SIZE = 1024 * 1024
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+https://huggingface.co/HuggingFaceTB)"

CAPABILITY_LABELS = {
    "chat": "Text & Chat",
    "vision": "Vision",
    "document": "Documents",
    "retrieval": "Retrieval",
}


@dataclass(frozen=True)
class ModelFile:
    role: str  # "model" | "mmproj"
    filename: str
    size: int
    sha256: str | None = None


@dataclass(frozen=True)
class ModelEntry:
    """One downloadable model as described by ``resources/models.json``."""

    id: str
    name: str
    family: str
    parameters: str
    params_b: float
    quality: float
    description: str
    capabilities: tuple[str, ...]
    backend: str | None
    repo: str
    revision: str
    source: str
    license: str
    quantization: str
    context_length: int
    recommended_ram_gb: int
    files: tuple[ModelFile, ...]
    base_model: str = ""
    unsupported_reason: str = ""

    @property
    def supported(self) -> bool:
        return self.backend is not None and bool(self.files)

    @property
    def download_size(self) -> int:
        return sum(f.size for f in self.files)

    @property
    def primary_category(self) -> str:
        for cap in ("document", "retrieval", "vision", "chat"):
            if cap in self.capabilities:
                return cap
        return "chat"

    def estimated_ram_bytes(self, context_length: int = 4096) -> int:
        """Rough resident-memory estimate: weights + KV cache + runtime overhead."""
        weights = self.download_size
        # KV cache grows with parameter count and context; ~72 KB/token for SmolLM3 3B (fp16).
        kv = int(self.params_b * 24_000 * min(context_length, self.context_length or context_length))
        return int(weights * 1.05) + kv + 150 * 1024**2

    def file_url(self, file: ModelFile) -> str:
        return f"{HF_BASE_URL}/{self.repo}/resolve/{self.revision}/{file.filename}"

    @property
    def page_url(self) -> str:
        return f"{HF_BASE_URL}/{self.repo}"

    @classmethod
    def from_dict(cls, raw: dict) -> "ModelEntry":
        return cls(
            id=raw["id"],
            name=raw["name"],
            family=raw["family"],
            parameters=raw["parameters"],
            params_b=float(raw["params_b"]),
            quality=float(raw.get("quality", raw["params_b"])),
            description=raw.get("description", ""),
            capabilities=tuple(raw.get("capabilities", ["chat"])),
            backend=raw.get("backend"),
            repo=raw["repo"],
            revision=raw.get("revision", "main"),
            source=raw.get("source", ""),
            license=raw.get("license", ""),
            quantization=raw.get("quantization", ""),
            context_length=int(raw.get("context_length", 2048)),
            recommended_ram_gb=int(raw.get("recommended_ram_gb", 8)),
            files=tuple(ModelFile(**f) for f in raw.get("files", [])),
            base_model=raw.get("base_model", ""),
            unsupported_reason=raw.get("unsupported_reason", ""),
        )


class ModelRegistry:
    """The catalogue of models smolchat knows how to obtain."""

    def __init__(self, entries: Iterable[ModelEntry]):
        self._entries = {e.id: e for e in entries}

    @classmethod
    def load(cls, path: Path) -> "ModelRegistry":
        data = json.loads(path.read_text("utf-8"))
        return cls(ModelEntry.from_dict(m) for m in data["models"])

    def get(self, model_id: str) -> ModelEntry | None:
        return self._entries.get(model_id)

    def all(self) -> list[ModelEntry]:
        return list(self._entries.values())

    def __len__(self) -> int:
        return len(self._entries)


@dataclass
class InstalledModel:
    entry: ModelEntry
    directory: Path
    installed_at: str

    def path_for(self, role: str) -> Path | None:
        for f in self.entry.files:
            if f.role == role:
                return self.directory / f.filename
        return None


class ModelStore:
    """Tracks which registry models are installed on disk."""

    def __init__(self, paths: AppPaths, registry: ModelRegistry):
        self.paths = paths
        self.registry = registry

    def model_dir(self, model_id: str) -> Path:
        return self.paths.models / model_id

    def manifest_path(self, model_id: str) -> Path:
        return self.paths.metadata / f"{model_id}.json"

    def partial_dir(self, model_id: str) -> Path:
        return self.paths.downloads / model_id

    def installed(self) -> dict[str, InstalledModel]:
        """Scan the disk; a model counts as installed only if every file is present
        with the expected size. Works fully offline."""
        result: dict[str, InstalledModel] = {}
        if not self.paths.metadata.exists():
            return result
        for manifest in sorted(self.paths.metadata.glob("*.json")):
            try:
                data = json.loads(manifest.read_text("utf-8"))
            except (OSError, ValueError):
                log.warning("Unreadable manifest %s", manifest)
                continue
            entry = self.registry.get(data.get("id", manifest.stem))
            if entry is None or not entry.supported:
                continue
            directory = self.model_dir(entry.id)
            if all(
                (directory / f.filename).is_file()
                and (directory / f.filename).stat().st_size == f.size
                for f in entry.files
            ):
                result[entry.id] = InstalledModel(entry, directory, data.get("installed_at", ""))
            else:
                log.warning("Model %s is incomplete on disk; ignoring", entry.id)
        return result

    def is_installed(self, model_id: str) -> bool:
        return model_id in self.installed()

    def partial_bytes(self, model_id: str) -> int:
        d = self.partial_dir(model_id)
        if not d.exists():
            return 0
        return sum(p.stat().st_size for p in d.glob("*.part"))

    def disk_usage(self, model_id: str) -> int:
        d = self.model_dir(model_id)
        return sum(p.stat().st_size for p in d.glob("*") if p.is_file()) if d.exists() else 0

    def register(self, entry: ModelEntry) -> InstalledModel:
        manifest = {
            "id": entry.id,
            "repo": entry.repo,
            "revision": entry.revision,
            "files": [
                {"role": f.role, "filename": f.filename, "size": f.size, "sha256": f.sha256}
                for f in entry.files
            ],
            "installed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        path = self.manifest_path(entry.id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(manifest, indent=2), "utf-8")
        tmp.replace(path)
        return InstalledModel(entry, self.model_dir(entry.id), manifest["installed_at"])

    def delete(self, model_id: str) -> None:
        """Remove weights, manifest and any partial download for ``model_id``."""
        self.manifest_path(model_id).unlink(missing_ok=True)
        shutil.rmtree(self.model_dir(model_id), ignore_errors=True)
        shutil.rmtree(self.partial_dir(model_id), ignore_errors=True)

    def discard_partial(self, model_id: str) -> None:
        shutil.rmtree(self.partial_dir(model_id), ignore_errors=True)


class DownloadCancelled(Exception):
    pass


class DownloadError(Exception):
    pass


@dataclass
class DownloadProgress:
    model_id: str
    downloaded: int
    total: int
    speed_bps: float = 0.0
    stage: str = "downloading"  # "preparing" (re-checking a partial) | "downloading" | "verifying"

    @property
    def fraction(self) -> float:
        return self.downloaded / self.total if self.total else 0.0


ProgressCallback = Callable[[DownloadProgress], None]
Opener = Callable[[urllib.request.Request], "object"]


@dataclass
class _SpeedMeter:
    window: list[tuple[float, int]] = field(default_factory=list)

    def update(self, done: int) -> float:
        now = time.monotonic()
        self.window.append((now, done))
        while len(self.window) > 2 and now - self.window[0][0] > 3.0:
            self.window.pop(0)
        t0, d0 = self.window[0]
        return (done - d0) / (now - t0) if now > t0 else 0.0


class ModelDownloader:
    """Downloads every file of a model with HTTP range resume and SHA-256 checks.

    ``download`` is blocking and meant to run on a worker thread; call
    ``cancel()`` from any thread to stop it. Partial files are kept so the next
    attempt resumes where this one stopped.
    """

    def __init__(
        self,
        store: ModelStore,
        entry: ModelEntry,
        on_progress: ProgressCallback | None = None,
        opener: Opener | None = None,
        timeout: float = 30.0,
    ):
        self.store = store
        self.entry = entry
        self.on_progress = on_progress or (lambda p: None)
        self._open = opener or (lambda req: urllib.request.urlopen(req, timeout=timeout))
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancelled(self) -> bool:
        return self._cancel.is_set()

    def download(self) -> InstalledModel:
        entry = self.entry
        if not entry.supported:
            raise DownloadError(f"{entry.name} is not supported by smolchat's runtime.")
        partial_dir = self.store.partial_dir(entry.id)
        partial_dir.mkdir(parents=True, exist_ok=True)
        self._check_disk_space(partial_dir)

        total = entry.download_size
        done_before = 0
        meter = _SpeedMeter()
        last_emit = 0.0

        for file in entry.files:
            part = partial_dir / f"{file.filename}.part"

            def report(file_done: int, stage: str = "downloading", force: bool = False) -> None:
                nonlocal last_emit
                now = time.monotonic()
                if force or now - last_emit >= 0.1:
                    last_emit = now
                    done = done_before + file_done
                    speed = meter.update(done) if stage == "downloading" else 0.0
                    self.on_progress(DownloadProgress(entry.id, done, total, speed, stage))

            digest = self._fetch(file, part, report)
            report(file.size, "verifying", force=True)
            if file.sha256 and digest != file.sha256:
                part.unlink(missing_ok=True)
                raise DownloadError(
                    f"Checksum mismatch for {file.filename}. The partial file was removed; "
                    "please try again."
                )
            done_before += file.size

        # Every file verified: move into place atomically per file, then register.
        target = self.store.model_dir(entry.id)
        target.mkdir(parents=True, exist_ok=True)
        for file in entry.files:
            (partial_dir / f"{file.filename}.part").replace(target / file.filename)
        shutil.rmtree(partial_dir, ignore_errors=True)
        installed = self.store.register(entry)
        log.info("Installed %s (%d bytes)", entry.id, total)
        return installed

    def _check_disk_space(self, directory: Path) -> None:
        needed = self.entry.download_size - self.store.partial_bytes(self.entry.id)
        free = shutil.disk_usage(directory).free
        if needed > free - 200 * 1024**2:
            raise DownloadError(
                f"Not enough disk space: {needed / 1024**3:.2f} GB needed, "
                f"{free / 1024**3:.2f} GB free."
            )

    def _fetch(self, file: ModelFile, part: Path, report: Callable[..., None]) -> str:
        """Download ``file`` into ``part`` (resuming if possible); return its sha256."""
        hasher = hashlib.sha256()
        offset = part.stat().st_size if part.exists() else 0
        if offset > file.size:
            part.unlink()
            offset = 0
        if offset:
            # Re-hash what we already have so the final digest covers the whole file.
            hashed = 0
            with part.open("rb") as fh:
                while chunk := fh.read(CHUNK_SIZE):
                    if self._cancel.is_set():
                        raise DownloadCancelled()
                    hasher.update(chunk)
                    hashed += len(chunk)
                    report(hashed, "preparing")
        if offset == file.size:
            return hasher.hexdigest()

        req = urllib.request.Request(self.entry.file_url(file), headers={"User-Agent": USER_AGENT})
        if offset:
            req.add_header("Range", f"bytes={offset}-")
        try:
            resp = self._open(req)
        except urllib.error.HTTPError as exc:
            if exc.code == 416:  # range not satisfiable: start over
                part.unlink(missing_ok=True)
                return self._fetch(file, part, report)
            raise DownloadError(f"Server returned HTTP {exc.code} for {file.filename}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise DownloadError(
                "Could not reach Hugging Face. Check your internet connection and try again."
            ) from exc

        with resp:
            status = getattr(resp, "status", 200)
            mode = "ab"
            if offset and status != 206:
                # Server ignored the range request; restart from scratch.
                hasher = hashlib.sha256()
                offset = 0
                mode = "wb"
            done = offset
            try:
                with part.open(mode) as out:
                    while True:
                        if self._cancel.is_set():
                            raise DownloadCancelled()
                        chunk = resp.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        out.write(chunk)
                        hasher.update(chunk)
                        done += len(chunk)
                        report(done)
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                raise DownloadError(
                    "The connection was interrupted. Download again to resume."
                ) from exc
        if done != file.size:
            raise DownloadError(
                f"Incomplete download of {file.filename} ({done} of {file.size} bytes). "
                "Download again to resume."
            )
        return hasher.hexdigest()


# ------------------------------------------------------------ compatibility

GIB = 1024**3
# Memory reserved for the operating system and everyday apps.
SYSTEM_RESERVE_BYTES = int(3.5 * GIB)
# Free space to leave on the disk after a download.
DISK_HEADROOM_BYTES = 2_000_000_000


@dataclass(frozen=True)
class DeviceProfile:
    """What smolchat needs to know about the device to judge a model."""

    os_name: str  # e.g. "macOS 15.1"
    os_major: int
    chip: str
    total_ram_bytes: int
    free_disk_bytes: int
    apple_silicon: bool
    gpu_backend: str = ""

    @property
    def gpu_acceleration(self) -> bool:
        # Metal is available on Apple Silicon; Windows GPU support depends on
        # the installed llama.cpp build (CUDA/Vulkan/etc.), not just the GPU.
        return (self.apple_silicon and self.os_major >= 13) or bool(self.gpu_backend)

    @property
    def model_memory_budget(self) -> int:
        return max(self.total_ram_bytes - SYSTEM_RESERVE_BYTES, self.total_ram_bytes // 4)


@dataclass(frozen=True)
class Compatibility:
    level: str  # "recommended" | "compatible" | "not_recommended" | "unsupported"
    label: str
    reason: str

    @property
    def can_download(self) -> bool:
        return self.level in ("recommended", "compatible")


def assess_compatibility(
    entry: ModelEntry,
    device: DeviceProfile,
    context_length: int = 4096,
    partial_bytes: int = 0,
) -> Compatibility:
    """Judge whether ``entry`` will run comfortably on ``device``.

    Models that would push the device into heavy swapping, run unbearably slowly
    on the CPU, or fill the disk are ``not_recommended`` and smolchat refuses
    to download them.
    """
    if not entry.supported:
        return Compatibility("unsupported", "Not yet supported", entry.unsupported_reason)

    needed_disk = max(entry.download_size - partial_bytes, 0)
    if needed_disk + DISK_HEADROOM_BYTES > device.free_disk_bytes:
        return Compatibility(
            "not_recommended",
            "Not enough storage",
            f"Needs {format_bytes(needed_disk)} plus {format_bytes(DISK_HEADROOM_BYTES)} of headroom; "
            f"only {format_bytes(device.free_disk_bytes)} is free on this device.",
        )

    ram_gb = device.total_ram_bytes / GIB
    if ram_gb + 0.25 < entry.recommended_ram_gb:
        return Compatibility(
            "not_recommended",
            "Too large for this device",
            f"Needs {entry.recommended_ram_gb} GB of memory; this device has {ram_gb:.0f} GB. "
            "It would slow your computer down.",
        )

    need = entry.estimated_ram_bytes(context_length)
    budget = device.model_memory_budget
    if need > budget * 0.85:
        return Compatibility(
            "not_recommended",
            "Too large for this device",
            f"Uses about {format_bytes(need)} of memory; with the operating system and your apps that would "
            "cause heavy swapping and slow your computer down.",
        )

    if not device.gpu_acceleration and entry.params_b >= 2:
        return Compatibility(
            "not_recommended",
            "Too slow without GPU",
            "Without GPU acceleration this model would answer very slowly and keep the CPU busy.",
        )

    if need > budget * 0.5 or (not device.gpu_acceleration and entry.params_b >= 1):
        return Compatibility(
            "compatible",
            "Runs, may be slower",
            "Fits in memory, but expect slower replies when other apps are open.",
        )
    return Compatibility("recommended", "Runs well", "Fits comfortably in this device's memory.")


def best_matches(
    entries: Iterable[ModelEntry], device: DeviceProfile, context_length: int = 4096
) -> dict[str, str]:
    """The highest-quality *recommended* model per category ("chat", "vision")."""
    best: dict[str, ModelEntry] = {}
    for e in entries:
        if assess_compatibility(e, device, context_length).level != "recommended":
            continue
        cat = "vision" if "vision" in e.capabilities else "chat"
        current = best.get(cat)
        if current is None or (e.quality, -e.download_size) > (current.quality, -current.download_size):
            best[cat] = e
    return {cat: e.id for cat, e in best.items()}


def format_eta(seconds: float) -> str:
    if seconds <= 0 or seconds == float("inf"):
        return ""
    if seconds < 60:
        return "less than a minute left"
    minutes = round(seconds / 60)
    if minutes < 60:
        return f"about {minutes} min left"
    return f"about {minutes / 60:.1f} h left"


def format_bytes(n: float, precise: bool = False) -> str:
    """Human-readable size using decimal units."""
    if n < 1000:
        return f"{n:.0f} B"
    if n < 1000**2:
        return f"{n / 1000:.0f} KB"
    if n < 1000**3:
        mb = n / 1000**2
        return f"{mb:.1f} MB" if precise and mb < 100 else f"{mb:.0f} MB"
    return f"{n / 1000**3:.2f} GB"
