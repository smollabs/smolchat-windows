"""Qt bridge between the QML interface and smolchat's Python services.

QML only ever sees the :class:`Backend` object (properties, slots, signals) and
the list models it exposes. Blocking work – startup scanning, downloads,
model loading and generation – runs on Python worker threads and reports
back through Qt signals, which Qt delivers on the UI thread.
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import (
    Property,
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    QSize,
    Qt,
    QUrl,
    Signal,
    Slot,
)
from PySide6.QtGui import QDesktopServices, QGuiApplication, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

from .config import AppPaths, HardwareInfo, Settings, available_memory_bytes, resource_root
from .database import ChatDatabase, Conversation, suggest_title
from .formatting import DARK_SYNTAX, LIGHT_SYNTAX, segment_message, strip_reasoning
from .inference import (
    ChatMessage,
    GenerationParams,
    InferenceError,
    LoadSpec,
    RuntimeManager,
    llama_cpp_available,
)
from .model_manager import (
    CAPABILITY_LABELS,
    DeviceProfile,
    DownloadCancelled,
    DownloadError,
    DownloadProgress,
    ModelDownloader,
    ModelEntry,
    ModelRegistry,
    ModelStore,
    assess_compatibility,
    best_matches,
    format_bytes,
    format_eta,
)
from .model_router import RouteRequest, SystemState, route

log = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}


# ------------------------------------------------------------------ list model


class DictListModel(QAbstractListModel):
    """A list of dicts exposed to QML; each key becomes a role."""

    countChanged = Signal()

    def __init__(self, roles: list[str], parent: QObject | None = None):
        super().__init__(parent)
        self._keys = roles
        self._roles = {Qt.UserRole + i + 1: r.encode() for i, r in enumerate(roles)}
        self._role_of = {r: Qt.UserRole + i + 1 for i, r in enumerate(roles)}
        self._items: list[dict[str, Any]] = []

    def roleNames(self) -> dict[int, QByteArray]:  # noqa: N802 (Qt API)
        return {k: QByteArray(v) for k, v in self._roles.items()}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._items)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        key = self._roles.get(role)
        return self._items[index.row()].get(key.decode()) if key else None

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._items)

    def items(self) -> list[dict[str, Any]]:
        return self._items

    def reset(self, items: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._items = list(items)
        self.endResetModel()
        self.countChanged.emit()

    def append(self, item: dict[str, Any]) -> None:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()
        self.countChanged.emit()

    def remove(self, row: int) -> None:
        if 0 <= row < len(self._items):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self._items[row]
            self.endRemoveRows()
            self.countChanged.emit()

    def find(self, key: str, value: Any) -> int:
        for i, item in enumerate(self._items):
            if item.get(key) == value:
                return i
        return -1

    def update(self, row: int, changes: dict[str, Any]) -> None:
        if not 0 <= row < len(self._items):
            return
        item = self._items[row]
        changed = [k for k, v in changes.items() if item.get(k) != v]
        if not changed:
            return
        item.update(changes)
        idx = self.index(row)
        self.dataChanged.emit(idx, idx, [self._role_of[k] for k in changed if k in self._role_of])

    @Slot(int, result="QVariant")
    def get(self, row: int) -> dict[str, Any]:
        return dict(self._items[row]) if 0 <= row < len(self._items) else {}


# --------------------------------------------------------------- icon provider


class IconProvider(QQuickImageProvider):
    """Serves ``image://icon/<name>?color=<hex>`` from ``resources/icons/*.svg``,
    re-coloured so a single stroke icon set works in both themes."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._dir = resource_root() / "resources" / "icons"
        self._cache: dict[str, str] = {}

    def requestImage(self, icon_id: str, size: QSize, requested: QSize) -> QImage:  # noqa: N802
        name, _, query = icon_id.partition("?")
        color = "#ffffff"
        for part in query.split("&"):
            if part.startswith("color="):
                hex_value = part[6:].lstrip("#")
                # QML may hand us #AARRGGBB; SVG wants #RRGGBB (use opacity for alpha).
                color = "#" + (hex_value[2:] if len(hex_value) == 8 else hex_value)
        svg = self._cache.get(name)
        if svg is None:
            path = self._dir / f"{name}.svg"
            svg = path.read_text("utf-8") if path.exists() else ""
            self._cache[name] = svg
        w = requested.width() if requested.width() > 0 else 48
        h = requested.height() if requested.height() > 0 else w
        image = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(Qt.transparent)
        if svg:
            renderer = QSvgRenderer(QByteArray(svg.replace("currentColor", color).encode()))
            painter = QPainter(image)
            renderer.render(painter)
            painter.end()
        if size is not None:
            size.setWidth(w)
            size.setHeight(h)
        return image


class SnapshotProvider(QQuickImageProvider):
    """Serves the most recent window snapshot (used for theme crossfades)."""

    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.image = QImage()

    def requestImage(self, image_id: str, size: QSize, requested: QSize) -> QImage:  # noqa: N802
        if size is not None:
            size.setWidth(self.image.width())
            size.setHeight(self.image.height())
        return self.image


# --------------------------------------------------------------------- helpers


def _date_section(ts: float, now: datetime | None = None) -> str:
    now = now or datetime.now()
    day = datetime.fromtimestamp(ts).date()
    today = now.date()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    if day > today - timedelta(days=7):
        return "Previous 7 Days"
    if day > today - timedelta(days=30):
        return "Previous 30 Days"
    if day.year == today.year:
        return datetime.fromtimestamp(ts).strftime("%B")
    return datetime.fromtimestamp(ts).strftime("%B %Y")


# --------------------------------------------------------------------- backend


