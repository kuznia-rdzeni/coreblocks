#!/usr/bin/env python3

import argparse
import sys
import re
from pathlib import Path
from typing import Optional
from collections.abc import Callable, Iterable
from tabulate import tabulate
from dataclasses import asdict

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))


from transactron.profiler import Profile, RunStat, RunStatNode  # noqa: E402


def process_stat_tree(
    xs: Iterable[RunStatNode], recursive: bool, ret: Optional[list[tuple]] = None, depth=0
) -> list[tuple]:
    if ret is None:
        ret = list[tuple]()
    for x in xs:
        row = asdict(x.stat)
        if recursive and depth:
            row["name"] = (2 * depth - 1) * "-" + " " + row["name"]
        ret.append(tuple(row.values()))
        if recursive and x.callers:
            process_stat_tree(x.callers.values(), recursive, ret, depth + 1)
    return ret


def filter_nodes(nodes: list[RunStatNode], key: Callable[[RunStat], str], regex: str):
    pattern = re.compile(regex)
    return [node for node in nodes if pattern.search(key(node.stat))]


def sort_node(node: RunStatNode, sort_order: str):
    node.callers = dict(sorted(node.callers.items(), key=lambda node: asdict(node[1].stat)[sort_order]))
    for node2 in node.callers.values():
        sort_node(node2, sort_order)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("-g", "--call-graph", action="store_true", help="Show call graph")
    parser.add_argument("-s", "--sort", choices=["name", "locked", "run"], default="name", help="Sort by column")
    parser.add_argument(
        "-m", "--mode", choices=["transactions", "methods"], default="transactions", help="Profile display mode"
    )
    parser.add_argument("-f", "--filter-name", help="Filter by name, regular expressions can be used")
    parser.add_argument("-l", "--filter-loc", help="Filter by source location, regular expressions can be used")
    parser.add_argument("file_name", nargs=1)

    args = parser.parse_args()

    profile = Profile.decode(args.file_name[0])

    recursive = args.call_graph

    if args.mode == "transactions":
        nodes = profile.analyze_transactions(recursive=recursive)
    elif args.mode == "methods":
        nodes = profile.analyze_methods(recursive=recursive)
    else:
        assert False

    headers = ["name", "source location", "locked", "run"]

    nodes.sort(key=lambda node: asdict(node.stat)[args.sort])
    for node in nodes:
        sort_node(node, args.sort)

    if args.filter_name:
        nodes = filter_nodes(nodes, lambda stat: stat.name, args.filter_name)
    if args.filter_loc:
        nodes = filter_nodes(nodes, lambda stat: stat.src_loc, args.filter_loc)

    print(tabulate(process_stat_tree(nodes, recursive), headers=headers))


if __name__ == "__main__":
    main()
