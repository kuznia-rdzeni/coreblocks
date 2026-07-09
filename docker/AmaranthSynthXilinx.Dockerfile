FROM ubuntu:24.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    git yosys lsb-release ca-certificates curl \
    build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

# Install nix
RUN curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install | sh -s -- --daemon && \
    echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf

ENV \
    PATH=/nix/var/nix/profiles/default/bin:/nix/var/nix/profiles/default/sbin:/bin:/sbin:/usr/bin:/usr/sbin \
    NIX_PATH=/nix/var/nix/profiles/per-user/root/channels

# Install openXC7 toolchain
RUN nix registry add openxc7 github:openxc7/toolchain-nix/f358781e5c21a59ab9c8c10f03beb81d8f8e468a && \
    nix profile add openxc7\#nextpnr-xilinx && \
    nix profile add openxc7\#prjxray && \
    nix profile add openxc7\#fasm && \
    nix build openxc7\#nextpnr-xilinx-chipdb.artix7 -o /nix/var/nix/gcroots/artix7-chipdb && \
    nix build openxc7\#nextpnr-xilinx-chipdb.kintex7 -o /nix/var/nix/gcroots/kintex7-chipdb && \
    nix build openxc7\#nextpnr-xilinx-chipdb.spartan7 -o /nix/var/nix/gcroots/spartan7-chipdb && \
    nix build openxc7\#nextpnr-xilinx-chipdb.zynq7 -o /nix/var/nix/gcroots/zynq7-chipdb && \
    nix-store --gc
