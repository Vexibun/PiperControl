#!/usr/bin/env python3
import sys


def main():
    if "--help" in sys.argv or "-h" in sys.argv:
        print("Usage: python3 main.py [--port=<port>]")
        return

    port = 8080
    for arg in sys.argv[1:]:
        if arg.startswith("--port="):
            try:
                port = int(arg.split("=", 1)[1])
            except ValueError:
                pass

    from browser_ui import BrowserApp
    print("Starting Piper Browser Control...")
    app = BrowserApp(port=port)
    app.run()


if __name__ == "__main__":
    main()
