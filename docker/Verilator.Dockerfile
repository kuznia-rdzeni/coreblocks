FROM debian:trixie

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    python3.13 libpython3.13 python3-pip python3.13-venv git lsb-release \
    perl perl-doc help2man make autoconf g++ flex bison ccache numactl \
    libgoogle-perftools-dev libfl-dev zlib1g-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --recursive --shallow-since=2024.12.01 \
    https://github.com/verilator/verilator.git \
    verilator && \
    cd verilator && \
    git checkout v5.032
RUN cd verilator && \
    autoconf && \
    ./configure && \
    make -j$(nproc) && \
    make install && \
    make clean && \
    ccache -C


