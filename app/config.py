"""Application paths, user settings, and hardware detection.

Data is stored in standard per-user locations for each operating system.
Set ``SMOLCHAT_HOME`` to relocate all app data under one directory.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import platform
import subprocess
import sys
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

log = logging.getLogger(__name__)

APP_NAME = "smolchat"
ORG_NAME = "smollabs"
APP_VERSION = "0.1.0"


def resource_root() -> Path:
    """Directory containing ``ui/`` and ``resources/`` (works when frozen)."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root)
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class AppPaths:
    """All on-disk locations used by the application."""

    data: Path
    cache: Path
    logs: Path

    @property
    def models(self) -> Path:
        return self.data / "models"

    @property
    def metadata(self) -> Path:
        return self.data / "metadata"

    @property
    def attachments(self) -> Path:
        return self.data / "attachments"

    @property
    def settings_file(self) -> Path:
        return self.data / "settings.json"

    @property
    def database(self) -> Path:
        return self.data / "chats.sqlite3"

    @property
    def downloads(self) -> Path:
        return self.cache / "downloads"

    @property
    def registry_file(self) -> Path:
        return resource_root() / "resources" / "models.json"

    @classmethod
    def default(cls) -> "AppPaths":
        override = os.environ.get("SMOLCHAT_HOME")
        if override:
            root = Path(override).expanduser()
            return cls(data=root / "data", cache=root / "cache", logs=root / "logs")
        if sys.platform == "win32":
            local_app_data = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
            root = local_app_data / ORG_NAME / APP_NAME
            return cls(data=root, cache=root / "cache", logs=root / "logs")
        if sys.platform == "darwin":
            lib = Path.home() / "Library"
            return cls(
                data=lib / "Application Support" / ORG_NAME / APP_NAME,
                cache=lib / "Caches" / ORG_NAME / APP_NAME,
                logs=lib / "Logs" / ORG_NAME / APP_NAME,
            )
        xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        xdg_cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        return cls(
            data=xdg_data / ORG_NAME / APP_NAME,
            cache=xdg_cache / ORG_NAME / APP_NAME,
            logs=Path.home() / ".local" / "state" / ORG_NAME / APP_NAME,
        )

    def ensure(self) -> None:
        for path in (
            self.data, self.models, self.metadata, self.attachments, self.downloads, self.logs
        ):
            path.mkdir(parents=True, exist_ok=True)


@dataclass
class Settings:
    """User-configurable preferences persisted as JSON."""

    theme: str = "dark"  # "dark" | "light" | "system"
    accent: str = "violet"  # blue | violet | green | orange | pink | graphite
    # Router bias: "speed" favours small models, "quality" favours large ones.
    routing_preference: str = "balanced"
    default_model_id: str = ""  # model used for manual mode in new chats
    temperature: float = 0.7
    max_tokens: int = 1024
    context_length: int = 4096
    system_prompt: str = "You are smolchat, a helpful assistant running locally on the user's device."
    use_gpu: bool = True  # Metal on macOS; build-dependent GPU offload on Windows
    # SmolLM3 can "think" before answering; slower but better at hard problems.
    enable_thinking: bool = False

    @classmethod
    def load(cls, path: Path) -> "Settings":
        try:
            raw = json.loads(path.read_text("utf-8"))
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError) as exc:
            log.warning("Ignoring unreadable settings file %s: %s", path, exc)
            return cls()
        known = {f.name: f for f in fields(cls)}
        values = {}
        for key, value in raw.items():
            if key in known:
                values[key] = value
        try:
            return cls(**values)
        except TypeError:
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), indent=2), "utf-8")
        tmp.replace(path)


