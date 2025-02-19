FROM ubuntu:24.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    git yosys lsb-release ca-certificates \
    build-essential cmake python3-dev libboost-all-dev libeigen3-dev && \
    rm -rf /var/lib/apt/lists/*

# Install prjtrellis
RUN git clone --recursive --shallow-since=2025.01.01 \
    https://github.com/YosysHQ/prjtrellis.git \
    prjtrellis && \
    cd prjtrellis && \
    git checkout 14ac883fa639b11fdc98f3cdef87a5d01f79e73d
RUN cd prjtrellis && \
    cd libtrellis && \
    cmake -DCMAKE_INSTALL_PREFIX=/usr/local . && \
    make -j$(nproc) && \
    make install && \
    make clean

# Install nexpnr-ecp5
RUN git clone  --shallow-since=2025.01.01 \
    https://github.com/YosysHQ/nextpnr/ \
    nextpnr && \
    cd nextpnr && \
    git checkout 0c060512c1bf6719391e2d3351c8cb757bec29cc
RUN cd nextpnr && \
    git submodule init && git submodule update && \
    cmake . -B build -DARCH=ecp5 -DTRELLIS_INSTALL_PREFIX=/usr/local && \
    cmake --build build && \
    cd build && \
    make install && \
    make clean
