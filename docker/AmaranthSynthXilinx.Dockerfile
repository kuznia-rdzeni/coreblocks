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
RUN nix profile install github:openxc7/toolchain-nix/f358781e5c21a59ab9c8c10f03beb81d8f8e468a\#nextpnr-xilinx && \
nix profile install github:openxc7/toolchain-nix/f358781e5c21a59ab9c8c10f03beb81d8f8e468a\#prjxray && \
nix profile install github:openxc7/toolchain-nix/f358781e5c21a59ab9c8c10f03beb81d8f8e468a\#fasm && \
    nix-store --gc 

