#!/bin/bash

set -e

if [ -z "$DOCS_DIR" ] || [ -z "$BUILD_DIR" ]; then
  echo "Documentation or build directory not specified. Exiting... "
  exit 1
fi

scripts/build_docs.sh -d "$DOCS_DIR" -o "$BUILD_DIR"
