FROM ubuntu:23.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    autoconf automake autotools-dev curl python3 bc lsb-release \
    libmpc-dev libmpfr-dev libgmp-dev gawk build-essential \
    bison flex texinfo gperf libtool patchutils zlib1g-dev \
    libexpat-dev ninja-build git ca-certificates python-is-python3 && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/riscv/riscv-gnu-toolchain && \
    cd riscv-gnu-toolchain && \
    git checkout 2023.05.14 && \
    ./configure --with-multilib-generator="rv32i-ilp32--a*zifence*zicsr;rv32im-ilp32--a*zifence*zicsr;rv32ic-ilp32--a*zifence*zicsr;rv32imc-ilp32--a*zifence*zicsr;rv32imfc-ilp32f--a*zifence;rv32i_zmmul-ilp32--a*zifence*zicsr;rv32ic_zmmul-ilp32--a*zifence*zicsr" && \
    make -j$(nproc) && \
    cd / && rm -rf riscv-gnu-toolchain


RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends device-tree-compiler && \
    rm -rf /var/lib/apt/lists/* && \
    git clone https://github.com/riscv-software-src/riscv-isa-sim.git spike && \
    cd spike && \
    git checkout eeef09ebb894c3bb7e42b7b47aae98792b8eef79 && \
    mkdir build/ install/  && \
    cd build/ && \
    ../configure --prefix=/spike/install/ && \
    make && \
    make install && \
    cd .. && \
    rm -rf build/

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev python3-venv python3-pip && \
    rm -rf /var/lib/apt/lists/* && \
    git clone https://github.com/pyenv/pyenv.git .pyenv && \
    export PATH=/.pyenv/bin:$PATH && \
    export PYENV_ROOT=/root/.pyenv && \
    eval "$(pyenv init --path)" && \
    pyenv install 3.6.15 && \
    pyenv install 3.11.6 && \
    pyenv global 3.6.15 && \
    python -V && \
    python -m venv venv3.6 && \
    . venv3.6/bin/activate && \
    python -m pip install --upgrade pip && \
    python -m pip install riscof && \
    pyenv global system
