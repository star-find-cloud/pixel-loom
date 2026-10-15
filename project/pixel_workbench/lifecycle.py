from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import time

from . import __version__
from .paths import RUNTIME, WORKSPACE, prepare
from .cli import Client


class StartupBusy(RuntimeError):
    pass


def live_client():
    try:
        client = Client()
        state = client.request("/health", timeout=2)
    except (RuntimeError, OSError, ValueError):
        return None
    if state.get("version") != __version__:
        raise RuntimeError("A different Pixel Loom version is running. Save and close that window before starting this version.")
    return client


@contextlib.contextmanager
def startup_lock(timeout=20, lock_name="startup.lock"):
    """Cross-process lock, so several MCP hosts don't spawn duplicate editors."""
    RUNTIME.mkdir(parents=True, exist_ok=True)
    handle = (RUNTIME / lock_name).open("a+b")
    handle.seek(0)
    handle.write(b"0")
    handle.flush()
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except (OSError, BlockingIOError):
            if time.monotonic() > deadline:
                handle.close()
                raise StartupBusy("Another client is starting the editor; retry shortly")
            time.sleep(0.1)
    try:
        yield
    finally:
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


def ensure_editor():
    prepare()
    client = live_client()
    if client:
        return client
    with startup_lock():
        client = live_client()
        if client:
            return client
        with (RUNTIME / "editor.log").open("a", encoding="utf-8") as log:
            # A short-lived launcher makes the GUI independent of a client's
            # process tree. MCP hosts may terminate their entire server subtree.
            command = [sys.executable, "--launch-backend"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "pixel_workbench.detached_launcher"]
            process = subprocess.Popen(command, cwd=WORKSPACE,
                                       stdout=log, stderr=log, stdin=subprocess.DEVNULL,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        process.wait(timeout=8)
        if process.returncode:
            raise RuntimeError("Editor launcher failed; see .runtime/editor.log")
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            client = live_client()
            if client:
                return client
            time.sleep(0.15)
        raise RuntimeError("Editor startup timed out; see .runtime/editor.log")
