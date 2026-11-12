#!/usr/bin/env python3
"""
CalcBlueprint SEO Patcher
Auto-fixes safe, reversible SEO issues across all HTML pages.

Fixes performed:
    og       — Insert og:* and twitter:* meta tags (derived from title/description)
    favicon  — Insert <link rel="icon">
    h1       — Insert missing <h1> (derived from <title> or canonical URL)
    nav      — Normalize nav links: #anchors → URLs, .html → clean URLs, no-slash → slash
    jsonld   — Insert WebApplication JSON-LD schema
    date     — Insert "Last updated" line after H1 on calculator pages

Does NOT fix (requires human decision):
    - Missing or too-short title/description
    - Broken internal links (except known nav patterns)
    - Missing footer citation (editorial per-page standard)

Usage:
    python scripts/seo_patch.py                       # dry-run, all fixes
    python scripts/seo_patch.py --fix=og              # only OG tags
    python scripts/seo_patch.py --fix=nav,date        # only nav + date
    python scripts/seo_patch.py --fix=all --write     # apply everything
    python scripts/seo_patch.py --site-root . --write # explicit root

Exit codes:
    0 = no changes needed OR changes applied successfully
    1 = something failed
"""

import argparse
import re
import sys
from pathlib import Path

SITE_DOMAIN = "https://calcblueprint.com"
DEFAULT_OG_IMAGE = f"{SITE_DOMAIN}/og-image.png"
SITE_AUTHOR = "Emiliano"
SITE_LAST_UPDATED = "2026-11-12"

IGNORE_DIRS = {
    ".git", ".github", "node_modules", "scripts", "assets", "img",
    "images", "css", "js", "static", "dist", "build", "__pycache__",
    ".venv", "venv", "env",
}
IGNORE_FILES = {"404.html"}

# #anchor → real URL (broken on-page nav)
ANCHOR_MAP = {
    "#about": "/about/",
    "#contact": "/contact/",
    "#privacy": "/privacy/",
    "#terms": "/terms/",
    "#how-it-works": "/how-it-works/",
}

# .html extension → clean URL (broken internal links)
HTML_EXT_MAP = {
    'href="/about.html"': 'href="/about/"',
    "href='/about.html'": "href='/about/'",
    'href="/contact.html"': 'href="/contact/"',
    "href='/contact.html'": "href='/contact/'",
    'href="/privacy.html"': 'href="/privacy/"',
    "href='/privacy.html'": "href='/privacy/'",
    'href="/terms.html"': 'href="/terms/"',
    "href='/terms.html'": "href='/terms/'",
    'href="/how-it-works.html"': 'href="/how-it-works/"',
    "href='/how-it-works.html'": "href='/how-it-works/'",
}

# Missing trailing slash → with trailing slash (normalization)
NO_SLASH_MAP = {
    'href="/about"': 'href="/about/"',
    "href='/about'": "href='/about/'",
    'href="/contact"': 'href="/contact/"',
    "href='/contact'": "href='/contact/'",
    'href="/privacy"': 'href="/privacy/"',
    "href='/privacy'": "href='/privacy/'",
    'href="/terms"': 'href="/terms/"',
    "href='/terms'": "href='/terms/'",
    'href="/how-it-works"': 'href="/how-it-works/"',
    "href='/how-it-works'": "href='/how-it-works/'",
}

# Pages that should NOT get auto-inserted "Last updated" lines
NON_CALCULATOR_URLS = {
    "/", "/about/", "/contact/", "/privacy/", "/terms/", "/how-it-works/",
}


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


def page_name_from_url(url: str) -> str:
    """Derive a human-readable page name from the URL slug."""
    if url == "/":
        return "CalcBlueprint"
    slug = url.strip("/").split("/")[-1]
    return " ".join(w.capitalize() for w in slug.replace("-", " ").split())


# ---------- Fix functions ----------
# Each returns (new_html, changed: bool, message: str)


