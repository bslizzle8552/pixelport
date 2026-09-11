# PixelPort distribution notices

PixelPort is distributed under the MIT license in LICENSE. Dependencies retain
their own terms. The onedir bundle includes upstream notices under
`_internal/notices/`; the onefile candidate embeds them and provides a readable
companion `notices/` directory. Keep the supplied notices and this file with the
distribution.

- Python 3.14.3: Python Software Foundation license and historical/included-component
  terms, reproduced from the Windows interpreter's LICENSE.txt.
- Pillow 12.3.0: PIL/Pillow terms and bundled codec/library notices from the installed
  Windows wheel's complete LICENSE file.
- pywin32 312: upstream Windows and COM redistribution notices, with the wheel's
  additional license material retained unmodified.
- OpenSSL 3.0.18 and zlib 1.3.1: upstream license texts for the DLLs collected
  with the Python standard-library extensions. No networking behavior is added
  by bundling these standard-library dependencies.
- Tcl/Tk 8.6.15: upstream license.terms for Tcl and the installed Tk scripts.
- PyInstaller 6.22.2: COPYING.txt includes the bootloader exception, GPL text, and
  Apache 2.0 runtime-hook terms. The unmodified embedded bootloader/loader is covered
  by the exception; runtime hooks retain their upstream license. PixelPort is not
  relicensed to GPL merely because it is bundled by PyInstaller.

Build-only tooling is not intentionally distributed as application code. Windows
system libraries are provided by Windows, not copied into this bundle. Bundled
Microsoft runtime files retain their vendor notices and terms. No affiliation
with OpenAI or endorsement by dependency authors is claimed.
