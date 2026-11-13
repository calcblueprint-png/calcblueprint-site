#!/usr/bin/env python3
"""
CalcBlueprint SEO Linter
Runs structural + on-page SEO checks against every HTML file.

Usage:
    python scripts/seo_lint.py                    # default site root
    python scripts/seo_lint.py --site-root .      # explicit
    python scripts/seo_lint.py --json             # machine-readable output
    python scripts/seo_lint.py --fail-on=warn     # stricter CI gate

Exit codes:
    0 = all checks passed
    1 = critical failures OR (warn failures with --fail-on=warn)
    2 = script/config error
"""

import argparse
import html as html_module
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

# ---------- Configuration ----------

SITE_DOMAIN = "https://calcblueprint.com"
DEFAULT_OG_IMAGE = f"{SITE_DOMAIN}/og-image.png"

# Current year — used to detect future dates that hurt trust signals
CURRENT_YEAR = "2026"

# Directories to skip when walking the tree
IGNORE_DIRS = {
    ".git", ".github", "node_modules", "scripts", "assets", "img",
    "images", "css", "js", "static", "dist", "build", "__pycache__",
    ".venv", "venv", "env",
}

# Files to skip (already-fixed anchors, templates, etc.)
IGNORE_FILES = {
    "404.html",
}

# Real URLs that #anchor links should map to
ANCHOR_MAP = {
    "#about": "/about/",
    "#contact": "/contact/",
    "#privacy": "/privacy/",
    "#terms": "/terms/",
    "#how-it-works": "/how-it-works/",
}

REQUIRED_OG = ["og:type", "og:url", "og:title", "og:description", "og:image"]
REQUIRED_TWITTER = ["twitter:card", "twitter:title", "twitter:description", "twitter:image"]

# Non-calculator pages (skip calculator-specific checks)
NON_CALCULATOR_PAGES = {"/", "/about/", "/contact/", "/privacy/", "/terms/", "/how-it-works/"}

# Orphan threshold — calculator pages should have at least this many inbound links
MIN_INBOUND_LINKS = 3


# ---------- Page loading ----------

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
    """Map a file path to its expected canonical URL."""
    rel = file_path.relative_to(site_root)
    parts = rel.parts
    if rel.name == "index.html":
        if len(parts) == 1:
            return "/"
        return "/" + "/".join(parts[:-1]) + "/"
    return "/" + rel.stem + "/"


# ---------- Helpers ----------

def extract(html: str, pattern: str, flags=re.IGNORECASE | re.DOTALL):
    m = re.search(pattern, html, flags)
    return m.group(1).strip() if m else None


def count(html: str, pattern: str, flags=re.IGNORECASE) -> int:
    return len(re.findall(pattern, html, flags))


def strip_html(text: str) -> str:
    """Strip HTML tags and decode entities, then collapse whitespace."""
    text = re.sub(r'<[^>]+>', '', text)
    text = html_module.unescape(text)
    return re.sub(r'\s+', ' ', text).strip()


# ---------- Individual checks ----------

def check_title(html: str):
    title = extract(html, r"<title>(.*?)</title>")
    if not title:
        return "critical", "Missing <title>"
    if len(title) < 30:
        return "warn", f"Title too short ({len(title)} chars): {title!r}"
    if len(title) > 65:
        return "warn", f"Title too long ({len(title)} chars)"
    return None, None


def check_description(html: str):
    desc = extract(html, r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']')
    if not desc:
        return "critical", "Missing meta description"
    if len(desc) < 120:
        return "warn", f"Description too short ({len(desc)} chars)"
    if len(desc) > 165:
        return "warn", f"Description too long ({len(desc)} chars)"
    return None, None


def check_h1(html: str):
    n = count(html, r"<h1[\s>]")
    if n == 0:
        return "critical", "Missing <h1>"
    if n > 1:
        return "warn", f"Multiple <h1> tags ({n})"
    return None, None


def check_canonical(html: str, expected: str):
    canonical = extract(html, r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']')
    if not canonical:
        return "critical", "Missing canonical"
    expected_full = f"{SITE_DOMAIN}{expected}"
    if canonical != expected_full:
        return "critical", f"Canonical mismatch: {canonical} (expected {expected_full})"
    return None, None


