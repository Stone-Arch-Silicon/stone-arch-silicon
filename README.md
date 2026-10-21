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

The site is plain HTML, CSS, and JavaScript with no build step. GitHub Pages serves the files as they are, and every page opens straight from disk in a browser.

| Path | Purpose |
| --- | --- |
| [index.html](index.html) | Home page, and the master copy of the shared head, header, menu, and footer |
| [about.html](about.html) | The four subteams, the team (board and advisors), the ASIC Network, and club facts |
| `team-*.html` | Individual profiles for the eight student leads and officers, linked from Home and About |
| [events.html](events.html) | The SASi Google Calendar |
| [updates.html](updates.html) | News cards (the home page lists the latest headlines) |
| [sponsor.html](sponsor.html) | Our sponsor, the sponsorship one-pager, and how to get in touch |
| [join.html](join.html) | Ways in, what members get, and the sign-up form |
| [assets/site.css](assets/site.css) | Styles shared by every page |
| [assets/site.js](assets/site.js) | Header, menu, scroll effects, and motion controls shared by every page |
| [assets/calendar.js](assets/calendar.js) | Calendar for events.html (API key and setup steps are at the top) |
| [assets/team/](assets/team/) | Team headshots for about.html and the home page, one square JPG per person (update the team list in both pages) |
| [assets/sasi-sponsorship.pdf](assets/sasi-sponsorship.pdf) | The sponsorship one-pager linked from sponsor.html |
| [assets/sasi-sponsorship.html](assets/sasi-sponsorship.html) | Source for the one-pager: edit it, open it in Chrome, and Print to PDF with no margins and background graphics on |
| [assets/](assets/) | Fonts, images, and the hero video |
| [scripts/sync_layout.py](scripts/sync_layout.py) | Copies the shared blocks from index.html into every page |
| [sitemap.xml](sitemap.xml) | Page list for search engines |
| [.github/workflows/](.github/workflows/) | Automation and deployment |
| [package.json](package.json) | Project configuration |

### Changing the nav, menu, announcement, or footer

These blocks repeat in every page between `<!-- shared:... -->` marker comments. Edit them in `index.html`, then run:

```sh
python3 scripts/sync_layout.py
```

The script copies the blocks into the other pages and marks each page's own links with `aria-current="page"`, which highlights the current page in the nav. Run it with `--check` to list pages that are out of date without changing anything.

### Adding a page

1. Copy an existing page, such as `sponsor.html`, and replace what's inside `<main>`. Keep the three marker pairs; the script fills them in.
2. Add the page to the nav, menu, and footer in `index.html`, and to `sitemap.xml`.
3. Run `python3 scripts/sync_layout.py`.

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

### Updating a lead profile

Edit the person’s `team-<name>.html` page for their role, focus, or links. Update the matching cards in `index.html` and `about.html` when names or roles change. Profiles use the existing photos in `assets/team/` and the same shared layout blocks as every other page; `python3 scripts/sync_layout.py` keeps their headers and footers current. Personal links should be verified before adding them; the club email is the default contact route.

### Sponsor logo belt

Home and Sponsor include a scrolling strip for TSMC, UCLA, Cadence, Synopsys, ForwardEdge ASIC, SCALE, and UMN ECE. The markup on both pages records the official logo source URLs; the Synopsys SVG is taken from its official homepage. Update both lists together. `assets/site.js` creates a non-interactive duplicate for the seamless loop. Hover pauses it, the button toggles pause, keyboard focus restores a static scrollable list, and the site motion preference and reduced-motion setting stop the animation.
