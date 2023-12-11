# Synthesis

CoreBlocks synthesizes `Core` circuit to test how many resources it consumes as the project
grows and more functionalities are added.

## Documentation

### Requirements

In order to perform synthesis you will need to install following tools:
  * [yosys](https://github.com/YosysHQ/yosys)
  * [prjtrellis](https://github.com/YosysHQ/prjtrellis)
  * [nextpnr-ecp5](https://github.com/YosysHQ/nextpnr.git)

These tools may need manual compilation from git repository, that can take some time.

You can use docker images that have installed all required tools to perform synthesis:
  * [vuush/amaranth-synth:ecp5](https://hub.docker.com/r/vuush/amaranth-synth/tags)

To build the `AmaranthSynthECP5.Dockerfile` yourself use following command:
```
docker build --platform linux/amd64 -t "amaranth-synth:ecp5" -f ./docker/AmaranthSynthECP5.Dockerfile .
```

### Usage

Script named `synthesize.py` is used to perform the `Core` synthesis.

Example usage:
```
./scripts/synthesize.py --help
./scripts/synthesize.py --platform ecp5 --verbose
```

To collect synthesis information we use script named `parse_benchmark_info.py`.

This script parses the output of the synthesis tool and extracts the
following information:
  - Max clock frequency
  - Number of logic cells used
  - Number of carry cells used
  - Number of RAM cells used
  - Number of DFF cells used

## Benchmarks

For each commit on `master` branch, CI runs the synthesis and saves the parameters collected by `parse_benchmark_info` script.

Graphs generated from this information are available on a dedicated [subpage](https://kuznia-rdzeni.github.io/coreblocks/dev/benchmark/).
