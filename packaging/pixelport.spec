# Windows x64 console ONEDIR. Run from the repository root; no custom runtime hooks.
from pathlib import Path
import shutil
import sys

root = Path(SPECPATH).parent
sys.path.insert(0, SPECPATH)
from build_support import notice_data, version_info, validate_build_environment
validate_build_environment(root)

analysis = Analysis(
    [str(root / "packaging/launcher.py")],
    pathex=[str(root)], binaries=[], datas=notice_data(root),
    # Frozen probes proved dynamic native imports: process times need win32timezone; COM needs win32com.
    hiddenimports=["win32timezone", "win32com"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(analysis.pure)
icon = root / "assets/pixelport.ico"
exe = EXE(
    pyz, analysis.scripts, [], exclude_binaries=True, name="PixelPort",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, version=version_info(root), icon=str(icon),
    contents_directory="_internal",
)
bundle = COLLECT(exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="PixelPort")
shutil.copy2(root / "LICENSE", Path(DISTPATH) / "PixelPort/LICENSE")
shutil.copy2(root / "packaging/THIRD_PARTY_NOTICES.md", Path(DISTPATH) / "PixelPort/THIRD_PARTY_NOTICES.md")
