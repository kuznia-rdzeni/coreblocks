#!/usr/bin/env python3

import argparse
import json
import tabulate
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--precision", type=int, default=0, help="Precision of printed values")
    parser.add_argument("--results-dir", default=".", help="Directory containing result files")
    parser.add_argument("--baseline-dir", help="Directory containing baseline results")
    parser.add_argument("--results", nargs=2, action="append", required=True)

    args = parser.parse_args()

    table = []
    keys: list[str] = []
    for results_name, results_file in args.results:
        with open(os.path.join(args.results_dir, results_file), "r") as f:
            results = {entry["name"]: entry["value"] for entry in json.load(f)}

        baseline_results: dict[str, float] = {}
        try:
            if args.baseline_dir:
                with open(os.path.join(args.baseline_dir, results_file), "r") as f:
                    baseline_results = {entry["name"]: entry["value"] for entry in json.load(f)}
        except FileNotFoundError:
            pass

        old_keys = keys
        keys = sorted(list(results.keys()))
        if old_keys:
            assert keys == old_keys

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
                    emoji = "▲ "
                    sign = "+"
                elif diff < 0:
                    emoji = "▼ "
                    sign = "-"

                diff_str = f" ({sign}{abs(diff):.{args.precision}f})"

            values.append(emoji + val_str + diff_str)

        table.append([results_name] + values)

    headers = ["config"] + keys

    if len(args.results) == 1:
        headers.pop(0)
        for row in table:
            row.pop(0)

    print(tabulate.tabulate(table, headers=headers, tablefmt="github"))


if __name__ == "__main__":
    main()