class Backend(QObject):
    # Property change notifications
    readyChanged = Signal()
    initStatusChanged = Signal()
    conversationChanged = Signal()
    modelStateChanged = Signal()
    generationChanged = Signal()
    settingsChanged = Signal()
    searchChanged = Signal()
    libraryChanged = Signal()
    recommendationChanged = Signal()

    # User-facing notifications
    toast = Signal(str, str)  # message, kind ("info" | "error")
    scrollToEnd = Signal()

    # Internal cross-thread signals (emitted from worker threads)
    _initDone = Signal(object)
    _downloadProgress = Signal(object)
    _downloadFinished = Signal(str, str)  # model id, error ("" = success, "cancelled")
    _genEvent = Signal(str, object)  # kind, payload

    def __init__(self, paths: AppPaths, parent: QObject | None = None):
        super().__init__(parent)
        self.paths = paths
        self.paths.ensure()
        self.settings = Settings.load(paths.settings_file)
        self.db = ChatDatabase(paths.database)
        self.registry = ModelRegistry([])
        self.store: ModelStore | None = None
        self.hardware: HardwareInfo | None = None
        self.runtime = RuntimeManager()

        self._ready = False
        self._init_status = "Starting…"
        self._runtime_ok = False
        self._runtime_version = ""
        self._installed: dict[str, Any] = {}
        self._downloads: dict[str, ModelDownloader] = {}
        self._download_errors: dict[str, str] = {}
        self._recommended: dict[str, Any] = {}

        self._conversation: Conversation | None = None
        self._draft_mode = "auto"
        self._draft_model = self.settings.default_model_id
        self._search = ""

        self._gen_thread: threading.Thread | None = None
        self._gen_stop = threading.Event()
        self._gen_message_row = -1
        self._gen_conversation = ""
        self._runtime_state = "idle"  # idle | loading | generating
        self._status_text = ""
        self._last_route = ""

        self.conversations = DictListModel(
            ["id", "title", "section", "modelMode", "modelId", "updated"], self
        )
        self.messages = DictListModel(
            ["id", "role", "content", "segments", "modelName", "meta", "streaming", "error",
             "images"],
            self,
        )
        self.library = DictListModel(
            ["id", "name", "family", "parameters", "description", "capabilities", "category",
             "quantization", "sizeText", "ramText", "source", "license", "supported",
             "unsupportedReason", "installed", "downloading", "progress", "progressText",
             "stage", "error", "partial", "loaded", "loading", "repoUrl", "compat", "compatLabel",
             "compatReason", "canDownload", "bestMatch",
             "contextLength"],
            self,
        )

        self._initDone.connect(self._on_init_done)
        self._downloadProgress.connect(self._on_download_progress)
        self._downloadFinished.connect(self._on_download_finished)
        self._genEvent.connect(self._on_gen_event)

    # ================================================================ startup

    @Slot()
    def start(self) -> None:
        """Kick off background initialisation (called once the splash is visible)."""
        self.reload_conversations()
        threading.Thread(target=self._init_worker, name="smolchat-init", daemon=True).start()

    def _set_init_status(self, text: str) -> None:
        self._init_status = text
        self.initStatusChanged.emit()

    def _init_worker(self) -> None:
        result: dict[str, Any] = {}
        try:
            self._initDone.emit({"status": "Loading model registry…"})
            result["registry"] = ModelRegistry.load(self.paths.registry_file)
            self._initDone.emit({"status": "Detecting hardware…"})
            result["hardware"] = HardwareInfo.detect()
            self._initDone.emit({"status": "Scanning downloaded models…"})
            store = ModelStore(self.paths, result["registry"])
            result["store"] = store
            result["installed"] = store.installed()
            self._initDone.emit({"status": "Preparing local runtime…"})
            result["runtime"] = llama_cpp_available()
        except Exception as exc:  # pragma: no cover - reported to the UI
            log.exception("Initialisation failed")
            result["error"] = str(exc)
        result["done"] = True
        self._initDone.emit(result)

    @Slot(object)
    def _on_init_done(self, result: dict[str, Any]) -> None:
        if "status" in result and not result.get("done"):
            self._set_init_status(result["status"])
            return
        if "error" in result:
            self._set_init_status(f"Startup error: {result['error']}")
        if "registry" in result:
            self.registry = result["registry"]
            self.store = result["store"]
            self.hardware = result["hardware"]
            self._installed = result["installed"]
            self._runtime_ok, self._runtime_version = result["runtime"]
            if not self._runtime_ok:
                log.error("llama.cpp runtime unavailable: %s", self._runtime_version)
            self.refresh_library()
        self._ready = True
        self._set_init_status("Ready")
        self.readyChanged.emit()
        self.modelStateChanged.emit()

    @Property(bool, notify=readyChanged)
    def ready(self) -> bool:
        return self._ready

    @Property(str, notify=initStatusChanged)
    def initStatus(self) -> str:  # noqa: N802
        return self._init_status

    @Property(QObject, constant=True)
    def conversationModel(self) -> QObject:  # noqa: N802
        return self.conversations

    @Property(QObject, constant=True)
    def messageModel(self) -> QObject:  # noqa: N802
        return self.messages

    @Property(QObject, constant=True)
    def libraryModel(self) -> QObject:  # noqa: N802
        return self.library

    @Property(str, constant=True)
    def appVersion(self) -> str:  # noqa: N802
        from .config import APP_VERSION

        return APP_VERSION

    def device_profile(self) -> DeviceProfile:
        hw = self.hardware or HardwareInfo.detect()
        try:
            free = shutil.disk_usage(self.paths.models).free
        except OSError:
            free = 0
        ram = hw.total_ram_bytes
        # QA aids: simulate less memory or a fuller disk.
        if os.environ.get("SMOLCHAT_SIMULATE_RAM_GB"):
            ram = int(float(os.environ["SMOLCHAT_SIMULATE_RAM_GB"]) * 1024**3)
        if os.environ.get("SMOLCHAT_SIMULATE_FREE_GB"):
            free = int(float(os.environ["SMOLCHAT_SIMULATE_FREE_GB"]) * 1024**3)
        return DeviceProfile(
            os_name=hw.os_name,
            os_major=hw.os_major,
            chip=hw.chip,
            total_ram_bytes=ram,
            free_disk_bytes=free,
            apple_silicon=hw.apple_silicon,
            gpu_backend="Metal" if hw.metal else hw.gpu_backend,
        )

    @Property(str, notify=libraryChanged)
    def hardwareSummary(self) -> str:  # noqa: N802
        if not self.hardware:
            return ""
        device = self.device_profile()
        accel = f"{device.gpu_backend} acceleration" if device.gpu_acceleration and self.settings.use_gpu else "CPU only"
        parts = [device.os_name, device.chip, f"{device.total_ram_bytes / 1024**3:.0f} GB memory",
                 f"{format_bytes(device.free_disk_bytes)} free", accel]
        return " · ".join(p for p in parts if p)

    @Property("QVariantMap", notify=recommendationChanged)
    def recommendedModel(self) -> dict[str, Any]:  # noqa: N802
        """The best first chat model for this device (for the welcome screen)."""
        return self._recommended

    @Property(bool, notify=modelStateChanged)
    def runtimeAvailable(self) -> bool:  # noqa: N802
        return self._runtime_ok

    @Property(str, constant=True)
    def modelsFolder(self) -> str:  # noqa: N802
        return str(self.paths.models)

    # ========================================================== conversations

    def reload_conversations(self) -> None:
        convs = self.db.list_conversations(self._search)
        now = datetime.now()
        self.conversations.reset([
            {
                "id": c.id,
                "title": c.title,
                "section": _date_section(c.updated_at, now),
                "modelMode": c.model_mode,
                "modelId": c.model_id,
                "updated": c.updated_at,
            }
            for c in convs
        ])

    @Property(str, notify=searchChanged)
    def searchQuery(self) -> str:  # noqa: N802
        return self._search

    @Slot(str)
    def setSearch(self, query: str) -> None:  # noqa: N802
        if query != self._search:
            self._search = query
            self.searchChanged.emit()
            self.reload_conversations()

    @Property(str, notify=conversationChanged)
    def currentConversationId(self) -> str:  # noqa: N802
        return self._conversation.id if self._conversation else ""

    @Property(str, notify=conversationChanged)
    def currentTitle(self) -> str:  # noqa: N802
        return self._conversation.title if self._conversation else "New chat"

    @Slot()
    def newChat(self) -> None:  # noqa: N802
        self._conversation = None
        self._draft_mode = "manual" if self.settings.default_model_id else "auto"
        self._draft_model = self.settings.default_model_id
        if self._draft_model and self._draft_model not in self._installed:
            self._draft_mode, self._draft_model = "auto", ""
        self.messages.reset([])
        self.conversationChanged.emit()
        self.modelStateChanged.emit()

    @Slot(str)
    def openConversation(self, conversation_id: str) -> None:  # noqa: N802
        conv = self.db.get_conversation(conversation_id)
        if conv is None:
            self.toast.emit("That conversation no longer exists.", "error")
            self.reload_conversations()
            return
        self._conversation = conv
        self._load_messages()
        self.conversationChanged.emit()
        self.modelStateChanged.emit()
        self.scrollToEnd.emit()

    def _load_messages(self) -> None:
        assert self._conversation is not None
        palette = self._palette()
        items = []
        for m in self.db.messages(self._conversation.id):
            if m.role == "system":
                continue
            items.append(self._message_item(
                m.id, m.role, m.content, m.model_id, m.metadata, palette
            ))
        if self._gen_conversation == self._conversation.id and self.is_generating:
            # Reattach to an in-flight generation for this conversation.
            for row, item in enumerate(items):
                if item["streaming"]:
                    self._gen_message_row = row
        self.messages.reset(items)

    def _message_item(
        self,
        msg_id: int,
        role: str,
        content: str,
        model_id: str,
        meta: dict[str, Any],
        palette: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        entry = self.registry.get(model_id) if model_id else None
        details = []
        if meta.get("tokens_per_second"):
            details.append(f"{meta['tokens_per_second']:.0f} tok/s")
        if meta.get("routed"):
            details.append("Auto")
        if meta.get("stopped"):
            details.append("Stopped")
        return {
            "id": msg_id,
            "role": role,
            "content": content,
            "segments": segment_message(content, palette or self._palette()) if role == "assistant" else [],
            "modelName": entry.name if entry else model_id,
            "meta": " · ".join(details),
            "streaming": bool(meta.get("streaming")),
            "error": bool(meta.get("error")),
            "images": [QUrl.fromLocalFile(p).toString() for p in meta.get("images", [])],
        }

    @Slot(str, str)
    def renameConversation(self, conversation_id: str, title: str) -> None:  # noqa: N802
        if not title.strip():
            return
        self.db.rename_conversation(conversation_id, title)
        if self._conversation and self._conversation.id == conversation_id:
            self._conversation = self.db.get_conversation(conversation_id)
            self.conversationChanged.emit()
        self.reload_conversations()

    @Slot(str)
    def deleteConversation(self, conversation_id: str) -> None:  # noqa: N802
        if self._gen_conversation == conversation_id and self.is_generating:
            self._gen_stop.set()
        for m in self.db.messages(conversation_id):
            for p in m.metadata.get("images", []):
                if Path(p).is_relative_to(self.paths.attachments):
                    Path(p).unlink(missing_ok=True)
        self.db.delete_conversation(conversation_id)
        if self._conversation and self._conversation.id == conversation_id:
            self.newChat()
        self.reload_conversations()

    # ============================================================ model state

    def _installed_entries(self) -> list[ModelEntry]:
        return [m.entry for m in self._installed.values()]

    @Property(bool, notify=modelStateChanged)
    def hasInstalledModels(self) -> bool:  # noqa: N802
        return bool(self._installed)

    @Property(str, notify=modelStateChanged)
    def modelMode(self) -> str:  # noqa: N802
        return self._conversation.model_mode if self._conversation else self._draft_mode

    @Property(str, notify=modelStateChanged)
    def selectedModelId(self) -> str:  # noqa: N802
        return self._conversation.model_id if self._conversation else self._draft_model

    @Property(str, notify=modelStateChanged)
    def selectedModelLabel(self) -> str:  # noqa: N802
        if self.modelMode == "auto":
            return "Auto"
        entry = self.registry.get(self.selectedModelId)
        return entry.name if entry else "Choose a model"

    @Property(bool, notify=modelStateChanged)
    def selectedModelMissing(self) -> bool:  # noqa: N802
        return self.modelMode == "manual" and self.selectedModelId not in self._installed

    @Property(str, notify=modelStateChanged)
    def loadedModelId(self) -> str:  # noqa: N802
        return self.runtime.loaded_model_id or ""

    @Property(str, notify=modelStateChanged)
    def loadedModelName(self) -> str:  # noqa: N802
        entry = self.registry.get(self.runtime.loaded_model_id or "")
        return entry.name if entry else ""

    @Property(bool, notify=modelStateChanged)
    def visionAvailable(self) -> bool:  # noqa: N802
        """True if a vision model is installed that the runtime can actually run."""
        from .inference import vision_supported

        return vision_supported() and any(
            "vision" in e.capabilities for e in self._installed_entries()
        )

    @Property(str, notify=modelStateChanged)
    def lastRouteReason(self) -> str:  # noqa: N802
        return self._last_route

    @Property("QVariantList", notify=modelStateChanged)
    def installedModels(self) -> list[dict[str, Any]]:  # noqa: N802
        loaded = self.runtime.loaded_model_id
        out = []
        for e in sorted(self._installed_entries(), key=lambda e: (e.family, e.params_b)):
            out.append({
                "id": e.id,
                "name": e.name,
                "family": e.family,
                "detail": f"{e.parameters} · {', '.join(CAPABILITY_LABELS[c] for c in e.capabilities if c != 'chat') or 'Text'}",
                "loaded": e.id == loaded,
            })
        return out

    @Slot(str)
    def selectModel(self, model_id: str) -> None:  # noqa: N802
        """Pin ``model_id`` to the current conversation (manual mode)."""
        if model_id not in self._installed:
            self.toast.emit("That model is not downloaded.", "error")
            return
        if self._conversation:
            self.db.set_conversation_model(self._conversation.id, model_id, "manual")
            self._conversation = self.db.get_conversation(self._conversation.id)
        else:
            self._draft_mode, self._draft_model = "manual", model_id
        self.modelStateChanged.emit()
        self.reload_conversations()
        self._preload(model_id)

    @Slot()
    def setAutoMode(self) -> None:  # noqa: N802
        if self._conversation:
            self.db.set_conversation_model(self._conversation.id, "", "auto")
            self._conversation = self.db.get_conversation(self._conversation.id)
        else:
            self._draft_mode, self._draft_model = "auto", ""
        self.modelStateChanged.emit()
        self.reload_conversations()

    def _preload(self, model_id: str) -> None:
        """Load a manually chosen model in the background so the first reply is fast."""
        if self.is_generating or self.runtime.loaded_model_id == model_id or not self._runtime_ok:
            return

        def work() -> None:
            try:
                self._load_model(model_id)
            except InferenceError as exc:
                self._genEvent.emit("toast_error", str(exc))
            finally:
                self._genEvent.emit("state", "idle")

        threading.Thread(target=work, name="smolchat-preload", daemon=True).start()

    @Slot()
    def unloadModel(self) -> None:  # noqa: N802
        if self.is_generating:
            self.toast.emit("Stop the current response before unloading the model.", "error")
            return

        def work() -> None:
            self.runtime.unload()
            self._genEvent.emit("state", "idle")

        threading.Thread(target=work, name="smolchat-unload", daemon=True).start()

    def _load_model(self, model_id: str) -> None:
        """Blocking; call from a worker thread."""
        installed = self._installed.get(model_id)
        if installed is None:
            raise InferenceError("The selected model is not downloaded.")
        entry = installed.entry
        if self.runtime.loaded_model_id == model_id:
            return
        if entry.backend == "llama_cpp_vision":
            from .inference import vision_supported

            mmproj = installed.path_for("mmproj") if vision_supported() else None
        else:
            mmproj = None
        ctx = min(self.settings.context_length, entry.context_length or self.settings.context_length)
        spec = LoadSpec(
            model_id=entry.id,
            model_path=installed.path_for("model"),
            mmproj_path=mmproj,
            context_length=ctx,
            use_gpu=self.settings.use_gpu and bool(
                self.hardware and (self.hardware.metal or self.hardware.gpu_backend)
            ),
            chat_style=entry.family,
        )
        self._genEvent.emit("state", ("loading", entry.name))
        self.runtime.ensure_loaded(spec, entry.backend or "", entry.estimated_ram_bytes(ctx))

    # ============================================================ generation

    @property
    def is_generating(self) -> bool:
        return self._gen_thread is not None and self._gen_thread.is_alive()

    @Property(bool, notify=generationChanged)
    def isGenerating(self) -> bool:  # noqa: N802
        return self.is_generating

    @Property(str, notify=generationChanged)
    def runtimeState(self) -> str:  # noqa: N802
        return self._runtime_state

    @Property(str, notify=generationChanged)
    def statusText(self) -> str:  # noqa: N802
        return self._status_text

    @Property(str, notify=generationChanged)
    def generatingConversationId(self) -> str:  # noqa: N802
        return self._gen_conversation if self.is_generating else ""

    @Slot(str, "QVariantList", result=bool)
    def sendMessage(self, text: str, images: list) -> bool:  # noqa: N802
        text = text.strip()
        image_paths = [QUrl(u).toLocalFile() if str(u).startswith("file:") else str(u) for u in images or []]
        if not text and not image_paths:
            return False
        if not self._ready:
            return False
        if self.is_generating:
            self.toast.emit("Please wait for the current response to finish.", "info")
            return False
        if not self._runtime_ok:
            self.toast.emit("The local llama.cpp runtime failed to load. See the log for details.", "error")
            return False

        stored_images = self._store_attachments(image_paths)
        if self._conversation is None:
            self._conversation = self.db.create_conversation(
                suggest_title(text or "Image"), self._draft_model, self._draft_mode
            )
            self.conversationChanged.emit()
        conv = self._conversation
        meta = {"images": stored_images} if stored_images else {}
        msg = self.db.add_message(conv.id, "user", text, metadata=meta)
        self.messages.append(self._message_item(msg.id, "user", text, "", meta))
        self.reload_conversations()
        self._start_generation(conv.id)
        return True

    def _store_attachments(self, paths: list[str]) -> list[str]:
        stored = []
        for p in paths:
            src = Path(p)
            if src.suffix.lower() not in IMAGE_SUFFIXES or not src.is_file():
                continue
            suffix = src.suffix.lower()
            if suffix in (".png", ".jpg", ".jpeg"):
                dest = self.paths.attachments / f"{uuid.uuid4().hex}{suffix}"
                shutil.copy2(src, dest)
            else:
                # The runtime's image decoder reads PNG/JPEG reliably; convert the rest.
                dest = self.paths.attachments / f"{uuid.uuid4().hex}.png"
                image = QImage(str(src))
                if image.isNull() or not image.save(str(dest), "PNG"):
                    self.toast.emit(f"Could not read image {src.name}.", "error")
                    continue
            stored.append(str(dest))
        return stored

    @Slot()
    def regenerate(self) -> None:
        if self.is_generating or self._conversation is None:
            return
        msgs = self.db.messages(self._conversation.id)
        while msgs and msgs[-1].role == "assistant":
            self.db.delete_message(msgs[-1].id)
            msgs.pop()
            self.messages.remove(self.messages.count - 1)
        if not msgs or msgs[-1].role != "user":
            return
        self._start_generation(self._conversation.id)

    @Slot()
    def stopGeneration(self) -> None:  # noqa: N802
        self._gen_stop.set()

    def _start_generation(self, conversation_id: str) -> None:
        conv = self.db.get_conversation(conversation_id)
        assert conv is not None
        history = self.db.messages(conversation_id)
        last_user = next((m for m in reversed(history) if m.role == "user"), None)
        has_images = bool(last_user and last_user.metadata.get("images"))

        # Decide which model answers.
        routed = conv.model_mode == "auto"
        if routed:
            decision = route(
                RouteRequest(
                    text=last_user.content if last_user else "",
                    has_images=has_images,
                    history_turns=sum(1 for m in history if m.role == "user") - 1,
                ),
                self._runnable_entries(),
                self._system_state(),
                self.settings.routing_preference,
                self.settings.context_length,
            )
            self._last_route = decision.reason
            model_id = decision.model_id
            if model_id is None:
                self._append_error(conversation_id, decision.reason)
                return
        else:
            model_id = conv.model_id
            if model_id not in self._installed:
                self._append_error(
                    conversation_id,
                    "The model selected for this chat is not downloaded anymore. "
                    "Pick another model or switch to Auto.",
                )
                return
            entry = self._installed[model_id].entry
            if has_images and "vision" not in entry.capabilities:
                self._append_error(
                    conversation_id,
                    f"{entry.name} cannot see images. Choose a SmolVLM model or switch to Auto.",
                )
                return
            self._last_route = ""

        entry = self.registry.get(model_id)
        assert entry is not None
        placeholder_meta = {"streaming": True}
        msg = self.db.add_message(conversation_id, "assistant", "", model_id, placeholder_meta)
        if self._conversation and self._conversation.id == conversation_id:
            self.messages.append(self._message_item(msg.id, "assistant", "", model_id, placeholder_meta))
            self._gen_message_row = self.messages.count - 1
            self.scrollToEnd.emit()

        chat = self._build_prompt(history, entry)
        params = GenerationParams(
            temperature=self.settings.temperature, max_tokens=self.settings.max_tokens
        )
        self._gen_stop.clear()
        self._gen_conversation = conversation_id
        self._gen_thread = threading.Thread(
            target=self._generation_worker,
            args=(conversation_id, msg.id, model_id, chat, params, routed),
            name="smolchat-generate",
            daemon=True,
        )
        self._gen_thread.start()
        self._set_runtime_state("generating", f"Starting {entry.name}…")
        self.modelStateChanged.emit()

    def _runnable_entries(self) -> list[ModelEntry]:
        from .inference import vision_supported

        entries = self._installed_entries()
        if not vision_supported():
            # Keep VLMs available for text chat, but not as image models.
            entries = [
                e if "vision" not in e.capabilities else ModelEntry(**{
                    **e.__dict__, "capabilities": tuple(c for c in e.capabilities if c != "vision")
                })
                for e in entries
            ]
        return entries

    def _system_state(self) -> SystemState:
        loaded = self.runtime.loaded_model_id
        loaded_entry = self.registry.get(loaded) if loaded else None
        return SystemState(
            available_bytes=available_memory_bytes(),
            total_bytes=self.hardware.total_ram_bytes if self.hardware else 8 * 1024**3,
            loaded_model_id=loaded,
            loaded_model_bytes=loaded_entry.estimated_ram_bytes(self.settings.context_length)
            if loaded_entry else 0,
        )

    def _build_prompt(self, history: list, entry: ModelEntry) -> list[ChatMessage]:
        system = self.settings.system_prompt.strip()
        if entry.family == "SmolLM3":
            # SmolLM3's chat template switches reasoning on/off with these flags.
            system = f"{system}\n{'/think' if self.settings.enable_thinking else '/no_think'}".strip()
        chat: list[ChatMessage] = []
        if system and "vision" not in entry.capabilities:
            chat.append(ChatMessage("system", system))
        for m in history:
            if m.role == "assistant" and (m.metadata.get("error") or not m.content.strip()):
                continue
            if m.role not in ("user", "assistant"):
                continue
            content = strip_reasoning(m.content) if m.role == "assistant" else m.content
            images = [p for p in m.metadata.get("images", []) if Path(p).is_file()]
            chat.append(ChatMessage(m.role, content, images))
        # Only the latest user turn carries images: older images would exhaust
        # the small context windows of SmolVLM models.
        for m in chat[:-1]:
            m.images = []
        return chat

    def _generation_worker(
        self,
        conversation_id: str,
        message_id: int,
        model_id: str,
        chat: list[ChatMessage],
        params: GenerationParams,
        routed: bool,
    ) -> None:
        buffer: list[str] = []
        text_parts: list[str] = []
        last_flush = time.monotonic()

        def on_token(piece: str) -> None:
            nonlocal last_flush
            buffer.append(piece)
            text_parts.append(piece)
            now = time.monotonic()
            if now - last_flush >= 0.04:
                last_flush = now
                self._genEvent.emit("tokens", (conversation_id, message_id, "".join(buffer)))
                buffer.clear()

        meta: dict[str, Any] = {"routed": routed}
        try:
            self._load_model(model_id)
            entry = self.registry.get(model_id)
            self._genEvent.emit("state", ("generating", f"{entry.name if entry else model_id} is responding…"))
            result = self.runtime.generate(chat, params, on_token, self._gen_stop.is_set)
            if buffer:
                self._genEvent.emit("tokens", (conversation_id, message_id, "".join(buffer)))
            meta.update(
                tokens=result.tokens,
                seconds=round(result.seconds, 2),
                tokens_per_second=round(result.tokens_per_second, 1),
                stopped=result.stopped,
                finish_reason=result.finish_reason,
            )
            text = result.text
            if not text.strip() and not result.stopped:
                text = "The model returned an empty response."
                meta["error"] = True
        except InferenceError as exc:
            log.warning("Generation failed: %s", exc)
            text = "".join(text_parts) or str(exc)
            meta["error"] = not text_parts
        except Exception as exc:  # pragma: no cover - unexpected runtime failure
            log.exception("Unexpected generation failure")
            text = f"Unexpected error: {exc}"
            meta["error"] = True
        self.db.update_message(message_id, text, model_id, meta)
        self._genEvent.emit("done", (conversation_id, message_id, text, model_id, meta))

    def _append_error(self, conversation_id: str, text: str) -> None:
        meta = {"error": True}
        msg = self.db.add_message(conversation_id, "assistant", text, "", meta)
        if self._conversation and self._conversation.id == conversation_id:
            self.messages.append(self._message_item(msg.id, "assistant", text, "", meta))
            self.scrollToEnd.emit()
        self.modelStateChanged.emit()

    def _set_runtime_state(self, state: str, text: str = "") -> None:
        self._runtime_state = state
        self._status_text = text
        self.generationChanged.emit()

    @Slot(str, object)
    def _on_gen_event(self, kind: str, payload: Any) -> None:
        if kind == "tokens":
            conv_id, msg_id, chunk = payload
            if self._conversation and self._conversation.id == conv_id:
                row = self.messages.find("id", msg_id)
                if row >= 0:
                    content = self.messages.items()[row]["content"] + chunk
                    self.messages.update(row, {
                        "content": content,
                        "segments": segment_message(content, self._palette()),
                    })
                    self.scrollToEnd.emit()
        elif kind == "state":
            if payload == "idle":
                if not self.is_generating:
                    self._set_runtime_state("idle")
            else:
                state, label = payload
                text = f"Loading {label}…" if state == "loading" else label
                self._set_runtime_state(state, text)
            self.modelStateChanged.emit()
            self.refresh_library()
        elif kind == "toast_error":
            self.toast.emit(str(payload), "error")
        elif kind == "done":
            conv_id, msg_id, text, model_id, meta = payload
            if self._gen_thread is not None:
                self._gen_thread.join(timeout=1)
            self._gen_thread = None
            self._gen_conversation = ""
            if self._conversation and self._conversation.id == conv_id:
                row = self.messages.find("id", msg_id)
                if row >= 0:
                    item = self._message_item(msg_id, "assistant", text, model_id, meta)
                    self.messages.update(row, item)
            self._set_runtime_state("idle")
            self.modelStateChanged.emit()
            self.reload_conversations()
            self.refresh_library()

    # ============================================================== library

    def refresh_library(self) -> None:
        if self.store is None:
            return
        device = self.device_profile()
        ctx = self.settings.context_length
        best = best_matches(self.registry.all(), device, ctx)
        loaded = self.runtime.loaded_model_id
        loading = self.runtime.loading_model_id
        from .inference import vision_supported

        vision_ok = vision_supported()
        rows = []
        order = {"chat": 0, "vision": 1, "document": 2, "retrieval": 3}
        for e in sorted(
            self.registry.all(), key=lambda e: (order[e.primary_category], e.family, e.params_b)
        ):
            existing = self.library.find("id", e.id)
            current = self.library.items()[existing] if existing >= 0 else {}
            downloading = e.id in self._downloads
            caps = [CAPABILITY_LABELS[c] for c in e.capabilities]
            supported = e.supported
            reason = e.unsupported_reason
            if supported and "vision" in e.capabilities and not vision_ok:
                reason = (
                    "Image input needs a llama.cpp build with multimodal support; this model "
                    "will answer text-only until it is available."
                )
            ram_need = e.estimated_ram_bytes(ctx)
            partial = self.store.partial_bytes(e.id)
            compat = assess_compatibility(e, device, ctx, partial)
            if downloading:
                progress = current.get("progress", 0.0)
                progress_text = current.get("progressText", "")
                stage = current.get("stage", "")
            else:
                progress = partial / e.download_size if e.download_size else 0.0
                progress_text = self._progress_text(partial, e.download_size) if partial else ""
                stage = ""
            rows.append({
                "id": e.id,
                "name": e.name,
                "family": e.family,
                "parameters": e.parameters,
                "description": e.description,
                "capabilities": caps,
                "category": e.primary_category,
                "quantization": e.quantization,
                "sizeText": format_bytes(e.download_size) if e.files else "—",
                "ramText": f"~{format_bytes(ram_need)} of memory while in use · "
                           f"{e.recommended_ram_gb} GB+ recommended",
                "source": e.source,
                "license": e.license,
                "supported": supported,
                "unsupportedReason": reason,
                "installed": e.id in self._installed,
                "downloading": downloading,
                "progress": progress,
                "progressText": progress_text,
                "stage": stage,
                "error": self._download_errors.get(e.id, ""),
                "partial": partial > 0 and not downloading,
                "loaded": e.id == loaded,
                "loading": e.id == loading,
                "repoUrl": e.page_url,
                "compat": compat.level,
                "compatLabel": compat.label,
                "compatReason": compat.reason,
                "canDownload": compat.can_download,
                "bestMatch": e.id in best.values(),
                "contextLength": e.context_length,
            })
        if [r["id"] for r in rows] == [r["id"] for r in self.library.items()]:
            for i, r in enumerate(rows):
                self.library.update(i, r)
        else:
            self.library.reset(rows)
        self._update_recommendation(best.get("chat", ""))
        self.libraryChanged.emit()

    def _update_recommendation(self, model_id: str) -> None:
        row = self.library.find("id", model_id)
        item = self.library.items()[row] if row >= 0 else {}
        rec = {
            "id": model_id,
            "name": item.get("name", ""),
            "description": item.get("description", ""),
            "sizeText": item.get("sizeText", ""),
            "downloading": item.get("downloading", False),
            "progress": item.get("progress", 0.0),
            "progressText": item.get("progressText", ""),
            "installed": item.get("installed", False),
        }
        if rec != self._recommended:
            self._recommended = rec
            self.recommendationChanged.emit()

    @staticmethod
    def _progress_text(done: int, total: int, speed: float = 0.0) -> str:
        pct = f"{done / total * 100:.0f}%" if total else ""
        text = f"{format_bytes(done, precise=True)} of {format_bytes(total)} · {pct}"
        if speed > 0:
            text += f" · {format_bytes(speed, precise=True)}/s"
            eta = format_eta((total - done) / speed)
            if eta:
                text += f" · {eta}"
        return text

    @Property(int, notify=libraryChanged)
    def activeDownloads(self) -> int:  # noqa: N802
        return len(self._downloads)

    @Slot(str)
    def downloadModel(self, model_id: str) -> None:  # noqa: N802
        entry = self.registry.get(model_id)
        if entry is None or self.store is None or model_id in self._downloads:
            return
        if not entry.supported:
            self.toast.emit(entry.unsupported_reason or "This model is not supported yet.", "error")
            return
        compat = assess_compatibility(
            entry, self.device_profile(), self.settings.context_length,
            self.store.partial_bytes(model_id),
        )
        if not compat.can_download:
            # Never download a model that would overwhelm the device or fill the disk.
            self.toast.emit(f"{entry.name} was not downloaded: {compat.reason}", "error")
            self.refresh_library()
            return
        downloader = ModelDownloader(self.store, entry, on_progress=self._downloadProgress.emit)
        self._downloads[model_id] = downloader
        self._download_errors.pop(model_id, None)

        def work() -> None:
            try:
                downloader.download()
                self._downloadFinished.emit(model_id, "")
            except DownloadCancelled:
                self._downloadFinished.emit(model_id, "cancelled")
            except DownloadError as exc:
                self._downloadFinished.emit(model_id, str(exc))
            except Exception as exc:  # pragma: no cover
                log.exception("Download failed")
                self._downloadFinished.emit(model_id, f"Download failed: {exc}")

        threading.Thread(target=work, name=f"download-{model_id}", daemon=True).start()
        self.refresh_library()

    @Slot(object)
    def _on_download_progress(self, p: DownloadProgress) -> None:
        row = self.library.find("id", p.model_id)
        if row < 0 or p.model_id not in self._downloads:
            return
        if p.stage == "verifying":
            text = "Verifying checksum…"
        elif p.stage == "preparing":
            text = f"Checking the partial download… {format_bytes(p.downloaded, precise=True)}"
        else:
            text = self._progress_text(p.downloaded, p.total, p.speed_bps)
        self.library.update(row, {"progress": p.fraction, "progressText": text, "stage": p.stage})
        if p.model_id == self._recommended.get("id"):
            self._update_recommendation(p.model_id)

    @Slot(str, str)
    def _on_download_finished(self, model_id: str, error: str) -> None:
        self._downloads.pop(model_id, None)
        entry = self.registry.get(model_id)
        name = entry.name if entry else model_id
        if not error:
            assert self.store is not None
            self._installed = self.store.installed()
            self.toast.emit(f"{name} is ready to use.", "info")
        elif error != "cancelled":
            self._download_errors[model_id] = error
            self.toast.emit(f"{name}: {error}", "error")
        row = self.library.find("id", model_id)
        if row >= 0:
            self.library.update(row, {"progressText": "", "stage": ""})
        self.refresh_library()
        self.modelStateChanged.emit()

    @Slot(str)
    def cancelDownload(self, model_id: str) -> None:  # noqa: N802
        downloader = self._downloads.get(model_id)
        if downloader:
            downloader.cancel()

    @Slot(str)
    def discardPartial(self, model_id: str) -> None:  # noqa: N802
        if self.store and model_id not in self._downloads:
            self.store.discard_partial(model_id)
            row = self.library.find("id", model_id)
            if row >= 0:
                self.library.update(row, {"progress": 0.0, "progressText": ""})
            self.refresh_library()

    @Slot(str, result=str)
    def deleteBlocker(self, model_id: str) -> str:  # noqa: N802
        """Reason a model cannot be deleted right now, or "" if it can."""
        if self.runtime.loading_model_id == model_id:
            return "This model is loading. Wait for it to finish, then unload it."
        if self.runtime.loaded_model_id == model_id:
            if self.is_generating:
                return "This model is generating a response. Stop it and unload the model first."
            return "This model is currently loaded. Unload it or switch to another model first."
        return ""

    @Slot(str, result=bool)
    def deleteModel(self, model_id: str) -> bool:  # noqa: N802
        blocker = self.deleteBlocker(model_id)
        if blocker:
            self.toast.emit(blocker, "error")
            return False
        if self.store is None:
            return False
        self.store.delete(model_id)
        self._installed = self.store.installed()
        if self._draft_model == model_id:
            self._draft_mode, self._draft_model = "auto", ""
        if self.settings.default_model_id == model_id:
            self.settings.default_model_id = ""
            self.settings.save(self.paths.settings_file)
        entry = self.registry.get(model_id)
        self.toast.emit(f"{entry.name if entry else model_id} was removed.", "info")
        self.refresh_library()
        self.modelStateChanged.emit()
        return True

    # ============================================================== settings

    def is_dark(self) -> bool:
        if self.settings.theme == "system":
            return QGuiApplication.styleHints().colorScheme() != Qt.ColorScheme.Light
        return self.settings.theme != "light"

    def _palette(self) -> dict[str, str]:
        return DARK_SYNTAX if self.is_dark() else LIGHT_SYNTAX

    def on_system_scheme_changed(self) -> None:
        """System appearance changed; re-highlight code when following it."""
        if self.settings.theme == "system" and self._conversation:
            self._load_messages()

    @Property(str, notify=settingsChanged)
    def theme(self) -> str:
        return self.settings.theme

    @Property(str, notify=settingsChanged)
    def accent(self) -> str:
        return self.settings.accent

    @Property(str, notify=settingsChanged)
    def routingPreference(self) -> str:  # noqa: N802
        return self.settings.routing_preference

    @Property(float, notify=settingsChanged)
    def temperature(self) -> float:
        return self.settings.temperature

    @Property(int, notify=settingsChanged)
    def maxTokens(self) -> int:  # noqa: N802
        return self.settings.max_tokens

    @Property(int, notify=settingsChanged)
    def contextLength(self) -> int:  # noqa: N802
        return self.settings.context_length

    @Property(str, notify=settingsChanged)
    def systemPrompt(self) -> str:  # noqa: N802
        return self.settings.system_prompt

    @Property(bool, notify=settingsChanged)
    def useGpu(self) -> bool:  # noqa: N802
        return self.settings.use_gpu

    @Property(bool, notify=settingsChanged)
    def enableThinking(self) -> bool:  # noqa: N802
        return self.settings.enable_thinking

    @Slot(str, "QVariant")
    def setSetting(self, key: str, value: Any) -> None:  # noqa: N802
        if not hasattr(self.settings, key):
            log.warning("Unknown setting %s", key)
            return
        current = getattr(self.settings, key)
        try:
            value = type(current)(value)
        except (TypeError, ValueError):
            return
        if value == current:
            return
        setattr(self.settings, key, value)
        self.settings.save(self.paths.settings_file)
        self.settingsChanged.emit()
        if key == "theme" and self._conversation:
            self._load_messages()
        if key in ("context_length", "use_gpu") and self.runtime.loaded_model_id and not self.is_generating:
            # Takes effect on next load; unload so the next message reloads with new settings.
            self.unloadModel()
        if key == "context_length":
            self.refresh_library()

    # ============================================================== utilities

    snapshots = SnapshotProvider()
    _snapshot_serial = 0

    @Slot(QObject, result=str)
    def snapshotWindow(self, window: QObject) -> str:  # noqa: N802
        """Capture the whole window (including popups) for a crossfade."""
        grab = getattr(window, "grabWindow", None)
        if grab is None:
            return ""
        self.snapshots.image = grab()
        Backend._snapshot_serial += 1
        return f"image://snapshot/{Backend._snapshot_serial}"

    @Slot(str)
    def copyText(self, text: str) -> None:  # noqa: N802
        QGuiApplication.clipboard().setText(text)

    @Slot()
    def revealModelsFolder(self) -> None:  # noqa: N802
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.models)))

    @Slot(str)
    def openUrl(self, url: str) -> None:  # noqa: N802
        QDesktopServices.openUrl(QUrl(url))

    def shutdown(self) -> None:
        self._gen_stop.set()
        for d in self._downloads.values():
            d.cancel()
        if self._gen_thread is not None:
            self._gen_thread.join(timeout=5)
        self.runtime.unload()
        self.db.close()
