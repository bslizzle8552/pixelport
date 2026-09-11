import sys


def main():
    if sys.platform != "win32":
        print("GPTSnip requires Windows 11.", file=sys.stderr)
        return 1
    from .app import run
    return run()


if __name__ == "__main__":
    raise SystemExit(main())
