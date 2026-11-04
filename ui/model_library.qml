import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// Compact, modal library panel: browse, download, load/unload and delete models.
Popup {
    id: library
    modal: true
    focus: true
    anchors.centerIn: Overlay.overlay
    width: Math.min(parent ? parent.width - 80 : 820, 820)
    height: Math.min(parent ? parent.height - 80 : 680, 680)
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    property string filter: "all"  // all | recommended | downloaded | chat | vision | document | retrieval

    Overlay.modal: Rectangle { color: Theme.overlay }
    background: C.Glass { radius: 20; fill: Theme.popup }
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
        NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
    }
    exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }

    function matches(category, installed, compat) {
        if (filter === "all") return true
        if (filter === "downloaded") return installed
        if (filter === "recommended") return compat === "recommended"
        return category === filter
    }

    contentItem: ColumnLayout {
        spacing: 0

        // ------------------------------------------------------------ header
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24
            Layout.rightMargin: 14
            Layout.topMargin: 18
            spacing: 12
            ColumnLayout {
                spacing: 3
                Layout.fillWidth: true
                Text { text: "Model Library"; color: Theme.text; font.pixelSize: Theme.fontXl - 2; font.weight: Font.DemiBold }
                Text {
                    text: "Download once, run locally, chat offline. Models come from Hugging Face and are stored on this computer."
                    color: Theme.textSecondary
                    font.pixelSize: Theme.fontSm + 1
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }
            }
            C.IconButton { iconName: "close"; tip: "Close"; onClicked: library.close(); Layout.alignment: Qt.AlignTop }
        }

        // Hardware + runtime line
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24
            Layout.rightMargin: 24
            Layout.topMargin: 10
            spacing: 8
            C.Icon { name: "chip"; size: 14; color: Theme.textTertiary }
            Text {
                text: backend.hardwareSummary || "Detecting hardware…"
                color: Theme.textTertiary
                font.pixelSize: Theme.fontXs + 1
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            Text {
                visible: backend.loadedModelName !== ""
                text: "In memory: " + backend.loadedModelName
                color: Theme.textTertiary
                font.pixelSize: Theme.fontXs + 1
            }
            C.ActionButton {
                visible: backend.loadedModelId !== ""
                text: "Unload"
                iconName: "eject"
                compact: true
                kind: "ghost"
                enabled: !backend.isGenerating
                onClicked: backend.unloadModel()
            }
        }

        // Filter tabs
        Row {
            Layout.leftMargin: 20
            Layout.topMargin: 14
            Layout.bottomMargin: 10
            spacing: 4
            Repeater {
                model: [
                    { key: "all", label: "All" },
                    { key: "recommended", label: "Recommended" },
                    { key: "downloaded", label: "Downloaded" },
                    { key: "chat", label: "Text & Chat" },
                    { key: "vision", label: "Vision" },
                    { key: "document", label: "Documents" },
                    { key: "retrieval", label: "Retrieval" }
                ]
                AbstractButton {
                    id: tab
                    required property var modelData
                    readonly property bool active: library.filter === modelData.key
                    implicitHeight: 30
                    implicitWidth: tabText.implicitWidth + 24
                    hoverEnabled: true
                    onClicked: library.filter = modelData.key
                    background: Rectangle {
                        radius: 15
                        color: tab.active ? Theme.hoverStrong : tab.hovered ? Theme.hover : "transparent"
                    }
                    contentItem: Text {
                        id: tabText
                        text: tab.modelData.label
                        color: tab.active ? Theme.text : Theme.textSecondary
                        font.pixelSize: Theme.fontSm + 1
                        font.weight: tab.active ? Font.Medium : Font.Normal
                        horizontalAlignment: Text.AlignHCenter
                        verticalAlignment: Text.AlignVCenter
                    }
                }
            }
        }

        C.Separator { Layout.fillWidth: true }

        // ------------------------------------------------------------- list
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: backend.libraryModel
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 10 }

            delegate: Item {
                id: row
                required property int index
                required property string id
                required property string name
                required property string family
                required property string parameters
                required property string description
                required property var capabilities
                required property string category
                required property string quantization
                required property string sizeText
                required property string ramText
                required property string source
                required property string license
                required property bool supported
                required property string unsupportedReason
                required property bool installed
                required property bool downloading
                required property real progress
                required property string progressText
                required property string stage
                required property string error
                required property bool partial
                required property bool loaded
                required property bool loading
                required property string repoUrl
                required property string compat
                required property string compatLabel
                required property string compatReason
                required property bool canDownload
                required property bool bestMatch

                readonly property bool shown: library.matches(category, installed, compat)
                readonly property color compatColor: compat === "recommended" ? Theme.success
                    : compat === "compatible" ? Theme.warning
                    : compat === "not_recommended" ? Theme.danger : Theme.textTertiary
                width: ListView.view.width
                height: shown ? content.implicitHeight + 32 : 0
                visible: shown

                Rectangle {
                    anchors.fill: parent
                    anchors.leftMargin: 10
                    anchors.rightMargin: 10
                    radius: Theme.radiusMd
                    color: rowHover.hovered ? Theme.hover : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.fast } }
                }
                HoverHandler { id: rowHover }

                RowLayout {
                    id: content
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.leftMargin: 24
                    anchors.rightMargin: 24
                    anchors.topMargin: 16
                    spacing: 16

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5

                        RowLayout {
                            spacing: 8
                            Text {
                                text: row.name
                                color: row.supported ? Theme.text : Theme.textSecondary
                                font.pixelSize: Theme.fontMd + 1
                                font.weight: Font.DemiBold
                            }
                            C.Badge { visible: row.installed; text: row.loaded ? "Loaded" : "Downloaded"; tint: Theme.success }
                            C.Badge { visible: row.loading; text: "Loading…"; tint: Theme.warning }
                            C.Badge { visible: row.bestMatch && !row.installed; text: "★ Best for this device"; tint: Theme.brand }
                            C.Badge { visible: !row.installed; text: row.compatLabel; tint: row.compatColor }
                        }

                        Text {
                            text: row.description
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSm + 1
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        Flow {
                            Layout.fillWidth: true
                            Layout.topMargin: 2
                            spacing: 6
                            Repeater {
                                model: row.capabilities
                                C.Badge {
                                    required property string modelData
                                    text: modelData
                                    tint: modelData === "Vision" ? "#a78bfa" : modelData === "Documents" ? "#f59e0b"
                                        : modelData === "Retrieval" ? "#2dd4bf" : Theme.brand
                                }
                            }
                            C.Badge { text: row.family + " · " + row.parameters }
                        }

                        Text {
                            text: [row.quantization, row.supported ? row.ramText : ""]
                                  .filter(s => s && s !== "—").join("  ·  ")
                            visible: text !== ""
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontXs + 1
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        Text {
                            text: row.source + " · " + row.license + " · <a href=\"" + row.repoUrl + "\">View on Hugging Face</a>"
                            textFormat: Text.StyledText
                            linkColor: Theme.textSecondary
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontXs + 1
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                            onLinkActivated: (link) => backend.openUrl(link)
                            HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.ArrowCursor }
                        }

                        // Why a model runs slowly or is blocked on this device
                        RowLayout {
                            visible: !row.installed && (row.compat === "compatible" || row.compat === "not_recommended")
                            Layout.fillWidth: true
                            spacing: 6
                            C.Icon { name: "alert"; size: 13; color: row.compatColor; Layout.alignment: Qt.AlignTop; Layout.topMargin: 1 }
                            Text {
                                text: row.compatReason + (row.compat === "not_recommended" ? " smolchat won't download it on this device." : "")
                                color: row.compatColor
                                font.pixelSize: Theme.fontXs + 1
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }

                        // Unsupported explanation
                        Text {
                            visible: row.unsupportedReason !== ""
                            text: row.unsupportedReason
                            color: row.supported ? Theme.warning : Theme.textTertiary
                            font.pixelSize: Theme.fontXs + 1
                            font.italic: true
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }

                        // Download progress
                        ColumnLayout {
                            visible: row.downloading || (row.partial && !row.installed)
                            Layout.fillWidth: true
                            Layout.topMargin: 4
                            spacing: 4
                            C.SlimProgress {
                                Layout.fillWidth: true
                                value: row.progress
                                indeterminate: row.downloading && row.progress === 0 && row.progressText === ""
                            }
                            Text {
                                text: row.downloading ? (row.progressText || "Connecting to Hugging Face…")
                                                      : "Paused · " + row.progressText
                                color: row.downloading ? Theme.textSecondary : Theme.textTertiary
                                font.pixelSize: Theme.fontXs + 1
                                font.features: { "tnum": 1 }
                            }
                        }

                        Text {
                            visible: row.error !== "" && !row.downloading
                            text: row.error
                            color: Theme.danger
                            font.pixelSize: Theme.fontXs + 1
                            wrapMode: Text.Wrap
                            Layout.fillWidth: true
                        }
                    }

                    // ------------------------------------------------ actions
                    ColumnLayout {
                        Layout.alignment: Qt.AlignTop
                        Layout.minimumWidth: 128
                        spacing: 6

                        // Download size, always visible next to the action
                        ColumnLayout {
                            visible: row.supported
                            spacing: 0
                            Layout.alignment: Qt.AlignRight
                            Layout.bottomMargin: 2
                            Text {
                                text: row.sizeText
                                color: Theme.text
                                font.pixelSize: Theme.fontMd + 1
                                font.weight: Font.DemiBold
                                Layout.alignment: Qt.AlignRight
                            }
                            Text {
                                text: row.installed ? "on disk" : "download size"
                                color: Theme.textTertiary
                                font.pixelSize: Theme.fontXs
                                Layout.alignment: Qt.AlignRight
                            }
                        }

                        C.ActionButton {
                            visible: row.supported && !row.installed && !row.downloading
                            enabled: row.canDownload
                            kind: row.canDownload ? "primary" : "secondary"
                            compact: true
                            iconName: row.canDownload ? "download" : "alert"
                            text: !row.canDownload ? "Not recommended" : row.partial ? "Resume" : "Download"
                            Layout.alignment: Qt.AlignRight
                            onClicked: backend.downloadModel(row.id)
                            ToolTip.visible: hovered && !row.canDownload
                            ToolTip.text: row.compatReason
                        }
                        C.ActionButton {
                            visible: row.partial && !row.installed && !row.downloading
                            kind: "ghost"
                            compact: true
                            text: "Discard"
                            Layout.alignment: Qt.AlignRight
                            onClicked: backend.discardPartial(row.id)
                        }
                        C.ActionButton {
                            visible: row.downloading
                            kind: "secondary"
                            compact: true
                            text: row.stage === "verifying" ? "Verifying…" : "Cancel"
                            enabled: row.stage !== "verifying"
                            Layout.alignment: Qt.AlignRight
                            onClicked: backend.cancelDownload(row.id)
                        }
                        C.ActionButton {
                            visible: row.installed
                            kind: "secondary"
                            compact: true
                            text: "Use in this chat"
                            Layout.alignment: Qt.AlignRight
                            onClicked: { backend.selectModel(row.id); library.close() }
                        }
                        C.ActionButton {
                            visible: row.installed
                            kind: "ghost"
                            compact: true
                            iconName: "trash"
                            text: "Delete"
                            Layout.alignment: Qt.AlignRight
                            onClicked: {
                                const blocker = backend.deleteBlocker(row.id)
                                deleteDialog.modelId = row.id
                                deleteDialog.blocked = blocker !== ""
                                deleteDialog.title = blocker ? "Model in use" : "Delete " + row.name + "?"
                                deleteDialog.message = blocker
                                    ? blocker
                                    : "This removes " + row.sizeText + " of model files from this computer. You can download it again at any time."
                                deleteDialog.open()
                            }
                        }
                    }
                }

                C.Separator {
                    anchors.bottom: parent.bottom
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.leftMargin: 24
                    anchors.rightMargin: 24
                    visible: row.shown
                }
            }

            Text {
                anchors.centerIn: parent
                visible: library.filter === "downloaded" && !backend.hasInstalledModels
                text: "No models downloaded yet."
                color: Theme.textTertiary
                font.pixelSize: Theme.fontMd - 1
            }
        }

        // ------------------------------------------------------------ footer
        C.Separator { Layout.fillWidth: true }
        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: 24
            Layout.rightMargin: 16
            Layout.topMargin: 10
            Layout.bottomMargin: 12
            Text {
                text: "Downloads are verified with SHA-256 and can be resumed if interrupted."
                color: Theme.textTertiary
                font.pixelSize: Theme.fontXs + 1
                Layout.fillWidth: true
                elide: Text.ElideRight
            }
            C.ActionButton {
                text: "Open model folder"
                iconName: "folder"
                compact: true
                kind: "ghost"
                onClicked: backend.revealModelsFolder()
            }
        }
    }

    C.ConfirmDialog {
        id: deleteDialog
        property string modelId
        property bool blocked: false
        confirmText: blocked ? "" : "Delete"
        cancelText: blocked ? "Close" : "Cancel"
        extraText: blocked && !backend.isGenerating && backend.loadedModelId === modelId ? "Unload model" : ""
        destructive: true
        onConfirmed: backend.deleteModel(modelId)
        onExtra: backend.unloadModel()
    }
}