def check_og_tags(html: str):
    missing = [tag for tag in REQUIRED_OG if f'property="{tag}"' not in html and f"property='{tag}'" not in html]
    if missing:
        return "warn", f"Missing OG tags: {', '.join(missing)}"
    return None, None


def check_twitter_tags(html: str):
    missing = [tag for tag in REQUIRED_TWITTER if f'name="{tag}"' not in html and f"name='{tag}'" not in html]
    if missing:
        return "warn", f"Missing Twitter tags: {', '.join(missing)}"
    return None, None


def check_favicon(html: str):
    if 'rel="icon"' not in html and "rel='icon'" not in html:
        return "warn", "Missing favicon link"
    return None, None


def check_webapp_jsonld(html: str):
    for m in re.finditer(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL):
        if '"WebApplication"' in m.group(1) or "'WebApplication'" in m.group(1):
            return None, None
    return "warn", "Missing WebApplication JSON-LD"


def check_ga4(html: str):
    if "G-DHN9J7B497" not in html:
        return "warn", "Missing GA4 tag"
    return None, None


def check_anchor_links(html: str):
    issues = []
    for anchor, real_url in ANCHOR_MAP.items():
        if f'href="{anchor}"' in html or f"href='{anchor}'" in html:
            issues.append(f"{anchor} → {real_url}")
    if issues:
        return "warn", f"Nav uses anchors instead of URLs: {', '.join(issues)}"
    return None, None


def check_internal_links(html: str, site_root: Path):
    """Report hrefs like /foo/ that don't resolve to any file."""
    hrefs = re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE)
    broken = []
    for href in hrefs:
        if not href.startswith("/") or href.startswith("//"):
            continue
        if href.startswith("#"):
            continue
        clean = href.split("?")[0].split("#")[0]
        if clean in ("/", ""):
            candidate = site_root / "index.html"
        elif clean.endswith("/"):
            candidate = site_root / clean.strip("/") / "index.html"
        else:
            candidate_1 = site_root / (clean.lstrip("/") + ".html")
            candidate_2 = site_root / clean.lstrip("/") / "index.html"
            candidate = candidate_1 if candidate_1.exists() else candidate_2
        if not candidate.exists():
            broken.append(href)
    if broken:
        return "critical", f"Broken internal links: {', '.join(sorted(set(broken)))}"
    return None, None


def check_last_updated(html: str, url: str = ""):
    if url in NON_CALCULATOR_PAGES:
        return None, None
    if re.search(r"Last updated\s+\d{4}-\d{2}-\d{2}", html):
        return None, None
    return "warn", "Missing 'Last updated YYYY-MM-DD' line"


def check_footer_citation(html: str, url: str = ""):
    if url in NON_CALCULATOR_PAGES:
        return None, None
    if "Formula source" in html or "Formula based on" in html:
        return None, None
    return "warn", "Missing formula source citation in footer"


def check_404_page(html: str, file_path: Path):
    """Special checks for 404 pages."""
    if file_path.name == "404.html":
        if 'name="robots"' not in html or "noindex" not in html:
            return "warn", "404 page should have <meta name=\"robots\" content=\"noindex\">"
    return None, None


# ---------- Structural integrity checks ----------

def check_faq_schema(html: str, url: str) -> tuple:
    """Visible FAQ section must have matching FAQPage JSON-LD."""
    m = re.search(
        r'<h2[^>]*>\s*Frequently\s+Asked\s+Questions\s*</h2>(.*?)(?=<section|<footer|</main>)',
        html, re.DOTALL | re.IGNORECASE
    )
    if not m:
        return None, None

    visible = re.findall(r'<h3[^>]*>(.*?)</h3>', m.group(1), re.DOTALL | re.IGNORECASE)
    visible_qs = [strip_html(q).strip() for q in visible if strip_html(q).strip()]
    if not visible_qs:
        return None, None

    schema_qs = []
    for sm in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    ):
        try:
            data = json.loads(sm.group(1))
            if isinstance(data, dict) and data.get("@type") == "FAQPage":
                for q in data.get("mainEntity", []):
                    name = q.get("name", "").strip()
                    if name:
                        schema_qs.append(name)
        except json.JSONDecodeError:
            continue

    if not schema_qs:
        return "critical", f"Visible FAQ ({len(visible_qs)} questions) but no FAQPage JSON-LD"
    unmatched = [q for q in visible_qs if q not in schema_qs]
    if unmatched:
        return "critical", f"FAQ schema mismatch: {len(unmatched)}/{len(visible_qs)} visible questions not in schema"
    return None, None


