# Windows x64 console ONEFILE; the proven launcher and runtime remain unchanged.
from pathlib import Path
import shutil
import sys

root = Path(SPECPATH).parent
sys.path.insert(0, SPECPATH)
from build_support import notice_data, version_info, validate_build_environment
validate_build_environment(root)
notices = notice_data(root)
analysis = Analysis(
    [str(root / "packaging/launcher.py")],
    pathex=[str(root)], binaries=[],
    datas=notices + [(str(root / "packaging/THIRD_PARTY_NOTICES.md"), ".")],
    # Same two native dynamic imports proved necessary in the ONEDIR build.
    hiddenimports=["win32timezone", "win32com"],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(analysis.pure)
icon = root / "assets/pixelport.ico"
exe = EXE(
    pyz, analysis.scripts, analysis.binaries, analysis.datas, [], name="PixelPort",
    debug=False, bootloader_ignore_signals=False, strip=False, upx=False,
    console=True, version=version_info(root), icon=str(icon) if icon.is_file() else None,
)
# Readable companion notices; also embedded so copying the EXE preserves them.
for source, destination in notices:
    folder = Path(DISTPATH) / destination
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, folder)
shutil.copy2(root / "LICENSE", Path(DISTPATH) / "LICENSE")
shutil.copy2(root / "packaging/THIRD_PARTY_NOTICES.md", Path(DISTPATH) / "THIRD_PARTY_NOTICES.md")
