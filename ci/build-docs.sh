#!/bin/bash
if [ -z "$DOCS_DIR" ] || [ -z "$BUILD_DIR" ]; then
  echo "Documentation or build directory not specified. Exiting... "
  exit 1
fi

scripts/build-docs.sh -d "$DOCS_DIR" -o "$BUILD_DIR"
