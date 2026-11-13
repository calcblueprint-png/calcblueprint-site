#!/usr/bin/env python3
"""
CalcBlueprint SEO Patcher
Auto-fixes safe, reversible SEO issues across all HTML pages.

Fixes performed:
    og          — Insert og:* and twitter:* meta tags (derived from title/description)
    favicon     — Insert <link rel="icon">
    h1          — Insert missing <h1> (derived from <title> or canonical URL)
    nav         — Normalize nav links: #anchors → URLs, .html → clean URLs, no-slash → slash
    jsonld      — Insert WebApplication JSON-LD schema (calculator pages only)
    date        — Insert "Last updated" line after H1 on calculator pages
    ga4         — Insert GA4 snippet if missing
    faq         — Generate FAQPage JSON-LD from visible FAQ if missing
    unclosed_p  — Close unclosed <p> tags (invalid HTML, breaks FAQ schema)
    related     — Insert Related Calculators section with category siblings

Does NOT fix (requires human decision):
    - Missing or too-short title/description
    - Broken internal links (except known nav patterns)
    - FAQ schema that exists but mismatches visible FAQ (flagged by linter)
    - Orphan pages with truly zero inbound links (flagged by linter)

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
import html as html_module
import json
import re
import sys
from pathlib import Path

SITE_DOMAIN = "https://calcblueprint.com"
DEFAULT_OG_IMAGE = f"{SITE_DOMAIN}/og-image.png"
SITE_AUTHOR = "Emiliano"
SITE_LAST_UPDATED = "2026-11-13"
GA4_MEASUREMENT_ID = "G-DHN9J7B497"

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

# Pages that should NOT get a WebApplication JSON-LD block
NO_JSONLD_URLS = {"/about/", "/contact/", "/privacy/", "/terms/", "/how-it-works/"}

# Block-level tags that cannot legally appear inside a <p>
BLOCK_TAGS = (
    r'p|h[1-6]|div|section|article|header|footer|main|aside|nav|'
    r'ul|ol|li|table|thead|tbody|tr|td|th|details|summary|'
    r'form|fieldset|blockquote|pre|hr'
)

# Topical category clusters — used to auto-generate "Related Calculators" sections.
# Each calculator slug belongs to one PRIMARY category (first one encountered wins),
# but may appear as a sibling in other categories too.
CATEGORY_SLUGS = {
    "concrete": [
        "concrete-slab-cost-calculator", "concrete-footing-calculator",
        "concrete-mix-calculator", "concrete-steps-calculator",
        "concrete-stairs-calculator", "concrete-column-calculator",
        "concrete-block-calculator", "rebar-spacing-calculator",
        "how-many-bags-of-concrete",
    ],
    "roofing": [
        "roof-pitch-calculator", "roof-area-calculator",
        "roof-truss-calculator", "shingle-calculator",
        "ridge-vent-calculator", "gutter-calculator",
    ],
    "fencing": [
        "fence-calculator", "chain-link-fence-calculator",
        "privacy-fence-calculator", "gate-calculator",
        "concrete-footing-calculator",
    ],
    "tile": [
        "tile-calculator", "grout-calculator", "thinset-calculator",
        "backsplash-calculator", "shower-tile-calculator",
        "bathroom-floor-tile-calculator", "kitchen-floor-calculator",
    ],
    "flooring": [
        "hardwood-flooring-calculator", "laminate-flooring-calculator",
        "carpet-calculator", "kitchen-floor-calculator",
    ],
    "drywall": [
        "drywall-calculator", "drywall-mud-calculator",
        "drywall-screws-calculator", "corner-bead-calculator",
        "wall-area-calculator",
    ],
    "paint": [
        "paint-calculator", "wallpaper-calculator", "wall-area-calculator",
        "drywall-calculator",
    ],
    "hvac": [
        "ac-unit-size-calculator", "btu-calculator",
        "furnace-size-calculator", "duct-size-calculator",
    ],
    "electrical": [
        "electrical-load-calculator", "wire-size-calculator",
        "breaker-size-calculator", "outlet-spacing-calculator",
    ],
    "landscaping": [
        "mulch-calculator", "sod-calculator", "compost-calculator",
        "fertilizer-calculator", "grass-seed-calculator",
        "topsoil-calculator", "artificial-turf-calculator",
        "paver-calculator",
    ],
    "siding": [
        "vinyl-siding-calculator", "hardie-plank-calculator",
        "wall-area-calculator", "paint-calculator",
    ],
    "deck": [
        "deck-calculator", "board-foot-calculator",
        "concrete-footing-calculator", "fence-calculator",
    ],
    "masonry": [
        "brick-calculator", "mortar-calculator",
        "concrete-block-calculator", "retaining-wall-calculator",
    ],
    "insulation": [
        "insulation-calculator", "drywall-calculator",
        "wall-area-calculator", "paint-calculator",
    ],
    "gravel": [
        "gravel-calculator", "asphalt-calculator",
        "concrete-mix-calculator", "topsoil-calculator", "mulch-calculator",
    ],
}

# Reverse lookup — first category a slug appears in becomes its primary
SLUG_TO_CATEGORY = {}
for _cat, _slugs in CATEGORY_SLUGS.items():
    for _slug in _slugs:
        SLUG_TO_CATEGORY.setdefault(_slug, _cat)


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


def strip_html(text: str) -> str:
    """Strip HTML tags and decode entities, then collapse whitespace."""
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


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

    for anchor, real_url in ANCHOR_MAP.items():
        if f'href="{anchor}"' in new_html:
            new_html = new_html.replace(f'href="{anchor}"', f'href="{real_url}"')
            changed = True
        if f"href='{anchor}'" in new_html:
            new_html = new_html.replace(f"href='{anchor}'", f"href='{real_url}'")
            changed = True

    for old, new in HTML_EXT_MAP.items():
        if old in new_html:
            new_html = new_html.replace(old, new)
            changed = True

    for old, new in NO_SLASH_MAP.items():
        if old in new_html:
            new_html = new_html.replace(old, new)
            changed = True

    return new_html, changed, "nav links normalized" if changed else "nav ok"


def fix_jsonld(html: str, url: str) -> tuple:
    if url in NO_JSONLD_URLS:
        return html, False, "skipped (non-calculator URL)"

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
    if re.search(r"Last updated\s+\d{4}-\d{2}-\d{2}", html):
        return html, False, "date present"

    if url in NON_CALCULATOR_URLS or "calculator" not in url:
        return html, False, "not a calculator page"

    h1_match = re.search(r"<h1[^>]*>.*?</h1>", html, re.DOTALL | re.IGNORECASE)
    if not h1_match:
        return html, False, "no h1 to anchor date"

    after_h1 = html[h1_match.end():h1_match.end() + 250].lower()
    if "last updated" in after_h1 or "by emiliano" in after_h1:
        return html, False, "date-like text already present"

    date_line = (
        f'\n      <p style="color:#777;font-size:.85rem;margin:.25rem 0 1.25rem">'
        f'By {SITE_AUTHOR} · Last updated {SITE_LAST_UPDATED}</p>'
    )
    new_html = html[:h1_match.end()] + date_line + html[h1_match.end():]
    return new_html, True, "date line inserted"


def fix_ga4(html: str, url: str) -> tuple:
    """Insert GA4 snippet if it is missing."""
    if GA4_MEASUREMENT_ID in html:
        return html, False, "GA4 present"

    snippet = (
        f'\n<script async src="https://www.googletagmanager.com/gtag/js?id={GA4_MEASUREMENT_ID}"></script>'
        f'\n<script>window.dataLayer=window.dataLayer||[];'
        f'function gtag(){{dataLayer.push(arguments);}}'
        f"gtag('js',new Date());"
        f"gtag('config','{GA4_MEASUREMENT_ID}');</script>"
    )
    if "</head>" in html:
        new_html = html.replace("</head>", snippet + "\n</head>", 1)
        return new_html, True, "GA4 inserted"
    return html, False, "GA4 could not be inserted (no </head>)"


def fix_faq_schema(html: str, url: str) -> tuple:
    """Generate FAQPage JSON-LD from visible FAQ if missing."""
    m = re.search(
        r'<h2[^>]*>\s*Frequently\s+Asked\s+Questions\s*</h2>(.*?)(?=<section|<footer|</main>)',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return html, False, "no visible FAQ"

    # Skip if FAQPage schema already exists (mismatches are flagged by the linter)
    for sm in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    ):
        try:
            data = json.loads(sm.group(1))
            if isinstance(data, dict) and data.get("@type") == "FAQPage":
                return html, False, "FAQPage schema present"
        except json.JSONDecodeError:
            continue

    faq_html = m.group(1)
    main_entity = []

    # Pattern 1: <h3>Question</h3> followed by <p>Answer</p>
    q_blocks = re.split(r'<h3[^>]*>', faq_html, flags=re.IGNORECASE)[1:]
    for block in q_blocks:
        parts = re.split(r'</h3>', block, maxsplit=1)
        if len(parts) != 2:
            continue
        question = strip_html(parts[0]).strip()
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', parts[1], re.DOTALL | re.IGNORECASE)
        answer = ' '.join(strip_html(p).strip() for p in paragraphs if strip_html(p).strip())
        if question and answer:
            main_entity.append({
                "@type": "Question",
                "name": question,
                "acceptedAnswer": {"@type": "Answer", "text": answer}
            })

    # Pattern 2 (fallback): <div class="faq-question">...</div> + <div class="faq-answer">...</div>
    if not main_entity:
        pairs = re.findall(
            r'<div[^>]*class=["\'][^"\']*faq-question[^"\']*["\'][^>]*>(.*?)</div>'
            r'\s*<div[^>]*class=["\'][^"\']*faq-answer[^"\']*["\'][^>]*>(.*?)</div>',
            faq_html, re.DOTALL | re.IGNORECASE
        )
        for q, a in pairs:
            question = strip_html(q).strip()
            answer = strip_html(a).strip()
            if question and answer:
                main_entity.append({
                    "@type": "Question",
                    "name": question,
                    "acceptedAnswer": {"@type": "Answer", "text": answer}
                })

    if not main_entity:
        return html, False, "no Q&A pairs parsed from visible FAQ"

    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": main_entity
    }
    block = f'\n<script type="application/ld+json">\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n</script>'

    if "</head>" in html:
        new_html = html.replace("</head>", block + "\n</head>", 1)
        return new_html, True, f"FAQPage schema generated ({len(main_entity)} questions)"
    return html, False, "no </head>"


def fix_unclosed_p(html: str, url: str) -> tuple:
    """Close unclosed <p> tags by inserting </p> before the next block element."""
    opens = len(re.findall(r'<p[\s>]', html, re.IGNORECASE))
    closes = len(re.findall(r'</p>', html, re.IGNORECASE))
    if opens <= closes:
        return html, False, "no unclosed <p> found"

    # Mask scripts/styles/comments so we don't touch them
    masked_items = []
    def mask_replacer(m):
        masked_items.append(m.group(0))
        return f'\x00MASK{len(masked_items) - 1}\x00'

    work = re.sub(r'<script\b[^>]*>.*?</script>', mask_replacer, html, flags=re.DOTALL | re.IGNORECASE)
    work = re.sub(r'<style\b[^>]*>.*?</style>', mask_replacer, work, flags=re.DOTALL | re.IGNORECASE)
    work = re.sub(r'<!--.*?-->', mask_replacer, work, flags=re.DOTALL)

    pattern = re.compile(
        r'<p\b[^>]*>((?:(?!</p>)(?!<' + BLOCK_TAGS + r'\b).)*?)(?=<' + BLOCK_TAGS + r'\b)',
        re.DOTALL | re.IGNORECASE
    )

    fixes_applied = 0
    for _ in range(100):
        m = pattern.search(work)
        if not m:
            break
        end = m.end(1)
        work = work[:end] + '</p>' + work[end:]
        fixes_applied += 1

    def unmask_replacer(m):
        return masked_items[int(m.group(1))]

    result = re.sub(r'\x00MASK(\d+)\x00', unmask_replacer, work)

    if fixes_applied == 0:
        return html, False, "no unclosed <p> found (may be at end of file)"

    opens_after = len(re.findall(r'<p[\s>]', result, re.IGNORECASE))
    closes_after = len(re.findall(r'</p>', result, re.IGNORECASE))
    remaining = opens_after - closes_after
    if remaining > 0:
        return result, True, f"closed {fixes_applied} unclosed <p> tag(s); {remaining} still unclosed"
    return result, True, f"closed {fixes_applied} unclosed <p> tag(s)"


def fix_related(html: str, url: str) -> tuple:
    """Insert a Related Calculators section with category  if missing."""
    if url in NON_CALCULATOR_URLS or "calculator" not in url:
        return html, False, "not a calculator page"

    if re.search(r'Related\s+Calculators', html, re.IGNORECASE):
        return html, False, "Related Calculators section present"

    slug = url.strip("/").split("/")[-1]
    category = SLUG_TO_CATEGORY.get(slug)
    if not category:
        return html, False, f"no category mapping for {slug}"

    siblings = [s for s in CATEGORY_SLUGS[category] if s != slug][:8]
    if not siblings:
        return html, False, f"no siblings in {category} category"

    items = '\n'.join(
        f'        <li><a href="/{s}/">{page_name_from_url("/" + s + "/")}</a></li>'
        for s in siblings
    )
    block = (
        '\n    <section class="content-section">\n'
        '      <h2>Related Calculators</h2>\n'
        '      <ul style="padding-left:20px;line-height:1.9;">\n'
        f'{items}\n'
        '      </ul>\n'
        '    </section>\n'
    )

    # Find insertion point. Try </main> first, then fall back to </footer> or </body>.
    insertion_index = -1
    for candidate in ('</main>', '</footer>', '</body>'):
        idx = html.find(candidate)
        if idx != -1:
            insertion_index = idx
            break

    if insertion_index == -1:
        return html, False, "no </main>, </footer>, or </body> found"

    # Prefer inserting before the last </div> that precedes the insertion point
    # (keeps the section inside the .container wrapper for pages without <main>)
    last_div = html.rfind('</div>', 0, insertion_index)
    if last_div != -1 and insertion_index - last_div < 400:
        new_html = html[:last_div] + block + html[last_div:]
    else:
        new_html = html[:insertion_index] + block + '\n' + html[insertion_index:]

    return new_html, True, f"Related section added ({len(siblings)} links from {category})"


# Registry — insertion order matters (h1 before date; unclosed_p before faq)
FIX_REGISTRY = {
    "og": fix_og,
    "favicon": fix_favicon,
    "h1": fix_h1,
    "nav": fix_nav,
    "jsonld": fix_jsonld,
    "date": fix_date,
    "ga4": fix_ga4,
    "unclosed_p": fix_unclosed_p,
    "faq": fix_faq_schema,
    "related": fix_related,
}


# ---------- Main ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-root", default=".", help="Root folder containing HTML files")
    ap.add_argument(
        "--fix",
        default="all",
        help="Comma-separated fixes: og,favicon,h1,nav,jsonld,date,ga4,unclosed_p,faq,related,all",
    )
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
