#!/usr/bin/env python3
"""
CalcBlueprint Description Rewriter
Replaces short meta descriptions with CTR-optimized 140-155 char versions,
and keeps og:description + twitter:description in sync.

Idempotent: safe to re-run. If a page's description already matches the
target, it is skipped. Pages not in DESCRIPTIONS are also skipped.

Usage:
    python scripts/seo_descriptions.py                     # dry-run
    python scripts/seo_descriptions.py --write             # apply
    python scripts/seo_descriptions.py --check             # report only
    python scripts/seo_descriptions.py --site-root . --write

Exit codes:
    0 = no changes needed OR changes applied successfully
    1 = something failed (missing file, missing meta tag, etc.)
"""

import argparse
import re
import sys
from pathlib import Path

# URL → new description (target 140-155 chars)
DESCRIPTIONS = {
    # ---- Calculators ----
    "/ac-unit-size-calculator/":
        "Calculate AC unit size in tons for any home. Enter square footage, ceiling height, and climate zone for precise cooling capacity and BTU sizing.",
    "/artificial-turf-calculator/":
        "Calculate artificial turf rolls and square footage for any lawn or patio. Enter area dimensions and turf roll width for exact material and seam quantities.",
    "/backsplash-calculator/":
        "Calculate backsplash tile for any kitchen. Enter counter length, backsplash height, and outlets for exact tile count, thinset, and grout needed.",
    "/bathroom-floor-tile-calculator/":
        "Calculate bathroom floor tile count, thinset, and grout. Enter floor dimensions, tile size, and waste % for a complete bathroom tile material list.",
    "/breaker-size-calculator/":
        "Calculate breaker size and wire gauge for any circuit. Enter amp load, voltage, and wire run for safe breaker, wire, and conduit recommendations.",
    "/btu-calculator/":
        "Calculate BTU cooling and heating needs for any room. Enter room size, ceiling height, and window count for precise AC and furnace sizing.",
    "/chain-link-fence-calculator/":
        "Calculate chain link fence materials for any yard. Enter linear feet, height, and post spacing for exact rolls, posts, rails, and tension wire.",
    "/compost-calculator/":
        "Calculate compost volume for lawns, gardens, and raised beds. Enter area dimensions and depth for exact cubic yards, cubic feet, or bag counts.",
    "/concrete-column-calculator/":
        "Calculate concrete for round, square, or rectangular columns. Enter column diameter, height, and quantity for exact cubic yards and bag count.",
    "/concrete-footing-calculator/":
        "Calculate concrete for footings and foundations. Enter footing width, depth, and total length for exact cubic yards with 10% waste included.",
    "/corner-bead-calculator/":
        "Calculate corner bead for drywall installations. Enter wall height, outside corner count, and bead type for exact linear feet and box quantity.",
    "/drywall-mud-calculator/":
        "Calculate joint compound for any drywall job. Enter sheet count, joint length, and finish level for exact mud, tape, and bucket quantities needed.",
    "/drywall-screws-calculator/":
        "Calculate drywall screw quantity for any job. Enter sheet count, stud spacing, and stud length for exact screw count and bulk box quantity.",
    "/duct-size-calculator/":
        "Calculate HVAC duct size for any room. Enter CFM airflow, duct type, and run length for exact round or rectangular duct dimensions and velocities.",
    "/electrical-load-calculator/":
        "Calculate electrical load for any home or service panel. Enter appliances, square footage, and voltage for exact amperage and panel size needed.",
    "/fertilizer-calculator/":
        "Calculate fertilizer quantity for any lawn or garden. Enter square footage, N-P-K ratio, and target rate for exact pounds and bag count needed.",
    "/furnace-size-calculator/":
        "Calculate furnace size in BTUs for any home. Enter square footage, climate zone, and insulation level for precise heating capacity recommendations.",
    "/gate-calculator/":
        "Calculate gate materials for any fence project. Enter gate width, height, and post size for exact lumber, hardware, and concrete quantities needed.",
    "/grass-seed-calculator/":
        "Calculate grass seed quantity for any lawn. Enter square footage, grass type, and seeding rate for exact pounds of seed and overseed quantity needed.",
    "/grout-calculator/":
        "Calculate grout for any tile installation. Enter tile size, joint width, and total area for exact grout pounds, kilograms, and bag count needed.",
    "/gutter-calculator/":
        "Calculate gutters, downspouts, and hangers for any home. Enter roof area, roof pitch, and downspout count for exact linear feet and fittings.",
    "/hardie-plank-calculator/":
        "Calculate Hardie plank siding for any exterior wall. Enter wall area, board dimensions, and overlap for exact siding boards and waste allowance.",
    "/insulation-calculator/":
        "Calculate insulation for walls, ceilings, and attics. Enter square footage, R-value target, and insulation type for exact batts, rolls, or blown-in bags.",
    "/kitchen-floor-calculator/":
        "Calculate tile, laminate, or vinyl for any kitchen floor. Enter kitchen dimensions, floor material, and waste % for exact material and cost.",
    "/laminate-flooring-calculator/":
        "Calculate laminate flooring planks and cartons for any room. Enter room dimensions, plank size, and waste % for exact box count and cost.",
    "/mortar-calculator/":
        "Calculate mortar, sand, and cement for brick or block walls. Enter wall area, unit size, and joint width for exact mortar bags and sand volume.",
    "/mulch-calculator/":
        "Calculate mulch volume for any landscape bed. Enter area dimensions and depth for exact cubic yards, cubic feet, and bag counts needed.",
    "/outlet-spacing-calculator/":
        "Calculate outlet spacing and total count for any room. Enter wall length, ceiling height, and local code spacing for exact outlet placement and count.",
    "/paver-calculator/":
        "Calculate pavers, sand, and gravel for driveways and patios. Enter area dimensions and paver size for exact paver count, base, and joint sand.",
    "/privacy-fence-calculator/":
        "Calculate privacy fence materials for any yard. Enter linear feet, height, and picket spacing for exact lumber, posts, rails, and concrete needed.",
    "/retaining-wall-calculator/":
        "Calculate retaining wall blocks, capstones, and gravel. Enter wall length, height, and block type for exact blocks, base, and drainage stone needed.",
    "/ridge-vent-calculator/":
        "Calculate ridge vent for any attic. Enter attic floor area, roof pitch, and vent type for exact linear feet and net free vent area needed.",
    "/roof-truss-calculator/":
        "Calculate roof trusses for any house. Enter building width, roof pitch, and truss spacing for exact truss count, span, and uplift requirements.",
    "/shower-tile-calculator/":
        "Calculate shower wall and floor tile, thinset, and grout. Enter shower dimensions, tile size, and waste % for exact material quantities needed.",
    "/sod-calculator/":
        "Calculate sod rolls or pallets for any lawn. Enter lawn dimensions and sod roll size for exact square footage, rolls, and pallet quantities needed.",
    "/thinset-calculator/":
        "Calculate thinset mortar for any tile job. Enter tile area, trowel size, and tile type for exact 50-lb bag count and per-bag coverage rate.",
    "/topsoil-calculator/":
        "Calculate topsoil for lawns, gardens, and raised beds. Enter area dimensions and depth for exact cubic yards, cubic feet, or bag counts needed.",
    "/vinyl-siding-calculator/":
        "Calculate vinyl siding squares, trim, and accessories for any home. Enter wall area, siding dimensions, and waste % for exact materials needed.",
    "/wall-area-calculator/":
        "Calculate wall area for paint, wallpaper, or siding. Enter room dimensions and subtract doors and windows for exact net wall square footage.",
    "/wallpaper-calculator/":
        "Calculate wallpaper rolls for any room. Enter wall dimensions, roll size, and pattern repeat for exact roll count, match allowance, and waste.",
    "/wire-size-calculator/":
        "Calculate wire gauge for any circuit. Enter amp load, wire run length, and voltage drop limit for exact AWG wire size and conduit recommendation.",

    # ---- Info pages (different framing — not calculator intents) ----
    "/contact/":
        "Contact CalcBlueprint with questions, corrections, or feedback about our construction calculators. We respond to accuracy reports within 1-2 business days.",
    "/how-it-works/":
        "See exactly how CalcBlueprint calculates every material estimate. Every formula, standard, and data source, verified against ACI, ICC, ASTM, and NRCA.",
    "/privacy/":
        "How CalcBlueprint handles your data. No signups, no accounts, no ad cookies. A short, analytics-limited privacy policy you can read in two minutes.",
    "/terms/":
        "CalcBlueprint terms of service. Free to use, no warranty on calculated results. Verify with a licensed professional before ordering any materials.",
}

