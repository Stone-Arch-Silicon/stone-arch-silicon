#!/usr/bin/env python3
"""Copy the shared layout blocks from index.html into every other page.

The site is plain HTML with no build step, so the head tags, header, menu,
and footer are repeated in each page. index.html holds the master copy of
each block, wrapped in marker comments:

    <!-- shared:head -->    ...  <!-- /shared:head -->
    <!-- shared:header -->  ...  <!-- /shared:header -->
    <!-- shared:footer -->  ...  <!-- /shared:footer -->

Edit a block in index.html, then run from the repository root:

    python3 scripts/sync_layout.py            # update every page
    python3 scripts/sync_layout.py --check    # only report pages that are out of date (exit 1)

While copying, any link that points at the page being written (for example
href="about.html" inside about.html) gets aria-current="page", which the
stylesheet uses to highlight the current page in the nav, menu, and footer.

To add a page: copy one of the existing pages, keep its three marker pairs
(the contents get replaced), add the page to the nav, menu, and footer in
index.html and to sitemap.xml, then run this script.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "index.html"
BLOCK = re.compile(r"(<!-- shared:([\w-]+) -->)(.*?)(<!-- /shared:\2 -->)", re.S)
CURRENT = ' aria-current="page"'


def mark_current(block: str, page: str) -> str:
    """Move aria-current="page" onto the links that point at `page`."""
    block = block.replace(CURRENT, "")
    return re.sub(r'(<a\b[^>]*?\shref="%s")' % re.escape(page), r"\1" + CURRENT, block)


def main() -> int:
    check = "--check" in sys.argv[1:]
    master = {m.group(2): m.group(3) for m in BLOCK.finditer(SOURCE.read_text(encoding="utf-8"))}
    if not master:
        print(f"No shared blocks found in {SOURCE.name}.")
        return 1

    stale = []
    for page in sorted(ROOT.glob("*.html")):
        html = page.read_text(encoding="utf-8")
        found = {m.group(2) for m in BLOCK.finditer(html)}
        if not found:
            continue  # not a site page (e.g. the Search Console verification file)
        missing = set(master) - found
        if missing:
            print(f"warning: {page.name} has no marker for: {', '.join(sorted(missing))}")
        unknown = found - set(master)
        if unknown:
            print(f"error: {page.name} uses blocks that index.html doesn't define: {', '.join(sorted(unknown))}")
            return 1

        def fill(m: re.Match) -> str:
            return m.group(1) + mark_current(master[m.group(2)], page.name) + m.group(4)

        updated = BLOCK.sub(fill, html)
        if updated != html:
            stale.append(page.name)
            if not check:
                page.write_text(updated, encoding="utf-8")

    if check:
        if stale:
            print("Out of date: " + ", ".join(stale) + "\nRun: python3 scripts/sync_layout.py")
            return 1
        print("All pages match index.html.")
    else:
        print(("Updated: " + ", ".join(stale)) if stale else "Nothing to update; all pages match index.html.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
