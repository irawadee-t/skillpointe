"""Production entrypoint.

The port is read here, in Python, rather than interpolated into a shell command.
Railway injects PORT at runtime, and a start command written as
``--port $PORT`` only works if something expands it first -- when the platform
exec's the command directly instead of through a shell, uvicorn receives the
literal string "$PORT" and exits with "not a valid integer".

Reading os.environ removes that dependency, so the same entrypoint works
whether it is launched via a shell, exec'd directly, or run as a Docker CMD.
"""
from __future__ import annotations

import os

import uvicorn


def _port() -> int:
    raw = (os.environ.get("PORT") or "").strip()
    if not raw.isdigit():
        # Covers unset, empty, and the un-expanded "$PORT" case.
        return 8000
    return int(raw)


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=_port(),
        timeout_graceful_shutdown=25,
        access_log=False,
    )
