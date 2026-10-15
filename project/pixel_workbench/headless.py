"""Optional local backend for CI and AI clients without a desktop display."""
import signal
import time

from .bridge import Bridge
from .paths import prepare
from .service import DocumentService


def run_backend():
    prepare()
    service = DocumentService(mode="headless")
    bridge = Bridge()
    def stop(*_):
        service.closing = True
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while not service.closing:
            bridge.pump(service.dispatch)
            time.sleep(.015)
    finally:
        service.autosave()
        bridge.close()


def main():
    from .lifecycle import live_client, startup_lock
    prepare()
    if live_client():
        return
    with startup_lock(timeout=.1, lock_name="editor.lock"):
        if not live_client():
            run_backend()


if __name__ == "__main__":
    main()
