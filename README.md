# smolchat

A lightweight desktop AI chat application that runs small language models directly on the user's machine. Part of **smollabs**.

**Download once, run locally, chat offline.** smolchat ships with no model weights. You pick models from the built-in Model Library, they download from Hugging Face into your local app data folder, and from then on every conversation runs on your computer with no network, no cloud APIs and no telemetry.

Built with Python, PySide6 and QML, with local inference through llama.cpp. Windows uses CPU inference by default, with optional GPU offload when supported by the installed llama.cpp build.

## Features

- Splash screen, then a ChatGPT-style window: sidebar with date-grouped history, search, rename and delete; markdown messages; highlighted code blocks with copy; regenerate; streaming with a stop button.
- **Model Library**: 16 Smol models across text, vision, documents and retrieval, with size, quantization, RAM estimate, licence and source. Downloads are resumable, cancellable, SHA-256-verified, and pinned to exact Hugging Face commits.
- **Device-aware recommendations**: smolchat checks your OS, processor, memory and free storage, then rates each model as *Runs well*, *Runs, may be slower* or *Not recommended*. It marks a suitable model and **refuses to download** a model that would cause heavy memory swapping, run too slowly on CPU, or fill the disk.
- **Clear download progress**: each row shows the download size, plus MB downloaded, percentage, speed and time remaining while downloading.
- **Dynamic loading**: a model is usable as soon as its download finishes, and you can switch models mid-session without restarting. Only one model is in memory at a time, and it can be unloaded on demand.
- **Automatic model selection**: each message goes to the best *installed* model, based on task (text or image), request complexity, model size, free memory, which model is already loaded, and your Speed/Balanced/Quality preference. Nothing is ever downloaded automatically.
- **Manual selection** per conversation. It is saved with the chat, and you can switch back to Auto at any time.
- **Vision**: SmolVLM and SmolVLM2 models answer questions about attached images (paperclip button or drag and drop).
- Desktop window with smooth animations. Dark (default), Light or **System** theme, six accent colours, and a crossfade whenever the theme changes. There's a quick sun/moon toggle in the sidebar.
- Local SQLite history and JSON settings.

## Supported models

| Family | Sizes | Runs in smolchat | Source of GGUF |
|---|---|---|---|
| SmolLM (v0.2 instruct) | 135M, 360M, 1.7B | ✅ chat | Official `HuggingFaceTB/smollm-*-instruct-v0.2-Q8_0-GGUF` |
| SmolLM2 Instruct | 135M, 360M, 1.7B | ✅ chat | Official for 360M/1.7B; 135M from `bartowski/SmolLM2-135M-Instruct-GGUF` (no official GGUF exists) |
| SmolLM3 | 3B | ✅ chat (optional thinking mode) | `ggml-org/SmolLM3-3B-GGUF` |
| SmolVLM Instruct | 256M, 500M, 2.2B | ✅ chat + images | `ggml-org/SmolVLM-*-GGUF` (+ `mmproj`) |
| SmolVLM2 Instruct | 256M, 500M, 2.2B | ✅ chat + still images (no video) | `ggml-org/SmolVLM2-*-GGUF` (+ `mmproj`) |
| SmolDocling | 256M | ❌ listed, not runnable | — |
| ColSmol | 256M, 500M | ❌ listed, not runnable | — |

The repositories, revisions, file sizes and SHA-256 hashes in `resources/models.json` were read from the Hugging Face API. Re-check them with `python scripts/verify_registry.py`.

### Known limitations

- **SmolDocling** has no official GGUF with a vision projector, and its DocTags output needs the `docling` toolkit to become Markdown. It appears in the library as *Not yet supported*. Document-style image questions are answered by an installed SmolVLM model instead, and the app says so.
- **ColSmol** is a ColPali-style multi-vector retriever, not a chat model, and llama.cpp cannot run it. It needs a PyTorch/`colpali-engine` runtime, which a future `smol-runtime` engine could provide.
- SmolVLM2's video understanding is not exposed. llama.cpp's multimodal library handles still images only.
- Conversation titles come from the first message rather than a model-written summary. Small models write unreliable titles.

## Getting started

Requirements: Windows 10/11 and Python 3.10–3.12. Windows uses CPU inference by default. If a compatible wheel is unavailable and llama.cpp must build from source, install Visual Studio 2022 Build Tools with **Desktop development with C++**, the Windows SDK, and CMake.

### Windows