def check_unclosed_p(html: str) -> tuple:
    """Detect unclosed <p> tags (invalid HTML that breaks FAQ schema matching)."""
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r'<style[^>]*>.*?</style>', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    opens = len(re.findall(r'<p[\s>]', cleaned, re.IGNORECASE))
    closes = len(re.findall(r'</p>', cleaned, re.IGNORECASE))
    if opens > closes:
        return "critical", f"{opens - closes} unclosed <p> tag(s) — invalid HTML"
    return None, None


def check_jsonld_validity(html: str) -> tuple:
    """Every JSON-LD block must parse as valid JSON."""
    for i, m in enumerate(re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )):
        try:
            json.loads(m.group(1))
        except json.JSONDecodeError as e:
            return "critical", f"Invalid JSON-LD block #{i+1}: {str(e)[:80]}"
    return None, None


def check_related_calculators(html: str, url: str) -> tuple:
    """Calculator pages must have a Related Calculators section."""
    if url in NON_CALCULATOR_PAGES or "calculator" not in url:
        return None, None
    if not re.search(r'Related\s+Calculators', html, re.IGNORECASE):
        return "warn", "Missing Related Calculators section"
    return None, None


def check_desc_differs_from_title(html: str) -> tuple:
    """Description must not be identical to title."""
    title = extract(html, r"<title>(.*?)</title>")
    desc = extract(html, r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']')
    if title and desc and title.strip() == desc.strip():
        return "warn", "Description is identical to title"
    return None, None


def check_future_dates(html: str) -> tuple:
    """Flag any year 2027+ in dates, copyright, or JSON-LD — future dates hurt trust signals."""
    FUTURE_YEAR = r'20(?:2[7-9]|[3-9]\d)'
    issues = []

    # "Last updated YYYY-MM-DD" lines with a future year
    for m in re.finditer(rf'Last updated\s+({FUTURE_YEAR})', html):
        issues.append(f"Last updated {m.group(1)}")

    # Copyright "© YYYY" or "&copy; YYYY"
    for m in re.finditer(rf'(?:©|&copy;)\s*({FUTURE_YEAR})', html):
        issues.append(f"© {m.group(1)}")

    # JSON-LD datePublished / dateModified
    for m in re.finditer(rf'"(?:datePublished|dateModified)"\s*:\s*"({FUTURE_YEAR})', html):
        issues.append(f"schema date {m.group(1)}")

    # OpenGraph article:published_time / modified_time
    for m in re.finditer(
        rf'<meta\s+property=["\']article:(?:published|modified)_time["\']\s+content=["\']({FUTURE_YEAR})',
        html
    ):
        issues.append(f"OG article date {m.group(1)}")

    if issues:
        unique = sorted(set(issues))
        return "warn", f"Future year(s) 2027+: {', '.join(unique)}"
    return None, None


# ---------- Main ----------

def lint_page(file_path: Path, site_root: Path):
    html = file_path.read_text(encoding="utf-8", errors="replace")
    expected = expected_url(file_path, site_root)

    results = []  # (severity, message)

    for check_fn, args in [
        (check_title, (html,)),
        (check_description, (html,)),
        (check_h1, (html,)),
        (check_canonical, (html, expected)),
        (check_og_tags, (html,)),
        (check_twitter_tags, (html,)),
        (check_favicon, (html,)),
        (check_webapp_jsonld, (html,)),
        (check_ga4, (html,)),
        (check_anchor_links, (html,)),
        (check_internal_links, (html, site_root)),
        (check_last_updated, (html, expected)),
        (check_footer_citation, (html, expected)),
        (check_404_page, (html, file_path)),
        (check_faq_schema, (html, expected)),
        (check_unclosed_p, (html,)),
        (check_jsonld_validity, (html,)),
        (check_related_calculators, (html, expected)),
        (check_desc_differs_from_title, (html,)),
        (check_future_dates, (html,)),
    ]:
        sev, msg = check_fn(*args)
        if sev:
            results.append((sev, msg))

    critical = sum(1 for s, _ in results if s == "critical")
    warn = sum(1 for s, _ in results if s == "warn")
    score = max(0, 100 - critical * 25 - warn * 5)

    return {
        "file": str(file_path.relative_to(site_root.parent)),
        "url": expected,
        "score": score,
        "critical": critical,
        "warn": warn,
        "issues": results,
    }


