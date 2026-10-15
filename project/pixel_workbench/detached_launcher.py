"""Release the GUI from the lifetime of a particular MCP host process."""
import os
import subprocess
import sys

from .paths import WORKSPACE, RUNTIME


def main():
    RUNTIME.mkdir(exist_ok=True)
    headless = os.environ.get("PIXEL_LOOM_HEADLESS") == "1"
    if os.name == "nt":
        # MCP SDKs can put servers into a kill-on-close Windows Job that forbids
        # breakaway. Ask the existing desktop shell to own this independent app.
        import win32com.client
        from pathlib import Path
        frozen = getattr(sys, "frozen", False)
        if frozen:
            name = "PixelLoomMCP.exe" if headless else "PixelLoom.exe"
            interpreter = Path(sys.executable).with_name(name)
        else:
            interpreter = Path(sys.executable).with_name("pythonw.exe")
        arguments = [] if frozen else ["-m", "pixel_workbench"]
        if headless:
            arguments.append("--headless")
        # Explorer does not inherit this MCP child's environment; pass instance
        # paths explicitly so isolated workspaces stay isolated after launch.
        from .paths import DATA_HOME
        arguments += ["--data-dir", str(DATA_HOME), "--workspace", str(WORKSPACE)]
        parameters = subprocess.list2cmdline(arguments)
        import pythoncom
        windows = win32com.client.Dispatch("Shell.Application").Windows()
        candidates = []
        try:
            # VT_UI4 / SWC_DESKTOP obtains the desktop even when no folder
            # windows are open. Its Document.Application lives in Explorer.
            candidates.append(windows.Item(win32com.client.VARIANT(pythoncom.VT_UI4, 8)))
        except Exception:
            pass
        candidates.extend(windows)
        for window in candidates:
            try:
                # Obtain the automation object hosted by the existing Explorer
                # process; a fresh Shell.Application object lives in our job.
                application = window.Document.Application
                application.ShellExecute(str(interpreter), parameters, str(WORKSPACE), "open", 0 if headless else 1)
                return
            except Exception:
                continue
        raise RuntimeError("The Windows desktop shell is unavailable; open the workbench manually before connecting MCP")
    with (RUNTIME / "editor.log").open("a", encoding="utf-8") as log:
        options = dict(cwd=WORKSPACE, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                       close_fds=True, start_new_session=True)
        subprocess.Popen([sys.executable, "-m", "pixel_workbench", *(["--headless"] if headless else [])], **options)


if __name__ == "__main__":
    main()
