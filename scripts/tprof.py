#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path

topdir = Path(__file__).parent.parent
sys.path.insert(0, str(topdir))


from transactron.profiler import Profile  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("file_name", nargs=1)

    args = parser.parse_args()

    profile = Profile.decode(args.file_name[0])

    print(profile)


if __name__ == "__main__":
    main()
