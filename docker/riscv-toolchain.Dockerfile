FROM ubuntu:23.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    autoconf automake autotools-dev curl python3.11 python3.11-venv python3-pip bc lsb-release \
    libmpc-dev libmpfr-dev libgmp-dev gawk build-essential \
    bison flex texinfo gperf libtool patchutils zlib1g-dev device-tree-compiler \
    libexpat-dev ninja-build git ca-certificates python-is-python3 \ 
    libssl-dev libbz2-dev libreadline-dev libsqlite3-dev libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --shallow-since=2023.05.01 https://github.com/riscv/riscv-gnu-toolchain && \
    cd riscv-gnu-toolchain && \
    git checkout 2023.12.10 && \
    ./configure --with-multilib-generator="rv32i-ilp32--a*zifence*zicsr;rv32im-ilp32--a*zifence*zicsr;rv32ic-ilp32--a*zifence*zicsr;rv32imc-ilp32--a*zifence*zicsr;rv32imfc-ilp32f--a*zifence;rv32imc_zba_zbb_zbc_zbs-ilp32--a*zifence*zicsr" && \
    make -j$(nproc) && \
    cd / && rm -rf riscv-gnu-toolchain

RUN git clone --shallow-since=2023.10.01 https://github.com/riscv-software-src/riscv-isa-sim.git spike && \
    cd spike && \
    git checkout eeef09ebb894c3bb7e42b7b47aae98792b8eef79 && \
    mkdir build/ install/  && \
    cd build/ && \
    ../configure --prefix=/spike/install/ && \
    make -j$(nproc) && \
    make install && \
    cd .. && \
    rm -rf build/

RUN git clone --depth=1 https://github.com/pyenv/pyenv.git .pyenv && \
    export PATH=/.pyenv/bin:$PATH && \
    export PYENV_ROOT=/root/.pyenv && \
    eval "$(pyenv init --path)" && \
    pyenv install 3.6.15 && \
    pyenv global 3.6.15 && \
    python -m venv venv3.6 && \
    . venv3.6/bin/activate && \
    python -m pip install --upgrade pip && \
    python -m pip install riscof && \
    pyenv global system