def _sysctl(name: str) -> str:
    try:
        return subprocess.run(
            ["sysctl", "-n", name], capture_output=True, text=True, timeout=2, check=True
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _windows_memory_status() -> tuple[int, int]:
    """Return total and currently available physical memory on Windows."""
    if sys.platform != "win32":
        return 0, 0

    class MemoryStatusEx(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatusEx()
    status.dwLength = ctypes.sizeof(status)
    try:
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys), int(status.ullAvailPhys)
    except (AttributeError, OSError):
        log.exception("Could not query Windows memory status")
    return 0, 0


def _llama_gpu_backend() -> str:
    """Report whether the installed llama.cpp build has GPU offload support."""
    try:
        from llama_cpp import llama_cpp

        if llama_cpp.llama_supports_gpu_offload():
            return "GPU"
    except Exception:
        pass
    return ""


@dataclass
class HardwareInfo:
    """A snapshot of the machine's capabilities relevant to local inference."""

    arch: str
    chip: str
    total_ram_bytes: int
    cpu_cores: int
    apple_silicon: bool
    metal: bool
    os_name: str = ""
    os_major: int = 0
    extra: dict = field(default_factory=dict)
    gpu_backend: str = ""

    @property
    def total_ram_gb(self) -> float:
        return self.total_ram_bytes / 1024**3

    @classmethod
    def detect(cls) -> "HardwareInfo":
        arch = platform.machine()
        is_mac = sys.platform == "darwin"
        chip = _sysctl("machdep.cpu.brand_string") if is_mac else (
            platform.processor() or platform.uname().processor
        )
        total = int(_sysctl("hw.memsize") or 0) if is_mac else 0
        if sys.platform == "win32":
            total = _windows_memory_status()[0]
        if not total:
            try:
                total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
            except (ValueError, OSError, AttributeError):
                total = 8 * 1024**3
        apple_silicon = is_mac and arch == "arm64"
        if is_mac:
            version = platform.mac_ver()[0] or "0"
            os_name = f"macOS {version}"
        else:
            version = platform.release() or "0"
            os_name = f"{platform.system()} {version}"
        try:
            os_major = int(version.split(".")[0])
        except ValueError:
            os_major = 0
        return cls(
            arch=arch,
            chip=chip or arch,
            total_ram_bytes=total,
            cpu_cores=os.cpu_count() or 4,
            apple_silicon=apple_silicon,
            metal=apple_silicon and os_major >= 13,
            os_name=os_name,
            os_major=os_major,
            gpu_backend=_llama_gpu_backend() if sys.platform == "win32" else "",
        )


def available_memory_bytes() -> int:
    """Best-effort estimate of memory that can be used without heavy swapping.

    Windows uses GlobalMemoryStatusEx; macOS uses vm_stat; other platforms
    use sysconf when available.

    On macOS this counts free, inactive, purgeable and speculative pages
    reported by ``vm_stat`` – the same pages the kernel will hand out on
    demand.
    """
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["vm_stat"], capture_output=True, text=True, timeout=2, check=True
            ).stdout
        except (OSError, subprocess.SubprocessError):
            out = ""
        if out:
            page_size = 4096
            first = out.splitlines()[0]
            if "page size of" in first:
                try:
                    page_size = int(first.split("page size of")[1].split()[0])
                except (IndexError, ValueError):
                    pass
            counts: dict[str, int] = {}
            for line in out.splitlines()[1:]:
                if ":" in line:
                    key, _, value = line.partition(":")
                    try:
                        counts[key.strip()] = int(value.strip().rstrip("."))
                    except ValueError:
                        continue
            pages = sum(
                counts.get(k, 0)
                for k in ("Pages free", "Pages inactive", "Pages purgeable", "Pages speculative")
            )
            if pages:
                return pages * page_size
    if sys.platform == "win32":
        available = _windows_memory_status()[1]
        if available:
            return available
    try:
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_AVPHYS_PAGES")
    except (ValueError, OSError, AttributeError):
        return HardwareInfo.detect().total_ram_bytes // 2


def configure_logging(paths: AppPaths) -> None:
    paths.logs.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        from logging.handlers import RotatingFileHandler

        handlers.append(
            RotatingFileHandler(paths.logs / "smolchat.log", maxBytes=2_000_000, backupCount=3)
        )
    except OSError:
        pass
    logging.basicConfig(
        level=os.environ.get("SMOLCHAT_LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        handlers=handlers,
    )
