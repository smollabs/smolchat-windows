import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import "."

// Main stage: glossy panel with ambient light, the conversation and composer.
Item {
    id: root

    property bool sidebarVisible: true
    signal toggleSidebar()
    signal openLibrary(string filter)
    signal openSettings()

    readonly property bool hasMessages: messages.count > 0
    readonly property bool emptyChat: backend.ready && backend.hasInstalledModels && !hasMessages
    readonly property bool generatingHere: backend.isGenerating
        && backend.generatingConversationId === backend.currentConversationId
    readonly property int stageWidth: Math.min(width - 56, 760)

    C.Backdrop {
        id: backdrop
        anchors.fill: parent
        radius: 18
    }

    // ================================================================= header
    Item {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: 60
        z: 3

        // Empty header space drags the window; double-click zooms.
        MouseArea {
            anchors.fill: parent
            onPressed: window.startDrag()
            onDoubleClicked: window.toggleZoom()
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: root.sidebarVisible ? 18 : Theme.trafficLightsInset
            anchors.rightMargin: 18
            spacing: 8
            Behavior on anchors.leftMargin { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

            C.Pill {
                visible: !root.sidebarVisible
                iconName: "sidebar"
                implicitWidth: 34
                onClicked: root.toggleSidebar()
                ToolTip.visible: hovered; ToolTip.delay: 600; ToolTip.text: "Show sidebar  ⌘\\"
            }
            C.Pill {
                visible: !root.sidebarVisible
                iconName: "plus"
                implicitWidth: 34
                onClicked: backend.newChat()
                ToolTip.visible: hovered; ToolTip.delay: 600; ToolTip.text: "New chat  ⌘N"
            }

            // Model selector
            C.Pill {
                id: modelButton
                iconName: backend.modelMode === "auto" ? "sparkles" : "chip"
                accent: modelPicker.opened
                text: backend.modelMode === "auto" ? "Auto" : backend.selectedModelLabel
                trailingIcon: "chevron-down"
                onClicked: modelPicker.opened ? modelPicker.close() : modelPicker.open()
            }

            Item { Layout.fillWidth: true }

            // On-device status
            C.Pill {
                visible: backend.loadedModelId !== ""
                text: "On-device"
                enabled: false
                opacity: 1
                contentItem: Row {
                    spacing: 7
                    Rectangle {
                        width: 7; height: 7; radius: 3.5
                        color: Theme.success
                        anchors.verticalCenter: parent.verticalCenter
                        SequentialAnimation on opacity {
                            running: backend.runtimeState === "generating"
                            loops: Animation.Infinite
                            onRunningChanged: if (!running) parent.opacity = 1
                            NumberAnimation { to: 0.3; duration: 600; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1; duration: 600; easing.type: Easing.InOutSine }
                        }
                    }
                    Text {
                        text: "On-device"
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontSm + 1
                        font.weight: Font.Medium
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }

        Popup {
            id: modelPicker
            y: header.height - 4
            x: (root.sidebarVisible ? 18 : Theme.trafficLightsInset) + modelButton.x
            width: 330
            padding: 6
            transformOrigin: Item.TopLeft
            background: Item {
                C.Glass { anchors.fill: parent; radius: 16; fill: Theme.popup }
            }
            enter: Transition {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
                NumberAnimation { property: "scale"; from: 0.95; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
            }
            exit: Transition {
                NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast }
            }

            contentItem: ColumnLayout {
                spacing: 0

                PickerRow {
                    title: "Auto"
                    subtitle: "Picks the best downloaded model for each message"
                    iconName: "sparkles"
                    iconTint: Theme.brand
                    selected: backend.modelMode === "auto"
                    onClicked: { backend.setAutoMode(); modelPicker.close() }
                }

                Text {
                    text: "DOWNLOADED MODELS"
                    visible: backend.installedModels.length > 0
                    color: Theme.textTertiary
                    font.pixelSize: Theme.fontXs - 1
                    font.weight: Font.DemiBold
                    font.letterSpacing: 0.8
                    Layout.leftMargin: 12
                    Layout.topMargin: 10
                    Layout.bottomMargin: 4
                }

                Repeater {
                    model: backend.installedModels
                    PickerRow {
                        required property var modelData
                        title: modelData.name
                        subtitle: modelData.detail + (modelData.loaded ? " · Loaded" : "")
                        iconName: "chip"
                        selected: backend.modelMode === "manual" && backend.selectedModelId === modelData.id
                        onClicked: { backend.selectModel(modelData.id); modelPicker.close() }
                    }
                }

                Text {
                    visible: backend.installedModels.length === 0
                    text: "No models downloaded yet."
                    color: Theme.textTertiary
                    font.pixelSize: Theme.fontSm
                    Layout.margins: 12
                }

                C.Separator { Layout.fillWidth: true; Layout.topMargin: 6; Layout.bottomMargin: 6 }

                PickerRow {
                    title: "Model Library…"
                    subtitle: "Download, manage and delete models"
                    iconName: "library"
                    onClicked: { modelPicker.close(); root.openLibrary("all") }
                }
            }
        }
    }

    component PickerRow: AbstractButton {
        id: pr
        property string title
        property string subtitle
        property string iconName
        property color iconTint: Theme.textSecondary
        property bool selected: false
        Layout.fillWidth: true
        implicitHeight: 50
        hoverEnabled: true
        background: Rectangle {
            radius: 11
            color: pr.selected ? Theme.brandSoft : pr.hovered ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
        contentItem: RowLayout {
            spacing: 10
            Rectangle {
                Layout.leftMargin: 8
                width: 30; height: 30; radius: 9
                color: pr.selected ? Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, 0.22) : Theme.hover
                C.Icon { anchors.centerIn: parent; name: pr.iconName; size: 15; color: pr.selected ? Theme.brand : pr.iconTint }
            }
            ColumnLayout {
                spacing: 1
                Layout.fillWidth: true
                Text { text: pr.title; color: Theme.text; font.pixelSize: Theme.fontMd - 1; font.weight: Font.Medium; elide: Text.ElideRight; Layout.fillWidth: true }
                Text { text: pr.subtitle; color: Theme.textTertiary; font.pixelSize: Theme.fontXs; elide: Text.ElideRight; Layout.fillWidth: true }
            }
            C.Icon { visible: pr.selected; name: "check"; size: 16; color: Theme.brand; Layout.rightMargin: 10 }
        }
    }

    // ============================================================ centre stage
    Item {
        id: stage
        anchors.top: header.bottom
        anchors.bottom: composerArea.top
        anchors.left: parent.left
        anchors.right: parent.right
        visible: !root.hasMessages
        opacity: visible ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }

        HoverHandler { id: stageHover }

        readonly property string greeting: {
            const h = new Date().getHours()
            return h < 5 ? "Burning the midnight oil?" : h < 12 ? "Good morning." : h < 18 ? "Good afternoon." : "Good evening."
        }

        // Models installed: orb + headline
        ColumnLayout {
            id: hero
            anchors.centerIn: parent
            width: root.stageWidth
            visible: root.emptyChat
            spacing: 0

            property int entranceKey: 0
            onVisibleChanged: if (visible) entranceKey++
            Connections {
                target: backend
                function onConversationChanged() { if (!root.hasMessages) hero.entranceKey++ }
            }
            onEntranceKeyChanged: heroIn.restart()
            Component.onCompleted: heroIn.restart()
            SequentialAnimation {
                id: heroIn
                PropertyAction { target: hero; property: "opacity"; value: 0 }
                PropertyAction { target: heroShift; property: "y"; value: 14 }
                ParallelAnimation {
                    NumberAnimation { target: hero; property: "opacity"; to: 1; duration: 420; easing.type: Easing.OutCubic }
                    NumberAnimation { target: heroShift; property: "y"; to: 0; duration: 520; easing.type: Easing.OutCubic }
                }
            }
            transform: Translate { id: heroShift }

            C.Mascot3D {
                id: heroTile
                size: 250
                energy: backend.runtimeState !== "idle" ? 1 : 0
                // Lean toward the pointer for a tactile, 3D feel.
                tiltY: stageHover.hovered ? Math.max(-16, Math.min(16, (stageHover.point.position.x - stage.width / 2) / stage.width * 36)) : 0
                tiltX: stageHover.hovered ? Math.max(-12, Math.min(12, -(stageHover.point.position.y - stage.height * 0.4) / stage.height * 28)) : 0
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 30
            }
            Text {
                text: stage.greeting
                color: Theme.textSecondary
                font.pixelSize: Theme.fontLg
                Layout.alignment: Qt.AlignHCenter
            }
            Text {
                text: "What shall we explore today?"
                color: Theme.text
                font.pixelSize: Theme.fontHero
                font.weight: Font.DemiBold
                font.letterSpacing: -0.6
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 4
            }
        }

        // No models yet: onboarding
        ColumnLayout {
            anchors.centerIn: parent
            width: Math.min(root.stageWidth, 560)
            visible: backend.ready && !backend.hasInstalledModels
            spacing: 0

            C.Mascot3D {
                size: 230
                tiltY: stageHover.hovered ? Math.max(-16, Math.min(16, (stageHover.point.position.x - stage.width / 2) / stage.width * 36)) : 0
                tiltX: stageHover.hovered ? Math.max(-12, Math.min(12, -(stageHover.point.position.y - stage.height * 0.35) / stage.height * 28)) : 0
                Layout.alignment: Qt.AlignHCenter
                Layout.bottomMargin: 34
            }
            Text {
                text: "Welcome to smolchat"
                color: Theme.text
                font.pixelSize: Theme.fontHero
                font.weight: Font.DemiBold
                font.letterSpacing: -0.6
                Layout.alignment: Qt.AlignHCenter
            }
            Text {
                text: "Small language models that run entirely on your computer. Download one once, then chat offline — nothing leaves this computer."
                color: Theme.textSecondary
                font.pixelSize: Theme.fontMd + 1
                wrapMode: Text.Wrap
                horizontalAlignment: Text.AlignHCenter
                lineHeight: 1.25
                Layout.fillWidth: true
                Layout.topMargin: 10
            }

            Item {
                Layout.fillWidth: true
                Layout.topMargin: 28
                implicitHeight: quick.implicitHeight + 36
                C.Glass { anchors.fill: parent; radius: 18 }
                ColumnLayout {
                    id: quick
                    anchors.fill: parent
                    anchors.margins: 18
                    spacing: 4
                    Text {
                        text: "★  RECOMMENDED FOR YOUR PC"
                        color: Theme.brand
                        font.pixelSize: Theme.fontXs - 1
                        font.weight: Font.DemiBold
                        font.letterSpacing: 0.8
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 4
                        spacing: 14
                        ColumnLayout {
                            spacing: 3
                            Layout.fillWidth: true
                            Text {
                                text: backend.recommendedModel.name || "No model fits this computer right now"
                                color: Theme.text
                                font.pixelSize: Theme.fontLg
                                font.weight: Font.DemiBold
                            }
                            Text {
                                text: backend.recommendedModel.description || "Free up storage or memory, then check the Model Library for models marked Runs well."
                                color: Theme.textSecondary
                                font.pixelSize: Theme.fontSm
                                wrapMode: Text.Wrap
                                Layout.fillWidth: true
                            }
                        }
                        ColumnLayout {
                            spacing: 6
                            visible: backend.recommendedModel.id !== undefined && backend.recommendedModel.id !== ""
                            Text {
                                text: backend.recommendedModel.sizeText || ""
                                color: Theme.text
                                font.pixelSize: Theme.fontMd
                                font.weight: Font.DemiBold
                                Layout.alignment: Qt.AlignRight
                            }
                            GlowButton {
                                text: backend.recommendedModel.downloading ? "Downloading…" : "Download"
                                iconName: "download"
                                enabled: !backend.recommendedModel.downloading
                                onClicked: backend.downloadModel(backend.recommendedModel.id)
                            }
                        }
                    }
                    ColumnLayout {
                        visible: backend.recommendedModel.downloading === true
                        Layout.fillWidth: true
                        Layout.topMargin: 10
                        spacing: 5
                        C.SlimProgress {
                            Layout.fillWidth: true
                            value: backend.recommendedModel.progress || 0
                            indeterminate: !backend.recommendedModel.progressText
                        }
                        Text {
                            text: backend.recommendedModel.progressText || "Connecting to Hugging Face…"
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontXs + 1
                        }
                    }
                    Text {
                        text: backend.hardwareSummary
                        visible: text !== ""
                        color: Theme.textTertiary
                        font.pixelSize: Theme.fontXs
                        wrapMode: Text.Wrap
                        Layout.fillWidth: true
                        Layout.topMargin: 8
                    }
                }
            }
            C.Pill {
                text: "Browse all models"
                iconName: "library"
                Layout.alignment: Qt.AlignHCenter
                Layout.topMargin: 14
                onClicked: root.openLibrary("all")
            }
        }
    }

    // Accent button with a soft glow (used for primary actions).
    component GlowButton: AbstractButton {
        id: gb
        property string iconName
        implicitHeight: 34
        implicitWidth: gbRow.implicitWidth + 30
        hoverEnabled: true
        scale: down ? 0.96 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        background: Item {
            Rectangle {
                anchors.fill: parent
                anchors.margins: -4
                radius: height / 2
                color: "transparent"
                border.width: 4
                border.color: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, gb.enabled && gb.hovered ? 0.25 : 0.12)
                Behavior on border.color { ColorAnimation { duration: Theme.fast } }
            }
            Rectangle {
                anchors.fill: parent
                radius: height / 2
                opacity: gb.enabled ? 1 : 0.5
                gradient: Gradient {
                    GradientStop { position: 0; color: Qt.lighter(Theme.brand, gb.hovered ? 1.3 : 1.18) }
                    GradientStop { position: 1; color: Qt.darker(Theme.brand, 1.15) }
                }
            }
        }
        contentItem: Item {
            implicitWidth: gbRow.implicitWidth
            Row {
                id: gbRow
                anchors.centerIn: parent
                spacing: 6
                C.Icon { visible: gb.iconName !== ""; name: gb.iconName; size: 15; color: "#ffffff"; anchors.verticalCenter: parent.verticalCenter }
                Text { text: gb.text; color: "#ffffff"; font.pixelSize: Theme.fontSm + 1; font.weight: Font.DemiBold; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }

    // ================================================================ messages
    ListView {
        id: messages
        anchors.top: header.bottom
        anchors.bottom: composerArea.top
        anchors.left: parent.left
        anchors.right: parent.right
        visible: root.hasMessages
        clip: true
        model: backend.messageModel
        spacing: 26
        topMargin: 8
        bottomMargin: 28
        boundsBehavior: Flickable.StopAtBounds
        cacheBuffer: 2000
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded; width: 10 }

        add: Transition {
            ParallelAnimation {
                NumberAnimation { property: "opacity"; from: 0; to: 1; duration: 280; easing.type: Easing.OutCubic }
                NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: 340; easing.type: Easing.OutCubic }
            }
        }
        displaced: Transition { NumberAnimation { properties: "y"; duration: Theme.normal; easing.type: Easing.OutCubic } }

        SequentialAnimation {
            id: switchFade
            PropertyAction { target: messages; property: "opacity"; value: 0 }
            NumberAnimation { target: messages; property: "opacity"; to: 1; duration: 260; easing.type: Easing.OutCubic }
        }

        property bool stickToBottom: true
        onMovementStarted: stickToBottom = false
        onMovementEnded: stickToBottom = atYEnd
        onContentHeightChanged: if (stickToBottom) Qt.callLater(positionViewAtEnd)

        Connections {
            target: backend
            function onScrollToEnd() {
                if (messages.stickToBottom) Qt.callLater(messages.positionViewAtEnd)
            }
            function onConversationChanged() {
                messages.stickToBottom = true
                switchFade.restart()
                Qt.callLater(messages.positionViewAtEnd)
            }
        }

        delegate: Item {
            id: msg
            required property int index
            required property int id
            required property string role
            required property string content
            required property var segments
            required property string modelName
            required property string meta
            required property bool streaming
            required property bool error
            required property var images

            readonly property bool isUser: role === "user"
            readonly property bool isLast: index === messages.count - 1
            width: messages.width
            height: column.implicitHeight

            HoverHandler { id: hover }

            Column {
                id: column
                width: root.stageWidth
                anchors.horizontalCenter: parent.horizontalCenter
                spacing: 6

                // ---------- user message
                Column {
                    visible: msg.isUser
                    width: parent.width
                    spacing: 6
                    Flow {
                        visible: msg.images.length > 0
                        layoutDirection: Qt.RightToLeft
                        width: parent.width
                        spacing: 6
                        Repeater {
                            model: msg.images
                            Rectangle {
                                required property string modelData
                                width: 150; height: 150; radius: 14
                                color: Theme.surface
                                border.color: Theme.glassEdgeTop
                                clip: true
                                Image {
                                    anchors.fill: parent
                                    anchors.margins: 1
                                    source: modelData
                                    fillMode: Image.PreserveAspectCrop
                                    sourceSize: Qt.size(300, 300)
                                    asynchronous: true
                                }
                            }
                        }
                    }
                    Item {
                        visible: msg.content !== ""
                        anchors.right: parent.right
                        width: Math.min(userText.implicitWidth + 38, parent.width * 0.78)
                        height: userText.implicitHeight + 24
                        C.Glass { anchors.fill: parent; radius: 20; fill: Theme.userBubble }
                        TextEdit {
                            id: userText
                            x: 19
                            y: 12
                            width: Math.min(implicitWidth, column.width * 0.78 - 38)
                            text: msg.content
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.Wrap
                            color: Theme.text
                            selectionColor: Theme.brand
                            font.pixelSize: Theme.fontMd + 1
                            textFormat: TextEdit.PlainText
                        }
                    }
                    Row {
                        anchors.right: parent.right
                        opacity: hover.hovered ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                        CopyButton { textToCopy: msg.content }
                    }
                }

                // ---------- assistant message
                Column {
                    visible: !msg.isUser
                    width: parent.width
                    spacing: 10

                    Row {
                        spacing: 10
                        height: 26
                        C.LogoMark {
                            size: 24
                            busy: msg.streaming
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Text {
                            text: msg.modelName || "smolchat"
                            color: Theme.textSecondary
                            font.pixelSize: Theme.fontSm + 1
                            font.weight: Font.DemiBold
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // Waiting indicator
                    Row {
                        visible: msg.streaming && msg.content === ""
                        spacing: 10
                        height: 24
                        leftPadding: 2
                        C.LoadingDots { color: Theme.brand; anchors.verticalCenter: parent.verticalCenter }
                        Text {
                            text: backend.statusText
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontSm + 1
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }

                    // Error card
                    Item {
                        visible: msg.error
                        width: parent.width
                        height: errRow.implicitHeight + 26
                        Rectangle {
                            anchors.fill: parent
                            radius: 14
                            color: Theme.dangerBg
                            border.color: Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.35)
                        }
                        RowLayout {
                            id: errRow
                            anchors.fill: parent
                            anchors.margins: 13
                            spacing: 10
                            C.Icon { name: "alert"; size: 17; color: Theme.danger; Layout.alignment: Qt.AlignTop }
                            Text {
                                text: msg.content
                                color: Theme.text
                                wrapMode: Text.Wrap
                                font.pixelSize: Theme.fontMd
                                Layout.fillWidth: true
                            }
                            C.Pill {
                                visible: !backend.hasInstalledModels || msg.content.indexOf("Model Library") >= 0
                                text: "Open Library"
                                iconName: "library"
                                onClicked: root.openLibrary(msg.content.indexOf("image") >= 0 ? "vision" : "all")
                            }
                        }
                    }

                    Repeater {
                        model: msg.error ? [] : msg.segments
                        delegate: Loader {
                            required property var modelData
                            width: parent.width
                            sourceComponent: modelData.kind === "code" ? codeBlock
                                           : modelData.kind === "think" ? thinkBlock : textBlock
                            property var seg: modelData
                        }
                    }

                    // Streaming caret
                    Rectangle {
                        visible: msg.streaming && msg.content !== ""
                        width: 9; height: 16; radius: 3
                        color: Theme.brand
                        SequentialAnimation on opacity {
                            running: msg.streaming
                            loops: Animation.Infinite
                            NumberAnimation { from: 1; to: 0.2; duration: 480; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.2; to: 1; duration: 480; easing.type: Easing.InOutSine }
                        }
                    }

                    Row {
                        visible: !msg.streaming && msg.content !== ""
                        spacing: 2
                        opacity: hover.hovered || msg.isLast ? 1 : 0
                        Behavior on opacity { NumberAnimation { duration: Theme.fast } }
                        CopyButton { textToCopy: msg.content; visible: !msg.error }
                        C.IconButton {
                            visible: msg.isLast && !backend.isGenerating
                            iconName: "refresh"
                            iconSize: 16
                            implicitWidth: 28; implicitHeight: 28
                            tip: "Regenerate response"
                            onClicked: backend.regenerate()
                        }
                        Text {
                            leftPadding: 8
                            text: msg.meta
                            color: Theme.textTertiary
                            font.pixelSize: Theme.fontXs + 1
                            anchors.verticalCenter: parent.verticalCenter
                        }
                    }
                }
            }
        }
    }

    // Jump-to-bottom
    C.Pill {
        anchors.horizontalCenter: messages.horizontalCenter
        anchors.bottom: composerArea.top
        anchors.bottomMargin: 6
        visible: opacity > 0
        opacity: root.hasMessages && !messages.atYEnd && messages.contentHeight > messages.height ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: Theme.normal } }
        iconName: "chevron-down"
        implicitWidth: 34
        onClicked: { messages.stickToBottom = true; messages.positionViewAtEnd() }
    }

    component CopyButton: C.IconButton {
        id: cb
        property string textToCopy
        property bool copied: false
        iconName: copied ? "check" : "copy"
        iconColor: copied ? Theme.brand : Theme.textSecondary
        iconSize: 15
        implicitWidth: 28
        implicitHeight: 28
        tip: copied ? "Copied" : "Copy"
        onClicked: { backend.copyText(textToCopy); copied = true; resetTimer.restart() }
        Timer { id: resetTimer; interval: 1500; onTriggered: cb.copied = false }
    }

    Component {
        id: textBlock
        TextEdit {
            property var seg: parent ? parent.seg : ({})
            text: seg.text
            textFormat: TextEdit.MarkdownText
            readOnly: true
            selectByMouse: true
            wrapMode: TextEdit.Wrap
            color: Theme.text
            selectionColor: Theme.brand
            font.pixelSize: Theme.fontMd + 1
            onLinkActivated: (link) => backend.openUrl(link)
            HoverHandler { cursorShape: parent.hoveredLink ? Qt.PointingHandCursor : Qt.IBeamCursor }
        }
    }

    Component {
        id: codeBlock
        Item {
            property var seg: parent ? parent.seg : ({})
            implicitHeight: codeHeader.height + codeText.implicitHeight + 26
            C.Glass { anchors.fill: parent; radius: 14; fill: Theme.codeBg }
            Item {
                id: codeHeader
                width: parent.width
                height: 36
                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 7
                    C.Icon { name: "code"; size: 13; color: Theme.brand; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: seg.lang || "code"
                        color: Theme.textSecondary
                        font.pixelSize: Theme.fontXs + 1
                        font.family: Theme.monoFamily
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                AbstractButton {
                    id: copyCode
                    property bool copied: false
                    anchors.right: parent.right
                    anchors.rightMargin: 8
                    anchors.verticalCenter: parent.verticalCenter
                    implicitHeight: 26
                    implicitWidth: copyRow.implicitWidth + 16
                    hoverEnabled: true
                    onClicked: { backend.copyText(seg.text); copied = true; copyReset.restart() }
                    Timer { id: copyReset; interval: 1500; onTriggered: copyCode.copied = false }
                    background: Rectangle { radius: 13; color: copyCode.hovered ? Theme.hover : "transparent" }
                    contentItem: Item {
                        Row {
                            id: copyRow
                            anchors.centerIn: parent
                            spacing: 5
                            C.Icon { name: copyCode.copied ? "check" : "copy"; size: 13; color: copyCode.copied ? Theme.brand : Theme.textSecondary; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: copyCode.copied ? "Copied" : "Copy"; color: Theme.textSecondary; font.pixelSize: Theme.fontXs + 1; anchors.verticalCenter: parent.verticalCenter }
                        }
                    }
                }
                Rectangle { anchors.bottom: parent.bottom; x: 1; width: parent.width - 2; height: 1; color: Theme.borderSubtle }
            }
            TextEdit {
                id: codeText
                anchors.top: codeHeader.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.margins: 13
                anchors.leftMargin: 15
                text: "<pre style=\"white-space: pre-wrap; margin:0\">" + (seg.html || "") + "</pre>"
                textFormat: TextEdit.RichText
                readOnly: true
                selectByMouse: true
                wrapMode: TextEdit.Wrap
                color: Theme.text
                selectionColor: Theme.brand
                font.family: Theme.monoFamily
                font.pixelSize: Theme.fontSm + 1
            }
        }
    }

    Component {
        id: thinkBlock
        Column {
            id: think
            property var seg: parent ? parent.seg : ({})
            property bool expanded: seg.open
            spacing: 6
            AbstractButton {
                id: thinkToggle
                hoverEnabled: true
                implicitHeight: 26
                implicitWidth: thinkRow.implicitWidth + 8
                onClicked: think.expanded = !think.expanded
                background: null
                contentItem: Row {
                    id: thinkRow
                    spacing: 6
                    C.Icon { name: "brain"; size: 14; color: Theme.brand; anchors.verticalCenter: parent.verticalCenter }
                    Text {
                        text: seg.open ? "Thinking…" : "Thought process"
                        color: thinkToggle.hovered ? Theme.textSecondary : Theme.textTertiary
                        font.pixelSize: Theme.fontSm + 1
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    C.Icon {
                        name: "chevron-down"
                        rotation: think.expanded ? 0 : -90
                        Behavior on rotation { NumberAnimation { duration: Theme.normal } }
                        size: 13
                        color: Theme.textTertiary
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
            Item {
                visible: think.expanded
                width: parent.width
                height: thoughtText.implicitHeight
                Rectangle { width: 2; height: parent.height; radius: 1; color: Theme.brandGlow }
                Text {
                    id: thoughtText
                    x: 14
                    width: parent.width - 14
                    text: seg.text
                    color: Theme.textTertiary
                    wrapMode: Text.Wrap
                    font.pixelSize: Theme.fontMd - 1
                    lineHeight: 1.2
                }
            }
        }
    }

    // ================================================================ composer
    Item {
        id: composerArea
        anchors.bottom: parent.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        height: content.implicitHeight + 16
        Behavior on height { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }

        property var attachments: []
        readonly property bool inputEnabled: backend.ready && backend.hasInstalledModels && backend.runtimeAvailable
        readonly property bool canSend: inputEnabled && !backend.isGenerating
            && (composer.text.trim().length > 0 || attachments.length > 0)

        function send() {
            if (!canSend) return
            if (backend.sendMessage(composer.text, attachments)) {
                composer.text = ""
                attachments = []
                messages.stickToBottom = true
            }
        }

        function usePrompt(text) {
            composer.text = text
            composer.forceActiveFocus()
            composer.cursorPosition = composer.length
        }

        function addFiles(urls) {
            const exts = [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"]
            let list = attachments.slice()
            for (const u of urls) {
                const s = String(u)
                if (exts.some(e => s.toLowerCase().endsWith(e)) && list.indexOf(s) < 0) list.push(s)
            }
            attachments = list.slice(0, 4)
        }

        FileDialog {
            id: fileDialog
            title: "Attach images"
            fileMode: FileDialog.OpenFiles
            nameFilters: ["Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp)"]
            onAccepted: composerArea.addFiles(selectedFiles)
        }

        ColumnLayout {
            id: content
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 12
            anchors.horizontalCenter: parent.horizontalCenter
            width: root.stageWidth
            spacing: 12

            // Quick-action chips (fresh chat only)
            Row {
                Layout.alignment: Qt.AlignHCenter
                visible: root.emptyChat
                spacing: 8
                Repeater {
                    model: [
                        { label: "Explain", icon: "lightbulb", prompt: "Explain in simple terms: " },
                        { label: "Brainstorm", icon: "compass", prompt: "Brainstorm ideas for " },
                        { label: "Write", icon: "pen", prompt: "Help me write " },
                        { label: "Code", icon: "code", prompt: "Write code that " }
                    ]
                    C.Pill {
                        required property var modelData
                        text: modelData.label
                        trailingIcon: modelData.icon
                        onClicked: composerArea.usePrompt(modelData.prompt)
                    }
                }
            }

            // Composer
            Item {
                id: composerBox
                Layout.fillWidth: true
                implicitHeight: boxColumn.implicitHeight + 24

                // Accent focus glow
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -5
                    radius: 27
                    color: "transparent"
                    border.width: 5
                    border.color: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, composer.activeFocus ? 0.14 : 0)
                    Behavior on border.color { ColorAnimation { duration: Theme.normal } }
                }
                C.Glass {
                    anchors.fill: parent
                    radius: 22
                    active: composer.activeFocus
                }

                DropArea {
                    anchors.fill: parent
                    enabled: backend.visionAvailable
                    onDropped: (drop) => { if (drop.hasUrls) composerArea.addFiles(drop.urls) }
                }

                ColumnLayout {
                    id: boxColumn
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.margins: 12
                    anchors.leftMargin: 14
                    spacing: 8

                    // Attachments
                    Row {
                        visible: composerArea.attachments.length > 0
                        spacing: 8
                        Layout.topMargin: 2
                        Repeater {
                            model: composerArea.attachments
                            Rectangle {
                                id: thumb
                                required property string modelData
                                required property int index
                                width: 58; height: 58; radius: 12
                                color: Theme.surfaceRaised
                                border.color: Theme.glassEdgeTop
                                clip: true
                                Image { anchors.fill: parent; anchors.margins: 1; source: thumb.modelData; fillMode: Image.PreserveAspectCrop; sourceSize: Qt.size(116, 116) }
                                C.IconButton {
                                    anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 2
                                    implicitWidth: 20; implicitHeight: 20
                                    iconName: "close"; iconSize: 12; iconColor: "#ffffff"
                                    background: Rectangle { radius: 10; color: "#aa000000" }
                                    onClicked: {
                                        const list = composerArea.attachments.slice()
                                        list.splice(thumb.index, 1)
                                        composerArea.attachments = list
                                    }
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 6
                        C.Icon {
                            name: "sparkles"
                            size: 18
                            color: Theme.brand
                            Layout.alignment: Qt.AlignTop
                            Layout.topMargin: 8
                            opacity: composerArea.inputEnabled ? 1 : 0.4
                        }
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: Math.min(Math.max(composer.implicitHeight, 26), 220)
                            ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                            TextArea {
                                id: composer
                                enabled: composerArea.inputEnabled
                                placeholderText: !backend.ready ? "Starting…"
                                    : !backend.hasInstalledModels ? "Download a model to start chatting"
                                    : !backend.runtimeAvailable ? "The local runtime could not be loaded"
                                    : "Ask anything…"
                                placeholderTextColor: Theme.textTertiary
                                color: Theme.text
                                selectionColor: Theme.brand
                                selectedTextColor: "#ffffff"
                                font.pixelSize: Theme.fontMd + 1
                                wrapMode: TextArea.Wrap
                                leftPadding: 4
                                rightPadding: 8
                                topPadding: 7
                                bottomPadding: 4
                                background: null
                                Keys.onReturnPressed: (event) => {
                                    if (event.modifiers & Qt.ShiftModifier) { event.accepted = false; return }
                                    event.accepted = true
                                    composerArea.send()
                                }
                                Keys.onEnterPressed: (event) => Keys.returnPressed(event)
                            }
                        }
                    }

                    // Toolbar
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: 2
                        spacing: 2

                        ToolbarButton {
                            visible: backend.visionAvailable
                            enabled: composerArea.inputEnabled
                            iconName: "paperclip"
                            text: "Attach"
                            onClicked: fileDialog.open()
                        }

                        // Status
                        Row {
                            Layout.fillWidth: true
                            Layout.leftMargin: 8
                            spacing: 8
                            clip: true
                            C.LoadingDots {
                                visible: backend.runtimeState !== "idle"
                                color: Theme.brand
                                dot: 4
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Text {
                                width: parent.width - 30
                                text: backend.runtimeState !== "idle" ? backend.statusText
                                    : backend.modelMode === "auto" && backend.lastRouteReason ? backend.lastRouteReason : ""
                                color: Theme.textTertiary
                                font.pixelSize: Theme.fontXs + 1
                                elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter
                            }
                        }

                        // Send / Stop
                        AbstractButton {
                            id: sendBtn
                            implicitWidth: 36
                            implicitHeight: 36
                            hoverEnabled: true
                            readonly property bool stopMode: root.generatingHere
                            enabled: stopMode || composerArea.canSend
                            onClicked: stopMode ? backend.stopGeneration() : composerArea.send()
                            ToolTip.visible: hovered
                            ToolTip.delay: 600
                            ToolTip.text: stopMode ? "Stop generating  ⌘." : "Send  ↩"
                            scale: down ? 0.9 : 1
                            Behavior on scale { NumberAnimation { duration: 90 } }
                            background: Item {
                                // Glow
                                Rectangle {
                                    anchors.centerIn: parent
                                    width: parent.width + 12; height: width; radius: width / 2
                                    color: "transparent"
                                    border.width: 6
                                    border.color: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b,
                                                          sendBtn.enabled && !sendBtn.stopMode ? (sendBtn.hovered ? 0.30 : 0.18) : 0)
                                    Behavior on border.color { ColorAnimation { duration: Theme.normal } }
                                }
                                Rectangle {
                                    anchors.fill: parent
                                    radius: sendBtn.stopMode ? 12 : width / 2
                                    Behavior on radius { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutCubic } }
                                    gradient: Gradient {
                                        GradientStop { position: 0; color: !sendBtn.enabled ? Theme.accentMuted : sendBtn.stopMode ? Theme.accent : Qt.lighter(Theme.brand, sendBtn.hovered ? 1.35 : 1.2) }
                                        GradientStop { position: 1; color: !sendBtn.enabled ? Theme.accentMuted : sendBtn.stopMode ? Theme.accent : Qt.darker(Theme.brand, 1.15) }
                                    }
                                }
                            }
                            contentItem: Item {
                                C.Icon {
                                    anchors.centerIn: parent
                                    name: "arrow-up"
                                    size: 18
                                    color: "#ffffff"
                                    opacity: sendBtn.stopMode ? 0 : (sendBtn.enabled ? 1 : 0.6)
                                    scale: sendBtn.stopMode ? 0.4 : 1
                                    rotation: sendBtn.stopMode ? 90 : 0
                                    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                                    Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
                                    Behavior on rotation { NumberAnimation { duration: Theme.normal } }
                                }
                                C.Icon {
                                    anchors.centerIn: parent
                                    name: "stop"
                                    size: 13
                                    color: Theme.textOnPrimary
                                    opacity: sendBtn.stopMode ? 1 : 0
                                    scale: sendBtn.stopMode ? 1 : 0.4
                                    Behavior on opacity { NumberAnimation { duration: Theme.normal } }
                                    Behavior on scale { NumberAnimation { duration: Theme.normal; easing.type: Easing.OutBack } }
                                }
                            }
                        }
                    }
                }
            }

            Text {
                visible: !root.emptyChat
                text: "smolchat runs entirely on this computer. Small models can make mistakes — check important information."
                color: Theme.textTertiary
                font.pixelSize: Theme.fontXs
                elide: Text.ElideRight
                horizontalAlignment: Text.AlignHCenter
                Layout.fillWidth: true
            }
        }
    }

    component ToolbarButton: AbstractButton {
        id: tb
        property string iconName
        property color iconTint: Theme.textSecondary
        implicitHeight: 30
        implicitWidth: tbRow.implicitWidth + 18
        hoverEnabled: true
        scale: down ? 0.96 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        background: Rectangle {
            radius: 15
            color: tb.hovered ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
        contentItem: Item {
            implicitWidth: tbRow.implicitWidth
            Row {
                id: tbRow
                anchors.centerIn: parent
                spacing: 6
                opacity: tb.enabled ? 1 : 0.45
                C.Icon { name: tb.iconName; size: 14; color: tb.iconTint; anchors.verticalCenter: parent.verticalCenter }
                Text { text: tb.text; color: Theme.textSecondary; font.pixelSize: Theme.fontSm + 1; anchors.verticalCenter: parent.verticalCenter }
            }
        }
    }

    Connections {
        target: backend
        function onConversationChanged() {
            composerArea.attachments = []
            if (backend.ready) composer.forceActiveFocus()
        }
    }
}
