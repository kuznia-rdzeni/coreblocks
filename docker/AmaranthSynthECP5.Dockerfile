FROM ubuntu:22.10

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    python3.10 python3-pip git yosys \
    build-essential cmake python3-dev libboost-all-dev libeigen3-dev

# Install prjtrellis
RUN git clone --recursive https://github.com/YosysHQ/prjtrellis
RUN cd prjtrellis && \
    cd libtrellis && \
    cmake -DCMAKE_INSTALL_PREFIX=/usr/local . && \
    make && \
    make install

# Install nexpnr-ecp5
RUN cd ../..
RUN git clone https://github.com/YosysHQ/nextpnr.git
RUN cd nextpnr && \
    cmake . -DARCH=ecp5 -DTRELLIS_INSTALL_PREFIX=/usr/local && \
    make -j$(nproc) && \
    make install

# Remove artifacts
RUN cd ..
RUN rm -rf prjtrellis
RUN rm -rf nextpnr
RUN rm -rf /var/lib/apt/lists/*
