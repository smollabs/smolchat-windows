"""smolchat desktop entry point."""

from __future__ import annotations

import os
import signal
import sys

from PySide6.QtCore import QMetaObject, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuickControls2 import QQuickStyle

from app.backend import Backend, IconProvider
from app.config import APP_NAME, APP_VERSION, ORG_NAME, AppPaths, configure_logging, resource_root


def main() -> int:
    paths = AppPaths.default()
    paths.ensure()
    configure_logging(paths)

    # The Basic style is fully customisable across desktop platforms.
    QQuickStyle.setStyle("Basic")
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    app = QGuiApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(ORG_NAME)
    app.setApplicationVersion(APP_VERSION)
    icon = QIcon()
    for size in (157, 314, 627, 1254):
        icon.addFile(str(resource_root() / "resources" / "assets" / "logo" / f"logo-{size}.png"))
    app.setWindowIcon(icon)

    backend = Backend(paths)

    def apply_color_scheme() -> None:
        # Native chrome (title bar, file dialogs) follows the app theme;
        # "system" follows the operating system's color scheme.
        hints = app.styleHints()
        theme = backend.settings.theme
        if theme == "system":
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(Qt.ColorScheme.Light if theme == "light" else Qt.ColorScheme.Dark)

    apply_color_scheme()
    backend.settingsChanged.connect(apply_color_scheme)
    app.styleHints().colorSchemeChanged.connect(lambda *_: backend.on_system_scheme_changed())

    engine = QQmlApplicationEngine()
    engine.addImageProvider("icon", IconProvider())
    engine.addImageProvider("snapshot", Backend.snapshots)
    engine.rootContext().setContextProperty("backend", backend)
    engine.load(QUrl.fromLocalFile(str(resource_root() / "ui" / "main.qml")))
    if not engine.rootObjects():
        return 1

    app.aboutToQuit.connect(backend.shutdown)
    # Start background initialisation once the event loop (and splash) is running.
    QTimer.singleShot(0, backend.start)

    # Development aid: SMOLCHAT_SCREENSHOT=out.png [SMOLCHAT_SCREENSHOT_DELAY=ms]
    # saves a capture of the main window and quits.
    shot = os.environ.get("SMOLCHAT_SCREENSHOT")
    if shot:
        window = engine.rootObjects()[0]

        panel = os.environ.get("SMOLCHAT_SCREENSHOT_PANEL")  # "library" | "settings"
        if panel:
            QTimer.singleShot(
                1500, lambda: QMetaObject.invokeMethod(window, f"open{panel.capitalize()}Panel")
            )

        prompt = os.environ.get("SMOLCHAT_SCREENSHOT_PROMPT")
        if prompt:
            QTimer.singleShot(1500, lambda: backend.sendMessage(prompt, []))

        def capture() -> None:
            window.grabWindow().save(shot)
            app.quit()

        QTimer.singleShot(int(os.environ.get("SMOLCHAT_SCREENSHOT_DELAY", "2500")), capture)

    # Let Ctrl+C in a terminal quit the app.
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    tick = QTimer()
    tick.start(250)
    tick.timeout.connect(lambda: None)

    code = app.exec()
    del engine  # tear down QML before the backend it binds to
    return code


if __name__ == "__main__":
    sys.exit(main())
