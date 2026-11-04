# PyInstaller spec for Windows. Model weights are downloaded at runtime.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

root = Path(SPECPATH).parent

a = Analysis(
    [str(root / "main.py")],
    pathex=[str(root)],
    binaries=collect_dynamic_libs("llama_cpp"),
    datas=[
        (str(root / "ui"), "ui"),
        (str(root / "resources"), "resources"),
        *collect_data_files("llama_cpp"),
    ],
    hiddenimports=["PySide6.QtSvg", "PySide6.QtQuickControls2"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="smolchat",
    console=False,
    icon=str(root / "resources" / "assets" / "smolchat.ico")
    if (root / "resources" / "assets" / "smolchat.ico").exists()
    else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="smolchat")
