# -*- mode: python ; coding: utf-8 -*-
# Especificación PyInstaller única para Windows (.exe de un solo archivo) y macOS (.app)
import re
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

APP = "ImagenLigera"
FIRMA = "Diseñado por Olivier Melín · tecmad.es"
VERSION = re.search(r'__version__ = "(.+?)"',
                    Path("imagenligera/__init__.py").read_text(encoding="utf-8")).group(1)
MAC = sys.platform == "darwin"

datas = [("assets/icon.png", "assets")]
binaries, hiddenimports = [], []
try:  # soporte HEIC (fotos de iPhone)
    d, b, h = collect_all("pillow_heif")
    datas += d; binaries += b; hiddenimports += h
except Exception:
    pass

a = Analysis(
    ["main.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "unittest", "pydoc", "test"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if MAC:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=APP,
              console=False, upx=False, icon="assets/icon.icns")
    coll = COLLECT(exe, a.binaries, a.datas, name=APP, upx=False)
    app = BUNDLE(
        coll,
        name=f"{APP}.app",
        icon="assets/icon.icns",
        bundle_identifier="es.tecmad.imagenligera",
        version=VERSION,
        info_plist={
            "CFBundleDisplayName": APP,
            "CFBundleShortVersionString": VERSION,
            "CFBundleVersion": VERSION,
            "NSHumanReadableCopyright": FIRMA,
            "NSHighResolutionCapable": True,
        },
    )
elif sys.platform == "win32":
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct,
        VSVersionInfo,
    )
    nums = tuple(int(x) for x in (VERSION.split(".") + ["0", "0", "0"])[:4])
    info = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[
            StringFileInfo([StringTable("0C0A04B0", [
                StringStruct("CompanyName", "tecmad.es"),
                StringStruct("FileDescription", "ImagenLigera - compresor de imágenes para web"),
                StringStruct("FileVersion", VERSION),
                StringStruct("InternalName", APP),
                StringStruct("LegalCopyright", FIRMA),
                StringStruct("OriginalFilename", f"{APP}.exe"),
                StringStruct("ProductName", APP),
                StringStruct("ProductVersion", VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0C0A, 1200])]),
        ],
    )
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=APP,
              console=False, upx=False, icon="assets/icon.ico", version=info)
else:  # Linux (también funciona)
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=APP, console=False, upx=False)
