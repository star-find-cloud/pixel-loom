"""Compatibility entry: the smoke test now uses an isolated temporary backend."""
import asyncio
from tests.mcp_public_smoke import run

if __name__ == "__main__":
    asyncio.run(run())
