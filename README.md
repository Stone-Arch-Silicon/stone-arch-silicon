# Stone Arch Silicon | University of Minnesota

**A student community for semiconductor design: ASICs, FPGAs, and the engineering that connects RTL to physical hardware.**

We help students turn ECE coursework into projects they can build, verify, explain, and hand off to another engineer.

[Club website](https://stone-arch-silicon.github.io/stone-arch-silicon/) · [Start ASIC 101](https://github.com/Stone-Arch-Silicon/ASIC_101) · [All repositories](https://github.com/orgs/Stone-Arch-Silicon/repositories)

## Find your starting point

| You want to... | Start here | What lives there |
| --- | --- | --- |
| Build your first digital chip project | [ASIC 101](https://github.com/Stone-Arch-Silicon/ASIC_101) | 25 lessons around an 8-bit ALU: RTL, verification, FPGA implementation, and an ASIC flow |
| Read or improve club documentation | [ASIC docs](https://github.com/Stone-Arch-Silicon/ASIC-docs) | Markdown source, mdBook configuration, and a shared theme |
| Explore accelerator architecture | [Systolic matrix multiplier](https://github.com/Stone-Arch-Silicon/Mat_Mul_Systolic_Arrays) | SystemVerilog project and simulation documentation for a 2x2 array |
| Explore numerical formats | [8-bit posit](https://github.com/Stone-Arch-Silicon/8-Bit_Posit) | Research documentation and an interactive codec manual |
| Improve the documentation experience | [ASIC Docs Theme](https://github.com/Stone-Arch-Silicon/ASIC-Docs-Theme) | Reusable mdBook styling, navigation, and HDL highlighting |
| Update the club website | **This repository** | Site pages, assets, and deployment configuration |

## Learning path

**Basic Verilog → ASIC 101 ALU → self-checking simulation → FPGA reports → ASIC physical design → documented project handoff.**

Start with the ripple-carry adder option in ASIC 101. Once you have a baseline, compare carry-lookahead and carry-select implementations under the same constraints. Save the source revision, tool versions, reports, and an explanation of the tradeoffs.

For broader educational resources and collaboration, visit the [ASIC Network](https://github.com/ASIC-Network), including its [analog](https://github.com/ASIC-Network/analog-tutorials) and [digital](https://github.com/ASIC-Network/digital-tutorials) tutorial tracks.

## Contributing to a project

1. Pick the repository that owns the work and read its README.
2. Make a focused change with a clear problem and expected result.
3. Include evidence: a rendered-page check for documentation, or the commands, logs, and reports for hardware changes.
4. Use a pull request for review and credit the contributors involved.

Each hardware project should state its current stage: concept, RTL, simulation, synthesis, routed layout, fabrication, or bench measurement. Report the stage supported by its artifacts and track the next missing step.

## Website repository guide

| Path | Purpose |
| --- | --- |
| [index.html](index.html) | Main website entry point |
| [pages/](pages/) | Additional site pages |
| [assets/](assets/) | Site assets |
| [.github/workflows/](.github/workflows/) | Automation and deployment |
| [package.json](package.json) | Project configuration |

Course lessons belong in ASIC 101 or the documentation book; shared documentation styling belongs in ASIC Docs Theme. Keeping these responsibilities separate makes updates easier to find and review.

## Tools and resources

- **HDL:** Verilog / SystemVerilog
- **FPGA simulation and implementation:** Vivado, ModelSim
- **ASIC learning track:** LibreLane and SKY130, as documented in ASIC 101
- **Professional EDA:** Cadence, available through club/university resources
- **Reference architectures:** [PicoRV32](https://github.com/YosysHQ/picorv32), [CVA6](https://github.com/openhwgroup/cva6)

## Club information

**Faculty advisor:** Prof. Kevin Cao  
**President:** Avi Raghuvanshi  
**Vice-President:** Paulo Dietrich  
**Treasurer:** Madeline Ngo  
**Officers:** Ethan Chung, Talis Birmanis  
**Open to:** All UMN ECE students, all experience levels  
**Contact:** umnasicclub@gmail.com

Project authorship and review history are recorded in each repository's contributors and commits.
