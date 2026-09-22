# @borgstrom's Woodworking repo

This repo uses build123d to model woodworking projects

## Setup

The `Pipfile` describes the required Python environment, so you'll need `pipenv` installed. @borgstrom has a venv in `~/.venv/` for it (`python3 -m venv ~/.venv/pipenv`) and then links `~/.venv/pipenv/bin/pipenv` into `~/bin/` so it's in the Python.

It is recommended to use `pyenv` to manage python versions so that you can match the version describe in the `Pipfile` and `.python-version`.

With the correct version of Python available and pipenv installed you can run `pipenv install` to set up all the required modules.

## Viewing models

Install the OCP Cad Viewer VSCode extension, then "Start Debugging (F5)" in vscode on a model.

The model will render in the viewer and auto-reload as you make changes.