def fix_og(html: str, url: str) -> tuple:
    if 'property="og:title"' in html or "property='og:title'" in html:
        return html, False, "og tags present"

    title = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    title = title.group(1).strip() if title else page_name_from_url(url) + " — CalcBlueprint"
    desc = re.search(r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']', html)
    desc = desc.group(1).strip() if desc else title

    full_url = f"{SITE_DOMAIN}{url}"
    block = (
        f'\n<meta property="og:type" content="website">'
        f'\n<meta property="og:url" content="{full_url}">'
        f'\n<meta property="og:title" content="{title}">'
        f'\n<meta property="og:description" content="{desc}">'
        f'\n<meta property="og:image" content="{DEFAULT_OG_IMAGE}">'
        f'\n<meta name="twitter:card" content="summary_large_image">'
        f'\n<meta name="twitter:title" content="{title}">'
        f'\n<meta name="twitter:description" content="{desc}">'
        f'\n<meta name="twitter:image" content="{DEFAULT_OG_IMAGE}">'
    )

    patterns = [
        r'(<meta\s+name=["\']description["\'][^>]*>)',
        r"(<title>.*?</title>)",
        r"(</head>)",
    ]
    for pat in patterns:
        if re.search(pat, html, re.DOTALL):
            new_html = re.sub(pat, r"\1" + block, html, count=1, flags=re.DOTALL)
            return new_html, True, "og tags inserted"
    return html, False, "og tags could not be inserted (no anchor)"


def fix_favicon(html: str, url: str) -> tuple:
    if 'rel="icon"' in html or "rel='icon'" in html:
        return html, False, "favicon present"
    tag = '\n<link rel="icon" href="/favicon.ico">'
    if "</head>" in html:
        new_html = html.replace("</head>", tag + "\n</head>", 1)
        return new_html, True, "favicon inserted"
    return html, False, "favicon could not be inserted (no </head>)"


def fix_h1(html: str, url: str) -> tuple:
    if re.search(r"<h1[\s>]", html, re.IGNORECASE):
        return html, False, "h1 present"

    title_match = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    if title_match:
        name = re.split(r"\s+[—|-]\s+", title_match.group(1).strip())[0].strip()
    else:
        name = page_name_from_url(url)

    tag = f'\n<h1>{name}</h1>'

    for pat in [
        r'(<div\s+class=["\']calculator-box["\'][^>]*>)',
        r'(<div\s+class=["\']container["\'][^>]*>)',
        r'(<main[^>]*>)',
    ]:
        m = re.search(pat, html, re.IGNORECASE)
        if m:
            new_html = html[:m.end()] + tag + html[m.end():]
            return new_html, True, f"h1 inserted: {name!r}"
    return html, False, "h1 could not be inserted (no anchor)"


def fix_nav(html: str, url: str) -> tuple:
    """Normalize all nav links: #anchors, .html extensions, missing trailing slash."""
    new_html = html
    changed = False

    # 1. #anchor → real URL
    for anchor, real_url in ANCHOR_MAP.items():
        if f'href="{anchor}"' in new_html:
            new_html = new_html.replace(f'href="{anchor}"', f'href="{real_url}"')
            changed = True
        if f"href='{anchor}'" in new_html:
            new_html = new_html.replace(f"href='{anchor}'", f"href='{real_url}'")
            changed = True

    # 2. .html extension → clean URL
    for old, new in HTML_EXT_MAP.items():
        if old in new_html:
            new_html = new_html.replace(old, new)
            changed = True

    # 3. missing trailing slash → trailing slash
    for old, new in NO_SLASH_MAP.items():
        if old in new_html:
            new_html = new_html.replace(old, new)
            changed = True

    return new_html, changed, "nav links normalized" if changed else "nav ok"


def fix_jsonld(html: str, url: str) -> tuple:
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    ):
        if '"WebApplication"' in m.group(1):
            return html, False, "WebApplication JSON-LD present"

    name = page_name_from_url(url)
    block = (
        f'\n<script type="application/ld+json">'
        f'{{"@context":"https://schema.org","@type":"WebApplication",'
        f'"name":"{name}","applicationCategory":"UtilityApplication",'
        f'"operatingSystem":"Web","offers":{{"@type":"Offer","price":"0","priceCurrency":"USD"}}}}'
        f'</script>'
    )
    if "</head>" in html:
        new_html = html.replace("</head>", block + "\n</head>", 1)
        return new_html, True, "WebApplication JSON-LD inserted"
    return html, False, "jsonld could not be inserted (no </head>)"


