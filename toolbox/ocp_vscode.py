import os
import subprocess
import sys
import time
from pathlib import Path

from watchfiles import watch

from ocp_vscode import show


def show_with_autoreload(*args, **kwargs):
    try:
        if sys.argv[1] == "show":
            print("Sending objects to CAD viewer")
            show(*args, **kwargs)
    except IndexError:
        show(*args, **kwargs)
        try:
            path = Path(__file__).parent.parent
            print(f"Watching for file changes in {path}... CTRL+C to exit")
            for _ in watch(path):
                subprocess.run([sys.executable, sys.argv[0], "show"])
        except KeyboardInterrupt:
            pass
