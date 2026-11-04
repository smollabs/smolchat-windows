import QtQuick
import QtQuick.Shapes
import "."

// Opening sequence: light blooms, the 3D logo spins into place with ripples
// and sparkles, the name writes itself in, then everything dissolves into
// the app. Click anywhere to skip.
Rectangle {
    id: splash
    color: "#04030b"

    property string status: ""
    property bool finished: false
    signal dismissed()
    signal fading()

    // Long enough to enjoy the intro, short enough not to get in the way.
    property bool minTimeElapsed: false
    Timer { interval: 2500; running: true; onTriggered: splash.minTimeElapsed = true }

    readonly property bool canDismiss: finished && minTimeElapsed
    onCanDismissChanged: if (canDismiss) outro.start()

    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        onClicked: splash.minTimeElapsed = true
    }

    readonly property color glow: Theme.brand

    // ------------------------------------------------------------ light
    Item {
        id: lights
        anchors.fill: parent
        opacity: 0
        property real bloom: 0.35
        Shape {
            anchors.fill: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: splash.width * 0.5; centerY: splash.height * 0.42
                    centerRadius: Math.max(splash.width, splash.height) * 0.55 * lights.bloom
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0; color: Qt.rgba(splash.glow.r, splash.glow.g, splash.glow.b, 0.30) }
                    GradientStop { position: 0.5; color: Qt.rgba(splash.glow.r, splash.glow.g, splash.glow.b, 0.06) }
                    GradientStop { position: 1; color: "transparent" }
                }
                PathRectangle { x: 0; y: 0; width: splash.width; height: splash.height }
            }
            ShapePath {
                strokeWidth: -1
                fillGradient: RadialGradient {
                    centerX: splash.width * 0.85; centerY: splash.height * 0.05
                    centerRadius: Math.max(splash.width, splash.height) * 0.6 * lights.bloom
                    focalX: centerX; focalY: centerY
                    GradientStop { position: 0; color: Qt.rgba(splash.glow.r, splash.glow.g, splash.glow.b, 0.22) }
                    GradientStop { position: 1; color: "transparent" }
                }
                PathRectangle { x: 0; y: 0; width: splash.width; height: splash.height }
            }
        }
    }

    // --------------------------------------------------------- centrepiece
    Item {
        id: stage
        width: 380
        height: 420
        anchors.centerIn: parent
        anchors.verticalCenterOffset: -20

        // Ripples radiating from the logo
        Repeater {
            model: 3
            Rectangle {
                id: ripple
                required property int index
                x: stage.width / 2 - width / 2
                y: 100 - height / 2
                width: 240; height: 150
                radius: height / 2
                color: "transparent"
                border.width: 1.5
                border.color: splash.glow
                opacity: 0
                scale: 0.6
                SequentialAnimation {
                    running: true
                    loops: Animation.Infinite
                    PauseAnimation { duration: 350 + ripple.index * 520 }
                    ParallelAnimation {
                        NumberAnimation { target: ripple; property: "scale"; from: 0.7; to: 1.9; duration: 1600; easing.type: Easing.OutCubic }
                        NumberAnimation { target: ripple; property: "opacity"; from: 0.5; to: 0; duration: 1600; easing.type: Easing.OutQuad }
                    }
                    PauseAnimation { duration: (2 - ripple.index) * 520 }
                }
            }
        }

        // Twinkling sparkles
        Repeater {
            model: 14
            Text {
                id: star
                required property int index
                readonly property real angle: index * 2.4 + 0.6
                readonly property real dist: 165 + (index * 37) % 60
                x: stage.width / 2 + Math.cos(angle) * dist - width / 2
                y: 100 + Math.sin(angle) * dist * 0.7 - height / 2 - drift
                property real drift: 0
                text: "✦"
                color: index % 3 === 0 ? "#ffffff" : index % 3 === 1 ? Theme.flameLight : Qt.lighter(splash.glow, 1.35)
                font.pixelSize: 8 + (index * 5) % 10
                opacity: 0
                scale: 0
                SequentialAnimation {
                    running: true
                    loops: Animation.Infinite
                    PauseAnimation { duration: 500 + (star.index * 173) % 900 }
                    ParallelAnimation {
                        NumberAnimation { target: star; property: "scale"; from: 0; to: 1; duration: 420; easing.type: Easing.OutBack }
                        NumberAnimation { target: star; property: "opacity"; from: 0; to: 0.95; duration: 420 }
                        NumberAnimation { target: star; property: "drift"; from: 0; to: 10; duration: 1300; easing.type: Easing.OutQuad }
                    }
                    ParallelAnimation {
                        NumberAnimation { target: star; property: "scale"; to: 0; duration: 700; easing.type: Easing.InQuad }
                        NumberAnimation { target: star; property: "opacity"; to: 0; duration: 700 }
                    }
                    PauseAnimation { duration: 300 + (star.index * 211) % 700 }
                }
            }
        }

        C.Mascot3D {
            id: logo
            size: 300
            x: stage.width / 2 - width / 2
            y: 100 - height / 2
            opacity: 0
            scale: 0.4
            tiltY: 80     // starts edge-on; springs to face the viewer
            tiltX: -20
        }

        // Name, written in letter by letter
        Row {
            id: title
            anchors.horizontalCenter: parent.horizontalCenter
            y: 236
            spacing: 0
            Repeater {
                model: "smolchat".split("")
                Text {
                    id: letter
                    required property string modelData
                    required property int index
                    text: modelData
                    color: "#f7f3ff"
                    font.family: Theme.fontFamily
                    font.pixelSize: 38
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.6
                    opacity: 0
                    transform: Translate { id: lift; y: 18 }
                    SequentialAnimation {
                        running: true
                        PauseAnimation { duration: 820 + letter.index * 55 }
                        ParallelAnimation {
                            NumberAnimation { target: letter; property: "opacity"; to: 1; duration: 380; easing.type: Easing.OutCubic }
                            NumberAnimation { target: lift; property: "y"; to: 0; duration: 520; easing.type: Easing.OutBack; easing.overshoot: 1.6 }
                        }
                    }
                }
            }
        }

        Text {
            id: tagline
            anchors.horizontalCenter: parent.horizontalCenter
            y: 290
            text: "by smollabs  ·  private AI that lives on your computer"
            color: "#8f8c9c"
            font.family: Theme.fontFamily
            font.pixelSize: 13
            font.letterSpacing: 0.3
            opacity: 0
        }

        // Shimmer line + status
        Item {
            id: progress
            anchors.horizontalCenter: parent.horizontalCenter
            y: 338
            width: 160
            height: 2
            opacity: 0
            Rectangle { anchors.fill: parent; radius: 1; color: "#1fffffff" }
            Rectangle {
                id: shimmer
                width: 60; height: parent.height; radius: 1
                gradient: Gradient {
                    orientation: Gradient.Horizontal
                    GradientStop { position: 0; color: "transparent" }
                    GradientStop { position: 0.5; color: Qt.lighter(splash.glow, 1.4) }
                    GradientStop { position: 1; color: "transparent" }
                }
                NumberAnimation on x {
                    loops: Animation.Infinite
                    from: -60; to: 160
                    duration: 1200
                    easing.type: Easing.InOutSine
                }
            }
        }
        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            y: 352
            text: splash.status
            color: "#5f5c6b"
            font.family: Theme.fontFamily
            font.pixelSize: 11
            opacity: progress.opacity
        }
    }

    // ------------------------------------------------------------- intro
    SequentialAnimation {
        running: true
        ParallelAnimation {
            NumberAnimation { target: lights; property: "opacity"; to: 1; duration: 900; easing.type: Easing.OutCubic }
            NumberAnimation { target: lights; property: "bloom"; to: 1; duration: 1600; easing.type: Easing.OutCubic }
            SequentialAnimation {
                PauseAnimation { duration: 150 }
                ScriptAction { script: { logo.tiltY = 0; logo.tiltX = 0 } }
                ParallelAnimation {
                    NumberAnimation { target: logo; property: "opacity"; to: 1; duration: 380 }
                    NumberAnimation { target: logo; property: "scale"; to: 1; duration: 820; easing.type: Easing.OutBack; easing.overshoot: 1.4 }
                }
            }
            SequentialAnimation {
                PauseAnimation { duration: 1250 }
                NumberAnimation { target: tagline; property: "opacity"; to: 1; duration: 450; easing.type: Easing.OutCubic }
            }
            SequentialAnimation {
                PauseAnimation { duration: 1500 }
                NumberAnimation { target: progress; property: "opacity"; to: 1; duration: 350 }
            }
        }
    }

    // ------------------------------------------------------------- outro
    SequentialAnimation {
        id: outro
        ScriptAction { script: splash.fading() }
        ParallelAnimation {
            NumberAnimation { target: logo; property: "scale"; to: 1.35; duration: 520; easing.type: Easing.InCubic }
            NumberAnimation { target: stage; property: "opacity"; to: 0; duration: 380; easing.type: Easing.InQuad }
            NumberAnimation { target: splash; property: "opacity"; to: 0; duration: 560; easing.type: Easing.InOutQuad }
            NumberAnimation { target: lights; property: "bloom"; to: 1.6; duration: 560; easing.type: Easing.InCubic }
        }
        ScriptAction { script: splash.dismissed() }
    }
}