def fix_date(html: str, url: str) -> tuple:
    """Insert 'By Emiliano · Last updated YYYY-MM-DD' after H1 on calculator pages."""
    # Skip if already present (matches any "Last updated YYYY-MM-DD")
    if re.search(r"Last updated\s+\d{4}-\d{2}-\d{2}", html):
        return html, False, "date present"

    # Skip non-calculator pages (about, contact, privacy, terms, how-it-works, homepage)
    if url in NON_CALCULATOR_URLS or "calculator" not in url:
        return html, False, "not a calculator page"

    # Need an H1 to anchor the insertion point
    h1_match = re.search(r"<h1[^>]*>.*?</h1>", html, re.DOTALL | re.IGNORECASE)
    if not h1_match:
        return html, False, "no h1 to anchor date"

    # Safety: if a "Last Updated" (any casing) or "By Emiliano" already appears
    # shortly after the H1, don't duplicate
    after_h1 = html[h1_match.end():h1_match.end() + 250].lower()
    if "last updated" in after_h1 or "by emiliano" in after_h1:
        return html, False, "date-like text already present"

    date_line = (
        f'\n      <p style="color:#777;font-size:.85rem;margin:.25rem 0 1.25rem">'
        f'By {SITE_AUTHOR} · Last updated {SITE_LAST_UPDATED}</p>'
    )
    new_html = html[:h1_match.end()] + date_line + html[h1_match.end():]
    return new_html, True, "date line inserted"


# Registry — insertion order matters (h1 must run before date)
FIX_REGISTRY = {
    "og": fix_og,
    "favicon": fix_favicon,
    "h1": fix_h1,
    "nav": fix_nav,
    "jsonld": fix_jsonld,
    "date": fix_date,
}


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-root", default=".", help="Root folder containing HTML files")
    ap.add_argument("--fix", default="all", help="Comma-separated fixes: og,favicon,h1,nav,jsonld,date,all")
    ap.add_argument("--write", action="store_true", help="Apply changes (default: dry-run)")
    args = ap.parse_args()

    site_root = Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"error: site root does not exist: {site_root}", file=sys.stderr)
        sys.exit(2)

    if args.fix == "all":
        fixes = list(FIX_REGISTRY.keys())
    else:
        fixes = [f.strip() for f in args.fix.split(",") if f.strip()]
        bad = [f for f in fixes if f not in FIX_REGISTRY]
        if bad:
            print(f"error: unknown fixes: {bad}. Valid: {list(FIX_REGISTRY.keys())}", file=sys.stderr)
            sys.exit(2)

    files = find_html_files(site_root)
    if not files:
        print(f"error: no HTML files found under {site_root}", file=sys.stderr)
        sys.exit(2)

    mode = "APPLY" if args.write else "DRY-RUN"
    print(f"SEO Patch [{mode}] — {len(files)} files — fixes: {', '.join(fixes)}\n")

    total_changed = 0
    total_skipped = 0
    total_failed = 0

    for path in files:
        url = expected_url(path, site_root)
        html = path.read_text(encoding="utf-8", errors="replace")
        original = html
        file_changes = []

        for fix_name in fixes:
            fn = FIX_REGISTRY[fix_name]
            try:
                html, changed, msg = fn(html, url)
                if changed:
                    file_changes.append(f"{fix_name}: {msg}")
            except Exception as e:
                total_failed += 1
                file_changes.append(f"{fix_name}: FAILED ({e})")

        if html != original:
            total_changed += 1
            print(f"[CHANGED] {url}")
            for c in file_changes:
                print(f"          {c}")
            if args.write:
                path.write_text(html, encoding="utf-8")
        else:
            total_skipped += 1

    print(f"\nSummary: {total_changed} changed, {total_skipped} unchanged, {total_failed} failed")
    if not args.write and total_changed > 0:
        print("(dry-run — re-run with --write to apply changes)")
    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
