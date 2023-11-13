# Synthesis

CoreBlocks synthesizes `Core` circuit to test how many resources it consumes as the project
grows and more functionalities are added.


## Benchmarks

On each commit to the `master` branch, CI runs the synthesis and saves the parameters collected by the `parse_benchmark_info` script.
The properties collected are:
- IPC
- Fmax
- LUT/RAM usage
The graphs generated from this data are available on a dedicated [benchmark subpage](https://kuznia-rdzeni.github.io/coreblocks/dev/benchmark/).

## Documentation

### Using pre-build container

There is a pre-built container available that is being used in CI. You can
download it and start the synthesis in it locally by executing the following commands:

```bash
sudo docker pull ghcr.io/kuznia-rdzeni/amaranth-synth:ecp5
sudo docker run -it --rm ghcr.io/kuznia-rdzeni/amaranth-synth:ecp5 
git clone --depth=1 https://github.com/kuznia-rdzeni/coreblocks.git
cd coreblocks
python3 -m pip install --upgrade pip
pip3 install -r requirements-dev.txt
PYTHONHASHSEED=0 ./scripts/synthesize.py --verbose --config <your_config>
./scripts/parse_benchmark_info.py
cat benchmark.json
```

### Requirements

In order to perform synthesis without using the ready container you will need to install following tools:
  * [yosys](https://github.com/YosysHQ/yosys)
  * [prjtrellis](https://github.com/YosysHQ/prjtrellis)
  * [nextpnr-ecp5](https://github.com/YosysHQ/nextpnr.git)

These tools may need manual compilation from git repository, that can take some time.

We also provides a dockerfile which can be used to reproduce image used in CI.
To do that, build the `AmaranthSynthECP5.Dockerfile` yourself using following command:
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
