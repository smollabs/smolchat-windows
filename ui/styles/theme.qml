pragma Singleton
import QtQuick

// Design tokens for smolchat: neutral greys, one user-selectable accent and
// System typography. `dark` and `accentName` are bound in main.qml.
QtObject {
    id: theme

    property bool dark: true
    property string accentName: "violet"

    // Accent palette (dark-mode tone, light-mode tone)
    readonly property var accents: ({
        "blue":     { dark: "#5b9dff", light: "#0a66e4", label: "Blue" },
        "violet":   { dark: "#ad66f5", light: "#7b3fe0", label: "Violet" },
        "green":    { dark: "#4ade80", light: "#15803d", label: "Green" },
        "orange":   { dark: "#fb923c", light: "#ea580c", label: "Orange" },
        "pink":     { dark: "#f472b6", light: "#db2777", label: "Pink" },
        "graphite": { dark: "#a1a1aa", light: "#52525b", label: "Graphite" }
    })
    readonly property var accentKeys: ["blue", "violet", "green", "orange", "pink", "graphite"]
    function accentColor(name, isDark) {
        const a = accents[name] || accents["blue"]
        return isDark ? a.dark : a.light
    }

    // Frame & glossy panel
    readonly property color frame:         dark ? "#04030b" : "#eeebf5"
    readonly property color panel:         dark ? "#0a0817" : "#fcfbff"
    readonly property color panelEdge:     dark ? "#1cffffff" : "#14000000"
    readonly property real  glowStrength:  dark ? 0.40 : 0.18
    readonly property color glassFill:     dark ? "#130f22" : "#ffffff"
    readonly property color glassFillHover: dark ? "#1a1530" : "#f7f3ff"
    readonly property color glassEdgeTop:  dark ? "#33ffffff" : "#1c000000"
    readonly property color glassEdgeBottom: dark ? "#0dffffff" : "#0d000000"
    readonly property color glassSheen:    dark ? "#0affffff" : "#00ffffff"

    // Surfaces
    readonly property color bg:            panel
    readonly property color sidebar:       frame
    readonly property color surface:       dark ? "#29292c" : "#f3f3f5"
    readonly property color surfaceRaised: dark ? "#2f2f33" : "#ffffff"
    readonly property color popup:         dark ? "#110d1e" : "#ffffff"
    readonly property color userBubble:    dark ? "#1c1533" : "#f0eafc"
    readonly property color codeBg:        dark ? "#07050f" : "#f7f5fc"
    readonly property color codeHeader:    dark ? "#120e20" : "#efebf8"
    readonly property color hover:         dark ? "#14ffffff" : "#0b000000"
    readonly property color hoverStrong:   dark ? "#22ffffff" : "#14000000"
    readonly property color selected:      dark ? "#2a2a2e" : "#ebebee"
    readonly property color overlay:       dark ? "#a6000000" : "#4d000000"
    readonly property color shadow:        dark ? "#80000000" : "#26000000"
    readonly property color splashBg:      "#0e0e10"

    // Lines
    readonly property color border:        dark ? "#2effffff" : "#1f000000"
    readonly property color borderSubtle:  dark ? "#17ffffff" : "#12000000"

    // Text
    readonly property color text:          dark ? "#ececf1" : "#0f0f12"
    readonly property color textSecondary: dark ? "#b4b4bb" : "#55555d"
    readonly property color textTertiary:  dark ? "#85858e" : "#8e8e96"
    readonly property color textOnAccent:  "#ffffff"
    readonly property color textOnPrimary: dark ? "#0f0f12" : "#ffffff"

    // Accents
    readonly property color brand:         accentColor(accentName, dark)
    readonly property color brandSoft:     Qt.rgba(brand.r, brand.g, brand.b, dark ? 0.16 : 0.10)
    readonly property color brandDeep:     Qt.darker(brand, 2.4)
    // Warm secondary colours taken from the mascot's flame.
    readonly property color flame:         "#f57a12"
    readonly property color flameLight:    "#fde38a"
    readonly property color brandGlow:     Qt.rgba(brand.r, brand.g, brand.b, dark ? 0.35 : 0.25)
    readonly property color accent:        dark ? "#ececf1" : "#0f0f12"   // neutral primary buttons
    readonly property color accentMuted:   dark ? "#4a4a50" : "#d4d4d8"
    readonly property color success:       dark ? "#4ade80" : "#16a34a"
    readonly property color warning:       dark ? "#fbbf24" : "#b45309"
    readonly property color danger:        dark ? "#f87171" : "#dc2626"
    readonly property color dangerBg:      dark ? "#2a1717" : "#fdeeee"

    // Typography
    readonly property string fontFamily: "Segoe UI"
    readonly property string monoFamily: "Consolas"
    readonly property int fontXs: 11
    readonly property int fontSm: 12
    readonly property int fontMd: 14
    readonly property int fontLg: 16
    readonly property int fontXl: 22
    readonly property int fontHero: 30

    // Shape & spacing
    readonly property int radiusSm: 6
    readonly property int radiusMd: 10
    readonly property int radiusLg: 16
    readonly property int radiusXl: 26
    readonly property int contentWidth: 768
    readonly property int sidebarWidth: 264
    // Space reserved for native window controls when content fills the title bar.
    readonly property int titleBarHeight: 52
    readonly property int trafficLightsInset: Qt.platform.os === "osx" ? 78 : 18

    // Motion
    readonly property int fast: 140
    readonly property int normal: 220
    readonly property int slow: 380
    readonly property int easing: Easing.OutCubic
}
