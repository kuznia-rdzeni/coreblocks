#!/bin/bash
# Add coreblocks to PYTHONPATH for sphinx-apidoc
export PYTHONPATH=$PYTHONPATH:$PWD
sphinx-apidoc -o docs coreblocks/
sphinx-build -M html docs/ build/