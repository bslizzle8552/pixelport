"""Frozen console entry point. Keep worker diversion before application imports."""

from multiprocessing import freeze_support


if __name__ == "__main__":
    freeze_support()

    import sys
    import traceback

    try:
        from gptsnip.__main__ import main
        code = main()
    except Exception:
        traceback.print_exc()
        code = 1
    if code and sys.stdin is not None and sys.stdin.isatty():
        try:
            input("PixelPort did not start. Review the message above. Press Enter to close...")
        except (EOFError, KeyboardInterrupt):
            pass
    raise SystemExit(code)
