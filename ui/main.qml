import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: window
    width: 1180
    height: 780
    minimumWidth: 720
    minimumHeight: 500
    visible: true
    // The custom title bar is enabled only on platforms that support it.
    title: Qt.platform.os === "osx" ? "" : "smolchat"
    color: Theme.frame
    // Extend under the transparent title bar only where supported.
    flags: Qt.platform.os === "osx"
           ? Qt.Window | Qt.ExpandedClientAreaHint | Qt.NoTitleBarBackgroundHint
           : Qt.Window
    // We lay out around the title bar ourselves (Theme.titleBarHeight), so
    // opt out of the automatic safe-area padding.
    topPadding: 0
    leftPadding: 0
    rightPadding: 0
    bottomPadding: 0

    property bool sidebarPinned: true

    Binding {
        target: Theme
        property: "dark"
        value: backend.theme === "system"
               ? Application.styleHints.colorScheme !== Qt.ColorScheme.Light
               : backend.theme !== "light"
    }
    Binding { target: Theme; property: "accentName"; value: backend.accent }

    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontMd

    function openLibraryPanel() { openLibrary("all") }
    function openSettingsPanel() { settingsDialog.open() }

    function openLibrary(filter) {
        library.filter = filter || "all"
        library.open()
    }

    // Change a setting that affects appearance with a smooth crossfade:
    // snapshot the window, apply the change underneath, fade the snapshot out.
    function setAppearance(key, value) {
        const shot = fader.running ? "" : backend.snapshotWindow(window)
        if (shot) {
            fader.source = shot
            fader.opacity = 1
        }
        backend.setSetting(key, value)
        if (shot) fader.fadeOut()
    }

    // Window dragging / zoom for the transparent title bar region.
    function startDrag() { window.startSystemMove() }
    function toggleZoom() {
        window.visibility === Window.Maximized ? window.showNormal() : window.showMaximized()
    }

    Item {
        id: shell
        anchors.fill: parent
        opacity: 0
        scale: 0.985

        RowLayout {
            anchors.fill: parent
            spacing: 0

            Sidebar {
                id: sidebar
                Layout.fillHeight: true
                Layout.preferredWidth: window.sidebarPinned ? Theme.sidebarWidth : 0
                visible: Layout.preferredWidth > 0
                clip: true
                Behavior on Layout.preferredWidth { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                onOpenLibrary: window.openLibrary("all")
                onOpenSettings: settingsDialog.open()
                onCollapse: window.sidebarPinned = false
                onToggleTheme: window.setAppearance("theme", Theme.dark ? "light" : "dark")
            }

            // The stage floats as a rounded, glossy panel inside the dark frame.
            Item {
                Layout.fillWidth: true
                Layout.fillHeight: true
                ChatView {
                    id: chat
                    anchors.fill: parent
                    anchors.topMargin: 8
                    anchors.bottomMargin: 8
                    anchors.rightMargin: 8
                    anchors.leftMargin: window.sidebarPinned ? 0 : 8
                    Behavior on anchors.leftMargin { NumberAnimation { duration: Theme.normal } }
                    sidebarVisible: window.sidebarPinned
                    onToggleSidebar: window.sidebarPinned = !window.sidebarPinned
                    onOpenLibrary: (filter) => window.openLibrary(filter)
                    onOpenSettings: settingsDialog.open()
                }
            }
        }

        ParallelAnimation {
            id: reveal
            NumberAnimation { target: shell; property: "opacity"; to: 1; duration: Theme.slow; easing.type: Easing.OutCubic }
            NumberAnimation { target: shell; property: "scale"; to: 1; duration: 520; easing.type: Easing.OutCubic }
        }
    }

    ModelLibrary { id: library }
    SettingsDialog {
        id: settingsDialog
        onOpenLibrary: window.openLibrary("all")
        onAppearanceChange: (key, value) => window.setAppearance(key, value)
    }

    // ------------------------------------------------------------- toast
    Rectangle {
        id: toast
        property string kind: "info"
        property bool shown: false
        parent: Overlay.overlay
        z: 900
        x: (window.width - width) / 2
        y: shown ? 18 : -height - 10
        width: Math.min(toastRow.implicitWidth + 32, window.width - 80)
        height: Math.max(42, toastText.implicitHeight + 22)
        radius: 14
        color: Theme.popup
        border.color: kind === "error" ? Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.5) : Theme.border
        opacity: shown ? 1 : 0
        visible: opacity > 0
        Behavior on y { NumberAnimation { duration: Theme.slow; easing.type: Easing.OutBack; easing.overshoot: 0.8 } }
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        RowLayout {
            id: toastRow
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 16
            spacing: 10
            Rectangle {
                width: 22; height: 22; radius: 11
                color: toast.kind === "error" ? Theme.dangerBg : Theme.brandSoft
                C.Icon {
                    anchors.centerIn: parent
                    name: toast.kind === "error" ? "alert" : "check"
                    color: toast.kind === "error" ? Theme.danger : Theme.brand
                    size: 14
                }
            }
            Text {
                id: toastText
                Layout.fillWidth: true
                Layout.maximumWidth: window.width - 160
                color: Theme.text
                font.pixelSize: Theme.fontMd - 1
                wrapMode: Text.Wrap
            }
        }
        Timer { id: toastTimer; interval: 4200; onTriggered: toast.shown = false }
        MouseArea { anchors.fill: parent; onClicked: toast.shown = false }
    }

    Connections {
        target: backend
        function onToast(message, kind) {
            toastText.text = message
            toast.kind = kind
            toast.shown = true
            toastTimer.restart()
        }
    }

    // Theme crossfade snapshot, above everything including popups.
    Image {
        id: fader
        parent: Overlay.overlay
        z: 1000
        width: window.width
        height: window.height
        opacity: 0
        visible: opacity > 0
        cache: false
        readonly property bool running: fadeAnim.running
        function fadeOut() { fadeAnim.restart() }
        NumberAnimation {
            id: fadeAnim
            target: fader
            property: "opacity"
            from: 1
            to: 0
            duration: 420
            easing.type: Easing.InOutQuad
        }
    }

    // Keyboard shortcuts
    Shortcut { sequences: [StandardKey.New]; onActivated: backend.newChat() }
    Shortcut { sequence: "Ctrl+Shift+O"; onActivated: backend.newChat() }
    Shortcut { sequence: "Ctrl+K"; onActivated: { window.sidebarPinned = true; sidebar.focusSearch() } }
    Shortcut { sequence: "Ctrl+Shift+M"; onActivated: window.openLibrary("all") }
    Shortcut { sequences: [StandardKey.Preferences]; onActivated: settingsDialog.open() }
    Shortcut { sequence: "Ctrl+,"; onActivated: settingsDialog.open() }
    Shortcut { sequence: "Ctrl+\\"; onActivated: window.sidebarPinned = !window.sidebarPinned }
    Shortcut { sequence: "Ctrl+Shift+L"; onActivated: window.setAppearance("theme", Theme.dark ? "light" : "dark") }
    Shortcut { sequence: "Ctrl+."; enabled: backend.isGenerating; onActivated: backend.stopGeneration() }

    // Splash overlay – sits above everything until initialisation finishes.
    Loader {
        id: splashLoader
        anchors.fill: parent
        z: 100
        sourceComponent: Splash {
            status: backend.initStatus
            finished: backend.ready
            onFading: reveal.start()
            onDismissed: splashLoader.active = false
        }
    }

    Component.onCompleted: backend.newChat()
}
