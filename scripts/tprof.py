#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path
from typing import Optional
from collections.abc import Iterable
from tabulate import tabulate
from dataclasses import astuple

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))


from transactron.profiler import Profile, RunStatNode  # noqa: E402


def process_stat_tree(
    xs: Iterable[RunStatNode], recursive: bool, ret: Optional[list[tuple]] = None, depth=0
) -> list[tuple]:
    if ret is None:
        ret = list[tuple]()
    for x in xs:
        row = astuple(x.stat)
        if recursive:
            row = (depth * "-",) + row
        ret.append(row)
        if recursive and x.callers:
            process_stat_tree(x.callers.values(), recursive, ret, depth + 1)
    return ret


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_name", nargs=1)

    args = parser.parse_args()

    profile = Profile.decode(args.file_name[0])

    recursive = True

    methods = profile.analyze_methods(recursive=recursive)

    headers = ["name", "source location", "locked", "run"]
    if recursive:
        headers = [""] + headers

    print(tabulate(process_stat_tree(methods, recursive), headers=headers))


if __name__ == "__main__":
    main()
