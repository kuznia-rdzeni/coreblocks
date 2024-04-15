#!/usr/bin/env python3

import argparse
import json
import tabulate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--precision", type=int, required=True, action="store", help="Precision of printed values")
    parser.add_argument("results", nargs=1)
    parser.add_argument("baseline_results", nargs=1)

    args = parser.parse_args()

    with open(args.results[0], "r") as f:
        results = {entry["name"]: entry["value"] for entry in json.load(f)}

    try:
        with open(args.baseline_results[0], "r") as f:
            baseline_results = {entry["name"]: entry["value"] for entry in json.load(f)}
    except FileNotFoundError:
        baseline_results: dict[str, float] = {}

    keys = sorted(list(results.keys()))
    values: list[str] = []
    for key in keys:
        emoji = ""
        val_str = f"{results[key]:.{args.precision}f}"

        diff_str = ""
        if key in baseline_results:
            diff = results[key] - baseline_results[key]

            emoji = ""
            sign = ""
            if diff > 0:
                emoji = "🔺 "
                sign = "+"
            elif diff < 0:
                emoji = "🔻 "
                sign = "-"

            diff_str = f" ({sign}{abs(diff):.{args.precision}f})"

        values.append(emoji + val_str + diff_str)

    print(tabulate.tabulate([values], headers=keys, tablefmt="github"))


if __name__ == "__main__":
    main()
