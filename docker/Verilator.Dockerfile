FROM ubuntu:22.10

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    python3.10 libpython3.10 python3-pip git \
    perl perl-doc help2man make autoconf g++ flex bison ccache numactl \
    libgoogle-perftools-dev libfl-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --recursive \
    https://github.com/verilator/verilator.git \
    verilator && \
    cd verilator && \
    git checkout v5.008
RUN cd verilator && \
    autoconf && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    make clean && \
    ccache -C


