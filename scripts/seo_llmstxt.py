#!/usr/bin/env python3
"""
CalcBlueprint llms.txt Generator
Regenerates llms.txt from the actual HTML files in the repo,
grouped by the same CATEGORY_SLUGS mapping used by seo_patch.py.

Because this reads from the filesystem, it can never go stale: every
new calculator page automatically appears in llms.txt on the next patch run.

Usage:
    python scripts/seo_llmstxt.py                    # dry-run (prints preview)
    python scripts/seo_llmstxt.py --write            # write llms.txt
    python scripts/seo_llmstxt.py --site-root . --write

Exit codes:
    0 = success (file written or no changes needed)
    1 = error
"""

import argparse
import html as html_module
import re
import sys
from pathlib import Path

# Import shared constants from the patcher so categories stay in sync
sys.path.insert(0, str(Path(__file__).parent))
try:
    from seo_patch import CATEGORY_SLUGS, NON_CALCULATOR_URLS, SITE_DOMAIN
except ImportError:
    print("error: could not import seo_patch.py — both files must live in scripts/", file=sys.stderr)
    sys.exit(1)

# Human-readable section titles for each category key
SECTION_TITLES = {
    "concrete": "Concrete & Masonry",
    "masonry": "Concrete & Masonry",
    "roofing": "Roofing & Gutters",
    "stairs": "Stairs & Framing",
    "deck": "Stairs & Framing",
    "tile": "Flooring & Tile",
    "flooring": "Flooring & Tile",
    "drywall": "Walls, Ceilings & Finishes",
    "paint": "Walls, Ceilings & Finishes",
    "insulation": "Walls, Ceilings & Finishes",
    "siding": "Siding & Exterior",
    "fencing": "Fencing & Gates",
    "landscaping": "Paving & Landscaping",
    "gravel": "Paving & Landscaping",
    "hvac": "HVAC",
    "electrical": "Electrical",
    "conversions": "Conversions & Reference",
}

# Priority order for sections — most-searched categories first
SECTION_ORDER = [
    "conversions",  # ← add at the top
    "concrete", "masonry", "roofing", "stairs", "deck", "tile", "flooring",
    "drywall", "paint", "insulation", "siding", "fencing", "landscaping",
    "gravel", "hvac", "electrical",
]

# Slugs that appear at the top in "Most Used Calculators"
FEATURED_SLUGS = [
    "concrete-slab-cost-calculator",
    "concrete-mix-calculator",
    "deck-calculator",
    "tile-calculator",
    "paint-calculator",
    "roof-area-calculator",
    "gravel-calculator",
    "fence-calculator",
]

SITE_NAME = "CalcBlueprint"
SITE_TAGLINE = (
    "Free construction calculators for contractors, estimators, and DIY. "
    "Instant material estimates for concrete, roofing, flooring, paint, and more. "
    "No signup, no account, no ads before results."
)
SITE_DESCRIPTION = (
    "CalcBlueprint is an independent tool site built by Emiliano. Every calculator "
    "uses published formulas from ACI 318, NRCA, IRC, TCNA, ASTM, and manufacturer "
    "specifications — not proprietary algorithms. Results are estimates for planning; "
    "verify with a licensed professional before ordering materials."
)
CONTACT_EMAIL = "hello@calcblueprint.com"


def find_html_files(site_root: Path):
    from seo_patch import IGNORE_DIRS, IGNORE_FILES
    files = []
    for path in site_root.rglob("*.html"):
        if any(part in IGNORE_DIRS for part in path.parts):
            continue
        if path.name in IGNORE_FILES:
            continue
        files.append(path)
    return sorted(files)


def expected_url(file_path: Path, site_root: Path) -> str:
    rel = file_path.relative_to(site_root)
    parts = rel.parts
    if rel.name == "index.html":
        if len(parts) == 1:
            return "/"
        return "/" + "/".join(parts[:-1]) + "/"
    return "/" + rel.stem + "/"