In PowerShell, run these commands from the project folder. The CPU wheel index avoids compiling llama.cpp when a matching wheel is available:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install PySide6-Essentials pytest
python -m pip install llama-cpp-python --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
python main.py
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process Bypass` in that window and activate again. If no matching wheel is available, install the Visual Studio C++ workload described above, open **Developer PowerShell for VS 2022**, activate `.venv`, then run `python -m pip install llama-cpp-python` to build from source. This also resolves the `nmake`-not-found error because the developer shell adds the compiler tools to `PATH`.

To build a Windows app folder containing `smolchat.exe`, run `scripts\build_windows.ps1` after installing the dependencies. The output is `dist\smolchat\`.

The default Windows install uses CPU inference. GPU acceleration depends on a `llama-cpp-python` build with GPU offload support for the installed GPU and drivers; smolchat checks whether the installed llama.cpp library advertises GPU offload and adjusts model recommendations.

On first launch no models are installed. Click **Download** on the recommended model, or open the **Model Library** (⌘⇧M), then start chatting.

Keyboard shortcuts use Ctrl-key combinations where available.

### Keyboard shortcuts

| | |
|---|---|
| ⌘N | New chat |
| ⌘K | Search chats |
| ⌘⇧M | Model Library |
| ⌘, | Settings |
| ⌘\ | Toggle sidebar |
| ⇧⌘L | Switch light / dark |
| ⌘. | Stop generating |
| ↩ / ⇧↩ | Send / new line |

## Where data lives

| What | Location |
|---|---|
| Model weights | `%LOCALAPPDATA%\smollabs\smolchat\models\<model-id>\` |
| Install manifests | `metadata/` under the app data folder above |
| Settings | `settings.json` under the app data folder above |
| Conversations | `chats.sqlite3` under the app data folder above |
| Image attachments | `attachments/` under the app data folder above |
| Partial downloads | `%LOCALAPPDATA%\smollabs\smolchat\cache\downloads\` |
| Logs | `%LOCALAPPDATA%\smollabs\smolchat\logs\smolchat.log` |

Set `SMOLCHAT_HOME` to put all data under a single directory. In PowerShell, for example: `$env:SMOLCHAT_HOME = 'C:\path\to\smolchat-data'`.

## Architecture

```
main.py               entry point: Qt app, QML engine, splash → main window
app/config.py         paths, JSON settings, hardware + free-memory detection
app/database.py       SQLite conversations/messages
app/model_manager.py  registry, installed-model store, resumable SHA-256-verified downloader (Qt-free)
app/model_router.py   pure-function automatic model selection
app/inference.py      InferenceEngine interface, llama.cpp engine, RuntimeManager (lifecycle + locking)
app/formatting.py     markdown/code/<think> segmentation + code highlighting
app/backend.py        the only Qt↔Python bridge: list models, slots, signals, worker threads
ui/*.qml              QML interface (main, splash, sidebar, chat, model_library, settings, components, styles/theme)
resources/models.json verified model registry
resources/assets/logo brand artwork: logo tiles (157–1254 px, app icon, sidebar) and the
                      transparent mascot shown in 3D on the splash and home screen
scripts/prepare_brand_assets.py  derives UI-ready assets (e.g. smollabs_mascot_clean.png) from the originals
```

- The UI never blocks. Startup scanning, downloads, model loading and generation run on worker threads and report back through Qt signals, which are delivered on the UI thread. Tokens are batched about every 40 ms.
- `RuntimeManager` keeps one model in memory. Loading another unloads the current one first, and a single lock serialises load, generate and unload, so a model can't be swapped or deleted mid-response.
- Each GGUF's embedded chat template is used as-is, which keeps each model's own tokenizer and prompt format. SmolVLM gets a dedicated libmtmd handler that mirrors its Hugging Face template.
- **Plugging in `smol-runtime`**: implement `app.inference.InferenceEngine` (`load`, `unload`, `generate`, `loaded_model_id`) and call `register_engine("<backend>", Factory)`. Registry entries pick their engine through the `backend` field, so the UI and backend need no changes.

## Tests

```bash
pytest
```

The suites cover the database, registry integrity (pinned revisions, checksums, no false capability claims), downloads (resume, cancel, checksum failure, offline errors) against a fake Hub, store scanning and deletion, routing decisions, and message formatting.

To run the real llama.cpp smoke test, point `SMOLCHAT_TEST_GGUF` at a downloaded GGUF file (for example SmolLM2-135M-Instruct) and run `pytest`.

To try the compatibility rules on other hardware, set `SMOLCHAT_SIMULATE_RAM_GB=4` or `SMOLCHAT_SIMULATE_FREE_GB=1.5`.

Development aids: `SMOLCHAT_SCREENSHOT=out.png` saves a capture of the window and quits. Optional extras:
- `SMOLCHAT_SCREENSHOT_DELAY=<ms>` sets when the capture happens;
- `SMOLCHAT_SCREENSHOT_PANEL=library|settings` opens a panel first;
- `SMOLCHAT_SCREENSHOT_PROMPT="…"` sends a message first.

## Packaging

```bash
scripts\build_windows.ps1      # Windows: dist\smolchat\smolchat.exe
```

The Windows script uses `packaging/smolchat-Windows.spec`. Model weights are not bundled.

## Privacy

smolchat makes network requests only to `huggingface.co` (and its CDN) when you download a model. Chats, prompts and attachments stay on your computer. There is no telemetry.
