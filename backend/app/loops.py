"""Event-loop factory that keeps async psycopg working on Windows."""

from __future__ import annotations

import asyncio


def selector_loop_factory() -> asyncio.AbstractEventLoop:
    """Return a selector loop compatible with psycopg's async connections."""
    return asyncio.SelectorEventLoop()
