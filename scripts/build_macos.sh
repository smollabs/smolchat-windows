#!/usr/bin/env bash
# Build smolchat.app (Apple Silicon) into dist/. Requires the project venv.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PYTHON:-.venv/bin/python}

# App icon (.icns) from the brand logo using macOS built-in tools.
LOGO=resources/assets/logo/logo-1254.png
if [ ! -f resources/assets/smolchat.icns ] || [ "$LOGO" -nt resources/assets/smolchat.icns ]; then
  ICONSET=$(mktemp -d)/smolchat.iconset
  mkdir -p "$ICONSET"
  for s in 16 32 128 256 512; do
    sips -z $s $s "$LOGO" --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
    sips -z $((s * 2)) $((s * 2)) "$LOGO" --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
  done
  iconutil -c icns "$ICONSET" -o resources/assets/smolchat.icns
fi

"$PY" -m pip install --quiet "pyinstaller>=6.10"
"$PY" -m PyInstaller packaging/smolchat.spec --noconfirm --distpath dist --workpath build
echo "Built dist/smolchat.app"
echo "For distribution: codesign --deep --options runtime -s 'Developer ID Application: …' dist/smolchat.app, then notarize with xcrun notarytool."
