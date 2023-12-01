FROM ubuntu:23.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    python3.11 python3-pip python3.11-venv git yosys lsb-release \
    build-essential cmake python3-dev libboost-all-dev libeigen3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install prjtrellis
RUN git clone --recursive \
    https://github.com/YosysHQ/prjtrellis.git \
    prjtrellis && \
    cd prjtrellis && \
    git checkout 35f5affe10a2995bdace49e23fcbafb5723c5347
RUN cd prjtrellis && \
    cd libtrellis && \
    cmake -DCMAKE_INSTALL_PREFIX=/usr/local . && \
    make -j$(nproc) && \
    make install && \
    make clean

# Install nexpnr-ecp5
RUN git clone \
    https://github.com/YosysHQ/nextpnr/ \
    nextpnr && \
    cd nextpnr && \
    git checkout b5d30c73877be032c1d87cd820ebdfe4db556fdb
RUN cd nextpnr && \
    cmake . -DARCH=ecp5 -DTRELLIS_INSTALL_PREFIX=/usr/local && \
    make -j$(nproc) && \
    make install && \
    make clean
