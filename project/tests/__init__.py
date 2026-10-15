"""Pixel Loom validation."""


async def cleanup_runtime(folder):
    """Wait for a stopped detached backend to release its test-only directory."""
    import asyncio
    from pathlib import Path
    import shutil
    import tempfile

    root = Path(folder).resolve()
    if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith("pixel-loom-"):
        raise AssertionError("Only this test's temporary runtime may be removed")
    deadline = asyncio.get_running_loop().time() + 10
    while root.exists():
        try:
            shutil.rmtree(root)
        except PermissionError:
            if asyncio.get_running_loop().time() >= deadline:
                raise
            await asyncio.sleep(.1)
