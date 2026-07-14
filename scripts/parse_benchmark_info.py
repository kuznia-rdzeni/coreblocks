#!/usr/bin/env python3
"""
This script parses the output of the synthesis tool and extracts the
following information:
    - Max clock frequency
    - Number of logic cells used
    - Number of carry cells used
    - Number of RAM cells used
    - Number of DFF cells used
"""

import os
import sys
import re
import json
import argparse


def find_synthesis_information(line, information_to_search):
    """
    Parses the given line for the given keyword and regex.
    Returns the found value if the keyword is found in the line.
    """

    for information in information_to_search:
        kws = [information["keyword"]] if isinstance(information["keyword"], str) else information["keyword"]
        for kw in [kw for kw in kws if kw in line]:
            found_value = re.findall(information["regex"], line)
            if found_value:
                fun = information["update"] if "update" in information else lambda kw, old, new: new
                information.update({"value": fun(kw, information["value"], float(found_value[0]))})
                break


def pick_information_to_search(platform):
    """
    Returns a list of information to search for based on the platform.
    """
    import constants.benchmark_information as information

    if not hasattr(information, platform):
        raise NotImplementedError(f"Platform {platform} is not supported.")

    return getattr(information, platform)


def omit_regex_and_keyword(information_to_search):
    """
    Removes the regex and keyword from the information.
    """

    for information in information_to_search:
        del information["regex"]
        del information["keyword"]
        if "update" in information:
            del information["update"]

    return information_to_search


if __name__ == "__main__":
    parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, parent)

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-p",
        "--platform",
        default="ecp5",
        choices=["ecp5", "xc7a200t"],
        help="Selects platform to collect information from. Default: %(default)s",
    )
    parser.add_argument(
        "-i",
        "--input",
        default="./build/top.tim",
        help="Selects input file to read information from. Default: %(default)s",
    )
    parser.add_argument(
        "-o",
        "--output",
        default="benchmark.json",
        help="Selects output file to write information to. Default: %(default)s",
    )

    args = parser.parse_args()

    information_to_search = pick_information_to_search(args.platform)

    with open(args.input, "r") as synth_info_file:
        for line in synth_info_file:
            find_synthesis_information(line, information_to_search)

    with open(args.output, "w") as benchmark_file:
        json.dump(omit_regex_and_keyword(information_to_search), benchmark_file, indent=4)
