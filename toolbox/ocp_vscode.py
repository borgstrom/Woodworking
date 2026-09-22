import subprocess
import sys
from pathlib import Path

from watchfiles import watch

from ocp_vscode import show


def show_with_autoreload_in_vscode(*args, **kwargs):
    """
    When run from within a VSCode debugging session this will invoke show_with_autoreload.

    Otherwise it does nothing.
    """
    if "debugpy" in sys.modules:
        show_with_autoreload(*args, **kwargs)


def show_with_autoreload(*args, **kwargs):
    """
    This overloads the `show` function from `ocp_vscode` to add automatic reloading when files change.
    """
    try:
        if sys.argv[1] == "show":
            print("Sending objects to CAD viewer")
            show(*args, **kwargs)
    except IndexError:
        show(*args, **kwargs)
        try:
            path = Path(__file__).parent.parent
            print(f"Watching for file changes in {path}... CTRL+C to exit")
            for _ in watch(path, debounce=500):
                subprocess.run([sys.executable, sys.argv[0], "show"])
        except KeyboardInterrupt:
            pass
