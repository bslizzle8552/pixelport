"""Build-time metadata and upstream notice collection; never imported by PixelPort."""

import ast
import platform
from importlib.metadata import version as installed_version
from importlib.metadata import distribution
from pathlib import Path
import sys


def app_version(root):
    module = ast.parse((root / "gptsnip/__init__.py").read_text(encoding="utf-8"))
    return next(ast.literal_eval(n.value) for n in module.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in n.targets))


def version_info(root):
    from PyInstaller.utils.win32.versioninfo import (
        VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
        VarFileInfo, VarStruct,
    )
    version = app_version(root)
    numbers = tuple(map(int, version.split("."))) + (0,)
    return VSVersionInfo(
        ffi=FixedFileInfo(filevers=numbers, prodvers=numbers, mask=0x3F,
                         flags=0, OS=0x40004, fileType=1, subtype=0, date=(0, 0)),
        kids=[StringFileInfo([StringTable("040904B0", [
            StringStruct("ProductName", "PixelPort"),
            StringStruct("FileDescription", "PixelPort"),
            StringStruct("ProductVersion", version),
            StringStruct("FileVersion", version),
            StringStruct("OriginalFilename", "PixelPort.exe"),
        ])]), VarFileInfo([VarStruct("Translation", [1033, 1200])])],
    )


def notice_data(root):
    # The actual installed wheel licenses include Pillow's bundled codec notices.
    items = [(str(root / "LICENSE"), "notices/PixelPort"),
             (str(Path(sys.base_prefix) / "LICENSE.txt"), "notices/Python"),
             (str(Path(sys.base_prefix) / "tcl/tk8.6/license.terms"), "notices/Tk"),
             (str(root / "packaging/licenses/tcl-license.terms"), "notices/Tcl"),
             (str(root / "packaging/licenses/openssl-LICENSE.txt"), "notices/OpenSSL"),
             (str(root / "packaging/licenses/zlib-LICENSE"), "notices/zlib")]
    for name in ("Pillow", "pywin32", "PyInstaller"):
        dist = distribution(name)
        found = []
        for entry in dist.files or ():
            path = Path(str(entry))
            if ".dist-info" in path.parts[0] and "licenses" in path.parts:
                relative = Path(*path.parts[path.parts.index("licenses") + 1:])
                found.append((str(dist.locate_file(entry)),
                              str(Path("notices") / name / relative.parent)))
        if not found:
            raise RuntimeError("Missing distribution notices: " + name)
        items.extend(found)
    for source, _ in items:
        if not Path(source).is_file():
            raise RuntimeError("Required license missing: " + Path(source).name)
    return items


def validate_build_environment(root):
    from packaging.requirements import Requirement
    if platform.python_implementation() != "CPython" or sys.version_info[:3] != (3, 14, 3) or sys.maxsize <= 2**32:
        raise RuntimeError("This accepted build configuration requires CPython 3.14.3 x64")
    for line in (root / "requirements-build.txt").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        if installed_version(requirement.name) not in requirement.specifier:
            raise RuntimeError("Build dependency does not match pin: " + requirement.name)
