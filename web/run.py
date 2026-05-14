"""
Development entrypoint for the TraceBi web API.

    python web/run.py            # default port 8000, hot-reload on
    python web/run.py --port 9000

Production (e.g. Docker):
    uvicorn web.api.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

import argparse
import sys
import os

# Ensure the repo root is on sys.path so `import web` and `import tracebi` work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description="TraceBi API dev server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-reload", action="store_true")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required:  pip install uvicorn")
        sys.exit(1)

    uvicorn.run(
        "web.api.main:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
    )


if __name__ == "__main__":
    main()
