#!/bin/sh

if [ -z "$MAKEFILE_PATH" ]; then
  echo "Makefile path not specifed. Exiting... "
  exit 1
fi

[ ! -z "$DIFF_QUIET" ] && [ "$DIFF_QUIET" -eq 1 ] && diff_add_args="-q"

RED="\033[1;31m"
GREEN="\033[1;32m"
RED_BG="\033[0;41m"
GREEN_BG="\033[0;42m"
NO_COLOR="\033[0m"

signature_files="$(cat $MAKEFILE_PATH | sed -n 's/^.*-o=\(.*\.signature\).*$/\1/p')"

REFERENCE_DIR_SUFF="/../ref/Reference-Spike.signature"

echo "> Veryfing signatures"
target_cnt=0
fail_cnt=0

for sig in $signature_files
do
    ref="$(dirname "$sig")$REFERENCE_DIR_SUFF"
    echo ">> Comparing $sig (TARGET$target_cnt) to $ref"

    diff -b --strip-trailing-cr "$diff_add_args" "$sig" "$ref"
    res=$?

    [ -f "$ref" ] || echo -e "${RED}!${NO_COLOR} Reference signature file not found!"
    [ -f "$sig" ] || echo -e "${RED}!${NO_COLOR} Coreblocks signature file not found! Check signature run logs"
    [ -s "$sig" ] || echo -e "${RED}!${NO_COLOR} Coreblock signature file is empty! Check signature run logs"

    if [ $res = 0 ]
    then
        echo -e "${GREEN}[PASS] Signature verification passed (TARGET$target_cnt)${NO_COLOR}"
    else
        echo -e "${RED}[FAIL] Signature verification failed (TARGET$target_cnt)${NO_COLOR}"
        fail_cnt=$(( $fail_cnt+1 ))
    fi

    target_cnt=$(( $target_cnt+1 ))
done

rc=1
[ $fail_cnt -eq 0 ] && rc=0

bg=${GREEN_BG}
[ $rc = 1 ] && bg=$RED_BG
echo -e "${bg}>>> Compared $target_cnt signatures, FAILED=$fail_cnt, PASSED=$(($target_cnt-$fail_cnt))${NO_COLOR}"
exit $rc
