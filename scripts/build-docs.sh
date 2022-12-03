#!/bin/bash
sphinx-apidoc -o docs coreblocks/
sphinx-build -M html docs/ build/