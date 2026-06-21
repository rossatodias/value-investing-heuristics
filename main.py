"""Single entry point: starts the web interface (frontend + API on one port)."""

from value_investing_heuristics.web.server import main

if __name__ == "__main__":
    raise SystemExit(main())
