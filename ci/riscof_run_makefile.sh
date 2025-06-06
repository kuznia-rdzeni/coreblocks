#!/bin/sh

if [ -z "$MAKEFILE_PATH" ]; then
  echo "Makefile path not specified. Exiting... "
  exit 1
fi

[ -z "$NPROC" ] && NPROC=$(nproc)

target_cnt=$(cat $MAKEFILE_PATH | grep TARGET | tail -n 1 | tr -d -c 0-9)

echo "> Running for $target_cnt Makefile targets"

targets=""

for i in $(seq 0 $target_cnt)
do
    targets="$targets TARGET$i"
done

echo "Starting for targets: $targets"
make -f $MAKEFILE_PATH -i -j $NPROC $targets
