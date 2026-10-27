#!/bin/bash
set -ex

##
## Create some aliases
##
echo 'alias ll="ls -alF"' >> $HOME/.bashrc
echo 'alias la="ls -A"' >> $HOME/.bashrc
echo 'alias l="ls -CF"' >> $HOME/.bashrc

# Convenience workspace directory for later use
WORKSPACE_DIR=$(pwd)

# The venv lands in .venv via poetry.toml
# Now install all dependencies
poetry install

# Sphinx toolchain for the docs container build
pip install -r docs/requirements.txt

echo "Done!"
