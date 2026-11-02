# Welcome to LeetSpice

LeetSpice is a circuit design challenge platform built on real EDA tools. You will write SPICE netlists and submit them for verification against silicon-accurate simulations.

## Before you begin: Install the EDA Toolchain

All circuit verification on LeetSpice runs on **IIC-OSIC-TOOLS** — a pre-configured open-source EDA environment that bundles ngspice, KLayout, Magic, Netgen, and the IHP SG13G2 PDK into a single ready-to-use container.

### Installation steps

1. Open the **[IIC-OSIC-TOOLS repository](https://github.com/iic-jku/iic-osic-tools)** and follow the installation guide for your operating system.
2. The toolchain runs as a Docker/Podman container — make sure one of those is installed first.
3. Launch the container and verify that the ngspice and KLayout commands are available inside it.

### Why these tools?

LeetSpice submits your SPICE netlists to an ngspice-based characterization engine that sweeps **process corners (SS · TT · FF)**, **temperature corners**, and **supply voltage** to verify your design holds across all conditions. The KLayout-backed challenges additionally run Magic DRC, Netgen LVS, and parasitic extraction. The same open-source tools you run locally are used for official verification — no proprietary simulators, no black boxes.

## Completing this challenge

Once you have installed and successfully launched IIC-OSIC-TOOLS, click the confirmation button on this page. All circuit design challenges will unlock immediately.
