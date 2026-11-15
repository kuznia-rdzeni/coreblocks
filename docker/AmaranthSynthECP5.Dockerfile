FROM ubuntu:24.04

RUN apt-get update && \
    DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends \
    git lsb-release ca-certificates curl \
    build-essential cmake && \
    rm -rf /var/lib/apt/lists/*

# Install nix
RUN curl --proto '=https' --tlsv1.2 -L https://nixos.org/nix/install | sh -s -- --daemon && \
    echo "experimental-features = nix-command flakes" >> /etc/nix/nix.conf

ENV \
    PATH=/nix/var/nix/profiles/default/bin:/nix/var/nix/profiles/default/sbin:/bin:/sbin:/usr/bin:/usr/sbin \
    NIX_PATH=/nix/var/nix/profiles/per-user/root/channels

# Install ecp5 toolchain
RUN nix profile add nixpkgs\#yosys && \
    nix profile add nixpkgs\#nextpnr && \
    nix profile add nixpkgs\#trellis && \
    nix-store --gc
