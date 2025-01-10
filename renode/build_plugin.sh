#!/bin/sh
# Usage: renode/build_plugin.sh [--trace] core.v

set -e

ORIGIN=$(dirname "$0")

if [ -z "$RENODE_ROOT" ]; then
  echo "RENODE_ROOT not set; trying to guess from PATH"
  RENODE_ROOT=$(renode --disable-gui --console -e 'python "import os;print(os.getcwd());os._exit(0)"' |tail -1)
fi
COSIM_DIR="$(find "$RENODE_ROOT" -name '*integration-library.cmake')"
COSIM_DIR="${COSIM_DIR%/*}"

CSOURCES=$(find "$COSIM_DIR" -name '*.cpp' | grep -v renode_cfu |grep -v buses)

# official way to build involves some crazy cmake, but let's just use verilator cli
verilator -j 0 -Wno-lint --cc --build --lib-create Vcoreblocks $CSOURCES "$ORIGIN/sim_main.cpp" "$ORIGIN/sim_coreblocks.cpp" -CFLAGS -I"$COSIM_DIR" "$@"
