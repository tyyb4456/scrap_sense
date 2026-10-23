"""Event-loop factory that keeps async psycopg working on Windows."""

from __future__ import annotations

import asyncio


def selector_loop_factory(use_subprocess: bool = False) -> type[asyncio.AbstractEventLoop]:
    """Uvicorn loop factory compatible with psycopg's async connections."""
    _ = use_subprocess
    return asyncio.SelectorEventLoop