def compute_inbound_links(files, site_root: Path) -> Counter:
    """Build a count of internal inbound links per URL across all pages."""
    inbound = Counter()
    for path in files:
        try:
            html = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        for href in re.findall(r'<a\s+[^>]*href=["\']([^"\']+)["\']', html, re.IGNORECASE):
            if not href.startswith("/") or href.startswith("//"):
                continue
            if href.startswith("#"):
                continue
            clean = href.split("?")[0].split("#")[0]
            if clean in ("/", ""):
                inbound["/"] += 1
            elif clean.endswith("/"):
                inbound[clean] += 1
    return inbound


def apply_orphan_check(results, inbound: Counter):
    """Flag calculator pages with too few inbound internal links."""
    for r in results:
        if r["url"] in NON_CALCULATOR_PAGES:
            continue
        count = inbound.get(r["url"], 0)
        if count >= MIN_INBOUND_LINKS:
            continue
        if count == 0:
            sev, msg = "critical", "Orphan page: 0 inbound internal links"
        else:
            sev, msg = "warn", f"Only {count} inbound internal link(s) — target {MIN_INBOUND_LINKS}+"
        r["issues"].append((sev, msg))
        if sev == "critical":
            r["critical"] += 1
            r["score"] = max(0, r["score"] - 25)
        else:
            r["warn"] += 1
            r["score"] = max(0, r["score"] - 5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-root", default=".", help="Root folder containing HTML files")
    ap.add_argument("--json", action="store_true", help="Machine-readable output")
    ap.add_argument("--fail-on", choices=["critical", "warn"], default="critical",
                    help="Exit 1 if issues at this level exist")
    ap.add_argument("--no-orphan-check", action="store_true",
                    help="Skip inbound-link orphan detection")
    args = ap.parse_args()

    site_root = Path(args.site_root).resolve()
    if not site_root.exists():
        print(f"error: site root does not exist: {site_root}", file=sys.stderr)
        sys.exit(2)

    files = find_html_files(site_root)
    if not files:
        print(f"error: no HTML files found under {site_root}", file=sys.stderr)
        sys.exit(2)

    results = [lint_page(f, site_root) for f in files]

    if not args.no_orphan_check:
        inbound = compute_inbound_links(files, site_root)
        apply_orphan_check(results, inbound)

    total_critical = sum(r["critical"] for r in results)
    total_warn = sum(r["warn"] for r in results)
    avg_score = sum(r["score"] for r in results) / len(results)

    if args.json:
        print(json.dumps({"results": results,
                          "summary": {"files": len(results),
                                      "critical": total_critical,
                                      "warn": total_warn,
                                      "avg_score": round(avg_score, 1)}},
                         indent=2))
    else:
        print(f"CalcBlueprint SEO Lint — {len(files)} pages\n")
        for r in results:
            status = "OK " if r["score"] == 100 else f"{r['score']:>3}"
            icon = "✓" if r["score"] == 100 else ("✗" if r["critical"] else "!")
            print(f"[{icon}] {status}/100  {r['url']}")
            for sev, msg in r["issues"]:
                marker = "    CRIT" if sev == "critical" else "    warn"
                print(f"{marker}  {msg}")
        print(f"\nSummary: {len(files)} files | "
              f"{total_critical} critical | {total_warn} warnings | "
              f"avg score {avg_score:.1f}/100")

    exit_code = 0
    if args.fail_on == "critical" and total_critical > 0:
        exit_code = 1
    elif args.fail_on == "warn" and (total_critical > 0 or total_warn > 0):
        exit_code = 1
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
