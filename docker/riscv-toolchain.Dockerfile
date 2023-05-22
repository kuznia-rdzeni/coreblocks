FROM ubuntu:22.10

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    autoconf automake autotools-dev curl python3 bc \
    libmpc-dev libmpfr-dev libgmp-dev gawk build-essential \
    bison flex texinfo gperf libtool patchutils zlib1g-dev \
    libexpat-dev ninja-build git ca-certificates python-is-python3 && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/riscv/riscv-gnu-toolchain && \
    cd riscv-gnu-toolchain && \
    git checkout 2023.05.14 && \
    ./configure --with-multilib-generator="rv32i-ilp32--a*zifence*zicsr;rv32im-ilp32--a*zifence*zicsr;rv32ic-ilp32--a*zifence*zicsr;rv32imc-ilp32--a*zifence*zicsr;rv32imfc-ilp32f--a*zifence" && \
    make -j$(nproc) && \
    cd / && rm -rf riscv-gnu-toolchain
