#!/bin/bash

set -e

if [ -z "$DOCS_DIR" ] || [ -z "$BUILD_DIR" ]; then
  echo "Documentation or build directory not specified. Exiting... "
  exit 1
fi

echo "creating build directory"
mkdir -p "$BUILD_DIR"

echo "copying markdown docs and config"
rsync -av "$DOCS_DIR/" "$BUILD_DIR/sources"

echo "generating and building docs"
scripts/build_docs.sh -d "$BUILD_DIR/sources" -o "$BUILD_DIR/html"
