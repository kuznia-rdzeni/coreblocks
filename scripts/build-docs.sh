#!/bin/bash

set -e

ROOT_PATH=$(dirname $0)/..

# Add coreblocks to PYTHONPATH for sphinx-apidoc
export PYTHONPATH=$PYTHONPATH:$ROOT_PATH
DOCS_DIR=$ROOT_PATH/"docs"
BUILD_DIR=$ROOT_PATH/"build"
CLEAN=false

function print_help() {
  echo "Usage: $0 [-c] [-h] [-o output_dir] [-d docs_dir]"
  echo ""
  echo "-h                                Show this help message."
  echo "-c                                Clean the documentation build."
  echo "-o                                Custom output directory. (Default: build)"
  echo "-d                                Custom documentation directory. (Default: docs)"
}

while getopts "cho:d:" opt
do
  case $opt in
    h)
      print_help
      exit 0
      ;;
    c)
      CLEAN=true
      ;;
    d)
      DOCS_DIR=$ROOT_PATH/$OPTARG
      ;;
    o)
      BUILD_DIR=$ROOT_PATH/$OPTARG
      ;;
    :)
      print_help
      exit 1
      ;;
    \?)
      print_help
      exit 1
      ;;
  esac
done

# Clean the documentation build and exit
if $CLEAN
then
# Remove output build directory.
    rm -frd $BUILD_DIR
# Remove sphinx-apidoc generated files.
    rm -f $DOCS_DIR/*.rst
    exit 0
fi

$ROOT_PATH/scripts/core_graph -p -f mermaid $DOCS_DIR/auto_graph.rst
sed -i -e '1i\.. mermaid::\n' -e 's/^/   /' $DOCS_DIR/auto_graph.rst

sphinx-apidoc -o $DOCS_DIR $ROOT_PATH/coreblocks/
sphinx-build -b html -W $DOCS_DIR $BUILD_DIR