IGNORE_DIRS = {
    ".git", ".github", "node_modules", "scripts", "assets", "img",
    "images", "css", "js", "static", "dist", "build", "__pycache__",
    ".venv", "venv", "env",
}
IGNORE_FILES = {"404.html"}

MIN_LEN = 140
MAX_LEN = 155


def find_html_files(site_root: Path):
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


def replace_description(html: str, new_desc: str) -> tuple:
    """
    Replace <meta name="description">, then sync og:description and
    twitter:description to the same value. Returns (new_html, changed, msg).
    """
    # Match the description meta tag content
    pattern = r'(<meta\s+name=["\']description["\']\s+content=["\'])([^"\']*)(["\']\s*/?>)'
    m = re.search(pattern, html, re.IGNORECASE)
    if not m:
        return html, False, "no description meta found"

    old_desc = m.group(2)
    if old_desc == new_desc:
        return html, False, "already up to date"

    # Replace description content using slices (safe for any characters)
    new_html = html[:m.start(2)] + new_desc + html[m.end(2):]

    # Sync og:description
    og_pattern = r'(<meta\s+property=["\']og:description["\']\s+content=["\'])([^"\']*)(["\']\s*/?>)'
    new_html = re.sub(
        og_pattern,
        lambda mm: mm.group(1) + new_desc + mm.group(3),
        new_html, count=1, flags=re.IGNORECASE,
    )

    # Sync twitter:description
    tw_pattern = r'(<meta\s+name=["\']twitter:description["\']\s+content=["\'])([^"\']*)(["\']\s*/?>)'
    new_html = re.sub(
        tw_pattern,
        lambda mm: mm.group(1) + new_desc + mm.group(3),
        new_html, count=1, flags=re.IGNORECASE,
    )

    return new_html, True, f"{len(old_desc)}→{len(new_desc)} chars (og+twitter synced)"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-root", default=".", help="Root folder containing HTML files")
    ap.add_argument("--write", action="store_true", help="Apply changes (default: dry-run)")
    ap.add_argument("--check", action="store_true", help="Only report, no changes")
    args = ap.parse_args()

    site_root = Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"error: site root does not exist: {site_root}", file=sys.stderr)
        sys.exit(2)

    files = find_html_files(site_root)
    if not files:
        print(f"error: no HTML files found under {site_root}", file=sys.stderr)
        sys.exit(2)

    mode = "APPLY" if args.write else ("CHECK" if args.check else "DRY-RUN")
    print(f"Description Rewriter [{mode}] — {len(files)} files — {len(DESCRIPTIONS)} targets\n")

    # Pre-flight: validate description lengths
    print("Length check on new descriptions:")
    bad_len = []
    for url, desc in DESCRIPTIONS.items():
        L = len(desc)
        flag = "OK " if MIN_LEN <= L <= MAX_LEN else "BAD"
        if not (MIN_LEN <= L <= MAX_LEN):
            bad_len.append((url, L))
            print(f"  [{flag}] {L:>3}  {url}")
    print(f"  {len(DESCRIPTIONS) - len(bad_len)}/{len(DESCRIPTIONS)} in range; {len(bad_len)} out of range\n")

    if args.check:
        print("--check mode: not modifying files.")
        sys.exit(0)

    total_changed = 0
    total_skipped = 0
    total_missing = 0
    seen_urls = set()

    for path in files:
        url = expected_url(path, site_root)
        seen_urls.add(url)

        if url not in DESCRIPTIONS:
            continue

        new_desc = DESCRIPTIONS[url]
        html = path.read_text(encoding="utf-8", errors="replace")
        new_html, changed, msg = replace_description(html, new_desc)

        if changed:
            total_changed += 1
            print(f"[CHANGED] {url}")
            print(f"          {msg}")
            if args.write:
                path.write_text(new_html, encoding="utf-8")
        else:
            total_skipped += 1
            if msg == "no description meta found":
                print(f"[MISSING] {url} — {msg}")
                total_missing += 1

    # Pages in DESCRIPTIONS dict that we never matched to a file
    unseen = set(DESCRIPTIONS.keys()) - seen_urls
    if unseen:
        print(f"\n[NOTFOUND] {len(unseen)} URLs in DESCRIPTIONS have no matching HTML file:")
        for url in sorted(unseen):
            print(f"          {url}")
        total_missing += len(unseen)

    print(f"\nSummary: {total_changed} changed, {total_skipped} skipped, {total_missing} missing")
    if not args.write and total_changed > 0:
        print("(dry-run — re-run with --write to apply changes)")
    sys.exit(0 if total_missing == 0 else 1)


if __name__ == "__main__":
    main()
