# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir specification for the Windows MVP helper.

The first packaging gate intentionally uses onedir rather than onefile so native
Matrix E2EE dependencies remain inspectable and every helper launch avoids a
fresh self-extraction step. A onefile build is a later optimization after this
shape has been validated on a clean Windows target.
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_all

repo_root = Path(SPECPATH).parents[1]
entrypoint = repo_root / "packaging" / "windows" / "helper_entry.py"

# matrix-nio imports a number of optional crypto modules dynamically. Collect
# the package explicitly, and collect vodozemac separately because matrix-nio
# 0.26 moved E2EE from libolm/python-olm to the Rust-backed vodozemac package.
datas = []
binaries = []
hiddenimports = []
for package in ("nio", "vodozemac"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden

analysis = Analysis(
    [str(entrypoint)],
    pathex=[str(repo_root / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="secure-messaging-helper",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="secure-messaging-helper",
)
