import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Effects
import "."

// Shared building blocks, used as C.Icon, C.IconButton, C.Button, ...
QtObject {

    // Tinted SVG icon from resources/icons via the "icon" image provider.
    component Icon: Item {
        id: icon
        property string name
        property color color: Theme.textSecondary
        property int size: 18
        implicitWidth: size
        implicitHeight: size
        width: size
        height: size
        Image {
            anchors.fill: parent
            sourceSize: Qt.size(icon.size * 2, icon.size * 2)
            source: icon.name ? "image://icon/" + icon.name + "?color=" + String(icon.color).replace("#", "") : ""
            smooth: true
            fillMode: Image.PreserveAspectFit
        }
    }

    // Square, borderless icon button with hover background and tooltip.
    component IconButton: AbstractButton {
        id: ib
        property string iconName
        property int iconSize: 18
        property color iconColor: Theme.textSecondary
        property string tip
        property bool highlighted: false
        implicitWidth: 32
        implicitHeight: 32
        hoverEnabled: true
        focusPolicy: Qt.NoFocus
        scale: down ? 0.92 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        background: Rectangle {
            radius: Theme.radiusSm + 2
            color: ib.down ? Theme.hoverStrong : (ib.hovered || ib.highlighted) ? Theme.hover : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
        contentItem: Item {
            Icon {
                anchors.centerIn: parent
                name: ib.iconName
                size: ib.iconSize
                color: ib.enabled ? ib.iconColor : Theme.textTertiary
                opacity: ib.enabled ? 1 : 0.5
            }
        }
        ToolTip.visible: tip !== "" && hovered
        ToolTip.delay: 600
        ToolTip.text: tip
    }

    // Text button. kind: "primary" | "secondary" | "ghost" | "danger"
    component ActionButton: AbstractButton {
        id: btn
        property string kind: "secondary"
        property string iconName
        property bool compact: false
        implicitHeight: compact ? 28 : 34
        implicitWidth: row.implicitWidth + (compact ? 20 : 28)
        hoverEnabled: true
        scale: down ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        font.family: Theme.fontFamily
        font.pixelSize: compact ? Theme.fontSm : Theme.fontMd - 1
        font.weight: Font.Medium
        readonly property color fg: kind === "primary" ? "#ffffff"
                                   : kind === "danger" ? "#ffffff" : Theme.text
        background: Rectangle {
            radius: btn.height / 2
            gradient: btn.kind === "primary" && btn.enabled ? primaryGradient : null
            Gradient {
                id: primaryGradient
                GradientStop { position: 0; color: Qt.lighter(Theme.brand, btn.hovered ? 1.12 : 1.0) }
                GradientStop { position: 1; color: Qt.darker(Theme.brand, 1.35) }
            }
            color: {
                if (!btn.enabled) return btn.kind === "primary" ? Theme.accentMuted : "transparent"
                if (btn.kind === "primary") return Theme.brand
                if (btn.kind === "danger") return btn.hovered ? Qt.darker(Theme.danger, 1.1) : Theme.danger
                if (btn.kind === "ghost") return btn.hovered ? Theme.hover : "transparent"
                return btn.hovered ? Theme.hover : "transparent"
            }
            border.width: btn.kind === "secondary" ? 1 : 0
            border.color: Theme.border
            Behavior on color { ColorAnimation { duration: Theme.fast } }
        }
        contentItem: Item {
            implicitWidth: row.implicitWidth
            implicitHeight: row.implicitHeight
            Row {
                id: row
                anchors.centerIn: parent
                spacing: 6
                Icon {
                    visible: btn.iconName !== ""
                    name: btn.iconName
                    size: btn.compact ? 14 : 16
                    color: btn.fg
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    text: btn.text
                    font: btn.font
                    color: btn.fg
                    opacity: btn.enabled ? 1 : 0.6
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }

    // Small pill label.
    component Badge: Rectangle {
        property alias text: label.text
        property color tint: Theme.textSecondary
        implicitWidth: label.implicitWidth + 12
        implicitHeight: 20
        radius: 10
        color: Theme.dark ? Qt.rgba(tint.r, tint.g, tint.b, 0.12) : Qt.rgba(tint.r, tint.g, tint.b, 0.10)
        Text {
            id: label
            anchors.centerIn: parent
            font.family: Theme.fontFamily
            font.pixelSize: Theme.fontXs
            font.weight: Font.Medium
            color: parent.tint
        }
    }

    component Separator: Rectangle {
        implicitHeight: 1
        implicitWidth: 1
        color: Theme.borderSubtle
    }

    // Thin progress bar. While `indeterminate` (e.g. connecting) a short runner
    // sweeps across; otherwise the fill grows from the left edge with `value`.
    component SlimProgress: Rectangle {
        id: bar
        property real value: 0
        property bool indeterminate: false
        implicitHeight: 6
        radius: height / 2
        color: Theme.hoverStrong
        clip: true

        Rectangle {
            visible: !bar.indeterminate
            x: 0
            height: parent.height
            radius: parent.radius
            color: Theme.brand
            // Keep tiny but non-zero progress visible on slow connections.
            width: bar.value > 0 ? Math.max(bar.height, bar.width * Math.min(1, bar.value)) : 0
            Behavior on width { NumberAnimation { duration: 250; easing.type: Easing.OutCubic } }
        }

        Rectangle {
            id: runner
            visible: bar.indeterminate
            width: bar.width * 0.3
            height: parent.height
            radius: parent.radius
            color: Theme.brand
            NumberAnimation on x {
                running: bar.indeterminate && bar.visible
                loops: Animation.Infinite
                from: -runner.width
                to: bar.width
                duration: 1100
                easing.type: Easing.InOutQuad
            }
        }
    }

    // Styled text field (used for search and rename).
    component Field: TextField {
        id: field
        property string iconName
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontMd - 1
        color: Theme.text
        placeholderTextColor: Theme.textTertiary
        selectionColor: Theme.brand
        selectedTextColor: "#ffffff"
        leftPadding: iconName ? 32 : 10
        rightPadding: 10
        implicitHeight: 34
        background: Rectangle {
            radius: Theme.radiusMd
            border.width: 1
            color: field.activeFocus ? Theme.surface : "transparent"
            border.color: field.activeFocus ? Theme.brand : Theme.borderSubtle
            Behavior on border.color { ColorAnimation { duration: Theme.fast } }
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            Icon {
                visible: field.iconName !== ""
                name: field.iconName
                size: 15
                color: Theme.textTertiary
                anchors.left: parent.left
                anchors.leftMargin: 10
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    component MenuItemStyled: MenuItem {
        id: mi
        property string iconName
        property bool destructive: false
        property bool checkedMark: false
        property string detail
        implicitHeight: detail ? 46 : 34
        implicitWidth: 240
        font.family: Theme.fontFamily
        font.pixelSize: Theme.fontMd - 1
        background: Rectangle {
            radius: Theme.radiusSm + 2
            anchors.fill: parent
            anchors.leftMargin: 4
            anchors.rightMargin: 4
            color: mi.highlighted ? Theme.hoverStrong : "transparent"
        }
        contentItem: RowLayout {
            spacing: 10
            Icon {
                visible: mi.iconName !== ""
                name: mi.iconName
                size: 16
                color: mi.destructive ? Theme.danger : Theme.textSecondary
                Layout.leftMargin: 6
            }
            ColumnLayout {
                spacing: 1
                Layout.fillWidth: true
                Layout.leftMargin: mi.iconName ? 0 : 6
                Text {
                    text: mi.text
                    font: mi.font
                    color: mi.destructive ? Theme.danger : Theme.text
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
                Text {
                    visible: mi.detail !== ""
                    text: mi.detail
                    font.family: Theme.fontFamily
                    font.pixelSize: Theme.fontXs
                    color: Theme.textTertiary
                    elide: Text.ElideRight
                    Layout.fillWidth: true
                }
            }
            Icon {
                visible: mi.checkedMark
                name: "check"
                size: 15
                color: Theme.text
                Layout.rightMargin: 8
            }
        }
        indicator: null
        arrow: null
    }

    component MenuStyled: Menu {
        id: menu
        padding: 5
        implicitWidth: 260
        delegate: MenuItemStyled {}
        background: Glass { implicitWidth: 220; radius: 14; fill: Theme.popup }
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }
    }

    component MenuSeparatorStyled: MenuSeparator {
        contentItem: Rectangle { implicitHeight: 1; color: Theme.borderSubtle }
        topPadding: 4
        bottomPadding: 4
    }

    // Modal confirmation dialog.
    component ConfirmDialog: Popup {
        id: dlg
        property string title
        property string message
        property string confirmText: "Confirm"
        property string cancelText: "Cancel"
        property bool destructive: false
        property string extraText: ""  // optional third action
        signal confirmed()
        signal extra()
        modal: true
        focus: true
        anchors.centerIn: Overlay.overlay
        width: 400
        padding: 22
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        Overlay.modal: Rectangle { color: Theme.overlay }
        background: Glass { radius: 18; fill: Theme.popup }
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fast }
            NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: Theme.normal; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.fast } }
        contentItem: ColumnLayout {
            spacing: 10
            Text {
                text: dlg.title
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontLg
                font.weight: Font.DemiBold
                color: Theme.text
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
            Text {
                text: dlg.message
                visible: text !== ""
                font.family: Theme.fontFamily
                font.pixelSize: Theme.fontMd - 1
                color: Theme.textSecondary
                wrapMode: Text.Wrap
                lineHeight: 1.2
                Layout.fillWidth: true
            }
            RowLayout {
                Layout.topMargin: 12
                spacing: 8
                Item { Layout.fillWidth: true }
                ActionButton {
                    text: dlg.cancelText
                    kind: "secondary"
                    onClicked: dlg.close()
                }
                ActionButton {
                    visible: dlg.extraText !== ""
                    text: dlg.extraText
                    kind: "secondary"
                    onClicked: { dlg.close(); dlg.extra() }
                }
                ActionButton {
                    visible: dlg.confirmText !== ""
                    text: dlg.confirmText
                    kind: dlg.destructive ? "danger" : "primary"
                    onClicked: { dlg.close(); dlg.confirmed() }
                }
            }
        }
    }

    // Three softly pulsing dots used while a model is loading/thinking.
    component LoadingDots: Row {
        property color color: Theme.textTertiary
        property int dot: 6
        spacing: 5
        Repeater {
            model: 3
            Rectangle {
                required property int index
                width: parent.dot
                height: parent.dot
                radius: width / 2
                color: parent.color
                opacity: 0.25
                SequentialAnimation on opacity {
                    loops: Animation.Infinite
                    PauseAnimation { duration: index * 160 }
                    NumberAnimation { to: 1; duration: 380; easing.type: Easing.InOutQuad }
                    NumberAnimation { to: 0.25; duration: 380; easing.type: Easing.InOutQuad }
                    PauseAnimation { duration: (2 - index) * 160 }
                }
            }
        }
    }

    // ------------------------------------------------------------ glossy kit

    // Rounded panel with ambient, slowly drifting accent light.
    component Backdrop: Item {
        id: bd
        property real radius: 18
        property bool animate: true
        property real drift: 0
        NumberAnimation on drift {
            running: bd.animate && bd.visible
            from: 0; to: Math.PI * 2
            duration: 26000
            loops: Animation.Infinite
        }
        readonly property color glowA: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, Theme.glowStrength)
        readonly property color glowB: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, Theme.glowStrength * 0.8)

        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeWidth: -1
                fillColor: Theme.panel
                PathRectangle { x: 0; y: 0; width: bd.width; height: bd.height; radius: bd.radius }
            }
            // Main glow, upper right
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: bd.width * (0.10 + 0.05 * Math.cos(bd.drift))
                    centerY: bd.height * (0.02 + 0.04 * Math.sin(bd.drift))
                    centerRadius: Math.max(bd.width, bd.height) * 0.62
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: bd.glowA }
                    GradientStop { position: 0.45; color: Qt.rgba(bd.glowA.r, bd.glowA.g, bd.glowA.b, bd.glowA.a * 0.35) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                PathRectangle { x: 0; y: 0; width: bd.width; height: bd.height; radius: bd.radius }
            }
            // Secondary glow, behind the centre stage
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: bd.width * (0.94 + 0.04 * Math.sin(bd.drift * 2))
                    centerY: bd.height * (0.98 + 0.03 * Math.cos(bd.drift))
                    centerRadius: Math.max(bd.width, bd.height) * 0.6
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: bd.glowB }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                PathRectangle { x: 0; y: 0; width: bd.width; height: bd.height; radius: bd.radius }
            }
            // Hairline edge
            ShapePath {
                strokeWidth: 1
                strokeColor: Theme.panelEdge
                fillColor: "transparent"
                PathRectangle { x: 0.5; y: 0.5; width: bd.width - 1; height: bd.height - 1; radius: bd.radius }
            }
        }
    }

    // The smollabs mascot rendered as a glossy 3D figure: an extruded body
    // (stacked tinted silhouettes whose depth follows the tilt), a light sweep
    // masked to the mascot's shape, warm core + violet outer glow, floor
    // shadow, orbiting sparkles and pointer-driven perspective tilt.
    component Mascot3D: Item {
        id: m
        property real size: 240                 // width; height follows the artwork
        property real tiltX: 0
        property real tiltY: 0
        property bool animate: true
        property real energy: 0                 // > 0 while busy: livelier motion
        property int depth: 7                   // extrusion slices
        readonly property real ratio: 705 / 1060
        width: size
        height: size * ratio
        implicitWidth: width
        implicitHeight: height

        property real t: 0
        NumberAnimation on t {
            running: m.animate && m.visible
            from: 0; to: Math.PI * 2
            duration: m.energy > 0 ? 3400 : 8200
            loops: Animation.Infinite
        }
        property real sweep: -0.5
        SequentialAnimation on sweep {
            running: m.animate && m.visible
            loops: Animation.Infinite
            NumberAnimation { from: -0.5; to: 1.5; duration: 2000; easing.type: Easing.InOutCubic }
            PauseAnimation { duration: 4200 }
        }

        property real smoothTiltX: tiltX
        property real smoothTiltY: tiltY
        Behavior on smoothTiltX { SpringAnimation { spring: 2.4; damping: 0.26 } }
        Behavior on smoothTiltY { SpringAnimation { spring: 2.4; damping: 0.26 } }
        readonly property real rx: smoothTiltX + (animate ? 4 * Math.sin(t) : 0)
        readonly property real ry: smoothTiltY + (animate ? 6 * Math.cos(t * 0.75) : 0)
        readonly property real lift: animate ? 6 * Math.sin(t * 1.3) : 0
        // Extrusion direction: the body shows on the side facing away from the light.
        readonly property real ex: -ry * 0.035 * size / 240
        readonly property real ey: (0.8 + rx * 0.025) * size / 240

        // Floor shadow
        Shape {
            anchors.horizontalCenter: parent.horizontalCenter
            y: m.height * 0.9
            width: m.size * 0.8
            height: m.size * 0.16
            opacity: 0.85 - m.lift * 0.03
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: m.size * 0.4; centerY: m.size * 0.08
                    centerRadius: m.size * 0.4
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0; color: Theme.dark ? "#a6000000" : "#33000000" }
                    GradientStop { position: 1; color: "transparent" }
                }
                PathRectangle { x: 0; y: 0; width: m.size * 0.8; height: m.size * 0.16; radius: m.size * 0.08 }
            }
        }

        // Glow: warm flame core inside a violet aura
        Shape {
            anchors.centerIn: parent
            width: m.size * 1.7; height: width
            scale: 1 + 0.04 * Math.sin(m.t * 2) + m.energy * 0.07 * Math.sin(m.t * 4)
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: m.size * 0.85; centerY: m.size * 0.85
                    centerRadius: m.size * 0.85
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0.0; color: Qt.rgba(Theme.flame.r, Theme.flame.g, Theme.flame.b, Theme.dark ? 0.30 : 0.18) }
                    GradientStop { position: 0.32; color: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, Theme.dark ? 0.30 : 0.16) }
                    GradientStop { position: 0.7; color: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, 0.06) }
                    GradientStop { position: 1.0; color: "transparent" }
                }
                PathRectangle { x: 0; y: 0; width: m.size * 1.7; height: m.size * 1.7; radius: m.size * 0.85 }
            }
        }

        // Artwork sources (hidden; sampled by the effects below)
        Image {
            id: art
            anchors.fill: body
            source: "../resources/assets/logo/smollabs_mascot_clean.png"
            sourceSize: Qt.size(Math.min(1060, m.size * 2.2), Math.min(705, m.size * 2.2 * m.ratio))
            smooth: true
            mipmap: true
            visible: false
        }
        Item {
            id: sweepSource
            anchors.fill: body
            visible: false
            clip: true
            Rectangle {
                width: m.size * 0.5
                height: m.height * 3
                x: m.size * m.sweep - width / 2
                y: -m.height
                rotation: 22
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0.0; color: "transparent" }
                    GradientStop { position: 0.5; color: "#80ffffff" }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
        }

        Item {
            id: body
            anchors.fill: parent
            transform: [
                Rotation { origin.x: m.width / 2; origin.y: m.height / 2; axis { x: 1; y: 0; z: 0 } angle: m.rx },
                Rotation { origin.x: m.width / 2; origin.y: m.height / 2; axis { x: 0; y: 1; z: 0 } angle: m.ry },
                Translate { y: -m.lift }
            ]

            // Extruded body
            Repeater {
                model: m.depth
                MultiEffect {
                    required property int index
                    readonly property int slice: m.depth - index      // farthest first
                    x: slice * m.ex
                    y: slice * m.ey
                    width: m.width
                    height: m.height
                    source: art
                    autoPaddingEnabled: false
                    colorization: 1.0
                    colorizationColor: Qt.darker(Theme.brandDeep, 1 + slice * 0.09)
                }
            }

            // Face with a soft violet aura
            MultiEffect {
                anchors.fill: parent
                source: art
                autoPaddingEnabled: true
                shadowEnabled: true
                shadowColor: Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, Theme.dark ? 0.55 : 0.35)
                shadowBlur: 1.0
                blurMax: 40
                shadowScale: 1.02
                shadowHorizontalOffset: 0
                shadowVerticalOffset: 0
                brightness: 0.02
                saturation: 0.08
            }

            // Light sweep, clipped to the mascot's silhouette
            MultiEffect {
                anchors.fill: parent
                source: sweepSource
                maskEnabled: true
                maskSource: art
                autoPaddingEnabled: false
                opacity: 0.9
            }
        }

        // Orbiting sparkles for depth
        Repeater {
            model: 5
            Text {
                id: sp
                required property int index
                readonly property real a: m.t * (index % 2 ? 1 : -1) + index * 1.26
                x: m.width / 2 + Math.cos(a) * m.size * (0.52 + index * 0.03) - width / 2
                y: m.height / 2 + Math.sin(a) * m.size * 0.22 - height / 2 - m.lift
                z: Math.sin(a) > 0 ? 1 : -1
                text: "✦"
                color: index % 2 ? Theme.flameLight : Qt.lighter(Theme.brand, 1.3)
                font.pixelSize: 9 + index * 2
                opacity: m.animate ? 0.35 + 0.5 * (0.5 + 0.5 * Math.sin(a * 2)) : 0
                scale: 0.75 + 0.3 * Math.sin(a)
            }
        }
    }

    // Small flat logo mark (sidebar, avatars).
    component LogoMark: Item {
        id: mark
        property real size: 28
        property bool busy: false
        width: size
        height: size
        implicitWidth: size
        implicitHeight: size
        Image {
            anchors.fill: parent
            source: "../resources/assets/logo/logo-157.png"
            sourceSize: Qt.size(mark.size * 2, mark.size * 2)
            smooth: true
            mipmap: true
        }
        // Breathing accent ring while busy
        Rectangle {
            anchors.centerIn: parent
            width: mark.size + 6; height: width
            radius: mark.size * 0.105 + 3
            color: "transparent"
            border.width: 1.5
            border.color: Theme.brand
            visible: mark.busy
            SequentialAnimation on opacity {
                running: mark.busy
                loops: Animation.Infinite
                NumberAnimation { from: 0.15; to: 0.95; duration: 700; easing.type: Easing.InOutSine }
                NumberAnimation { from: 0.95; to: 0.15; duration: 700; easing.type: Easing.InOutSine }
            }
        }
    }

    // Glass panel: translucent fill, gradient edge (bright on top) and sheen.
    component Glass: Item {
        id: glass
        property real radius: 16
        property bool hovered: false
        property bool active: false
        property color fill: hovered ? Theme.glassFillHover : Theme.glassFill
        // Edge
        Rectangle {
            anchors.fill: parent
            radius: glass.radius
            gradient: Gradient {
                GradientStop { position: 0; color: glass.active ? Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, 0.75) : Theme.glassEdgeTop }
                GradientStop { position: 1; color: glass.active ? Qt.rgba(Theme.brand.r, Theme.brand.g, Theme.brand.b, 0.30) : Theme.glassEdgeBottom }
            }
        }
        // Body
        Rectangle {
            anchors.fill: parent
            anchors.margins: 1
            radius: glass.radius - 1
            color: glass.fill
            Behavior on color { ColorAnimation { duration: Theme.fast } }
            // Sheen
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: Math.min(parent.height, 48)
                radius: parent.radius
                gradient: Gradient {
                    GradientStop { position: 0; color: Theme.glassSheen }
                    GradientStop { position: 1; color: "transparent" }
                }
            }
        }
    }

    // Pill button with glass styling: icon and/or text.
    component Pill: AbstractButton {
        id: pill
        property string iconName
        property string trailingIcon
        property bool accent: false
        property int iconSize: 14
        implicitHeight: 32
        implicitWidth: pillRow.implicitWidth + 26
        hoverEnabled: true
        scale: down ? 0.96 : 1
        Behavior on scale { NumberAnimation { duration: 90 } }
        font.pixelSize: Theme.fontSm + 1
        font.weight: Font.Medium
        background: Glass {
            radius: pill.height / 2
            hovered: pill.hovered
            active: pill.accent
        }
        contentItem: Item {
            implicitWidth: pillRow.implicitWidth
            Row {
                id: pillRow
                anchors.centerIn: parent
                spacing: 7
                Icon {
                    visible: pill.iconName !== ""
                    name: pill.iconName
                    size: pill.iconSize
                    color: pill.accent ? Theme.brand : Theme.textSecondary
                    anchors.verticalCenter: parent.verticalCenter
                }
                Text {
                    visible: pill.text !== ""
                    text: pill.text
                    font: pill.font
                    color: Theme.text
                    anchors.verticalCenter: parent.verticalCenter
                }
                Icon {
                    visible: pill.trailingIcon !== ""
                    name: pill.trailingIcon
                    size: 13
                    color: Theme.textTertiary
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
    }
}