def page_title(html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", html, re.DOTALL | re.IGNORECASE)
    if not m:
        return ""
    title = m.group(1).strip()
    # Strip the " — CalcBlueprint" suffix
    title = re.split(r"\s+[—|]\s+CalcBlueprint", title)[0].strip()
    return html_module.unescape(title)


def page_description(html: str) -> str:
    m = re.search(
        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
        html, re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return ""
    return html_module.unescape(m.group(1).strip()).replace("\n", " ")


def build_llmstxt(site_root: Path) -> str:
    files = find_html_files(site_root)

    # Map slug -> (title, description)
    pages = {}
    for path in files:
        url = expected_url(path, site_root)
        if url in NON_CALCULATOR_URLS:
            continue
        slug = url.strip("/").split("/")[-1]
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        title = page_title(html)
        desc = page_description(html)
        if title and desc:
            pages[slug] = (title, desc)

    lines = []
    lines.append(f"# {SITE_NAME}")
    lines.append("")
    lines.append(f"> {SITE_TAGLINE}")
    lines.append("")
    lines.append(SITE_DESCRIPTION)
    lines.append("")

    # Featured section
    featured = [s for s in FEATURED_SLUGS if s in pages]
    if featured:
        lines.append("## Most Used Calculators")
        lines.append("")
        for slug in featured:
            title, desc = pages[slug]
            lines.append(f"- [{title}]({SITE_DOMAIN}/{slug}/): {desc}")
        lines.append("")

    # Category sections (deduped by display title, in priority order)
    seen_titles = set()
    seen_slugs = set(featured)

    for cat_key in SECTION_ORDER:
        if cat_key not in CATEGORY_SLUGS:
            continue
        display_title = SECTION_TITLES.get(cat_key, cat_key.title())
        if display_title in seen_titles:
            continue
        seen_titles.add(display_title)

        section_slugs = [
            s for s in CATEGORY_SLUGS[cat_key]
            if s in pages and s not in seen_slugs
        ]
        if not section_slugs:
            continue

        lines.append(f"## {display_title}")
        lines.append("")
        for slug in section_slugs:
            title, desc = pages[slug]
            lines.append(f"- [{title}]({SITE_DOMAIN}/{slug}/): {desc}")
            seen_slugs.add(slug)
        lines.append("")

    # Any calculator not covered by the category map (safety net)
    orphans = sorted(set(pages) - seen_slugs)
    if orphans:
        lines.append("## Other Calculators")
        lines.append("")
        for slug in orphans:
            title, desc = pages[slug]
            lines.append(f"- [{title}]({SITE_DOMAIN}/{slug}/): {desc}")
        lines.append("")

    # Site info section
    lines.append("## Site Information")
    lines.append("")
    info_pages = [
        ("/how-it-works/", "Every formula, standard, and data source behind the calculators, with a complete calculator library."),
        ("/about/", "Independent tool site built by Emiliano."),
        ("/contact/", "Questions, corrections, and accuracy reports."),
        ("/privacy/", "No signups, no accounts, no ad cookies."),
        ("/terms/", "Free to use, no warranty on calculated results."),
    ]
    info_titles = {
        "/how-it-works/": "How It Works",
        "/about/": "About",
        "/contact/": "Contact",
        "/privacy/": "Privacy Policy",
        "/terms/": "Terms of Service",
    }
    for url, desc in info_pages:
        lines.append(f"- [{info_titles[url]}]({SITE_DOMAIN}{url}): {desc}")
    lines.append("")

    # Notes
    lines.append("## Notes")
    lines.append("")
    lines.append("- All calculators are free and require no signup or account.")
    lines.append("- Formula sources: ACI 318 (concrete), NRCA (roofing), IRC and ICC (framing and stairs), TCNA (tile), ASTM (materials), AWC NDS (lumber).")
    lines.append("- Results are planning estimates. Verify with a licensed professional before ordering materials or beginning structural work.")
    lines.append(f"- Contact: {CONTACT_EMAIL}")
    lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-root", default=".", help="Root folder containing HTML files")
    ap.add_argument("--write", action="store_true", help="Write llms.txt (default: print preview)")
    args = ap.parse_args()

    site_root = Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"error: site root does not exist: {site_root}", file=sys.stderr)
        sys.exit(1)

    content = build_llmstxt(site_root)

    word_count = len(content.split())
    line_count = content.count("\n")
    url_count = content.count(f"{SITE_DOMAIN}/")

    if args.write:
        target = site_root / "llms.txt"
        # Skip write if identical (keeps git history clean)
        if target.exists() and target.read_text(encoding="utf-8") == content:
            print(f"llms.txt unchanged — {url_count} URLs, {word_count} words")
            sys.exit(0)
        target.write_text(content, encoding="utf-8")
        print(f"Wrote llms.txt — {url_count} URLs, {word_count} words, {line_count} lines")
    else:
        print(content)
        print(f"\n--- preview: {url_count} URLs, {word_count} words ---")
        print("(dry-run — re-run with --write to apply)")

    sys.exit(0)


if __name__ == "__main__":
    main()
