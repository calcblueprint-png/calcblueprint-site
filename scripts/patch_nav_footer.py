#!/usr/bin/env python3
"""
Add "How It Works" to header nav and footer nav.
Add "Terms" to footer if missing.
Skips pages that already have it.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SKIP_LIST = {
    "how-it-works/index.html",  # already correct
}

# HEADER NAV: insert <a href="/how-it-works/">How It Works</a> before About
HEADER_NAV_PATTERN = re.compile(
    r'(<nav>\s*)<a href="/about/">About</a>',
    re.DOTALL
)
HEADER_NAV_REPLACEMENT = r'\1<a href="/how-it-works/">How It Works</a>\n<a href="/about/">About</a>'

# FOOTER NAV: insert Home at start if missing, How It Works after Home, Terms after Privacy
FOOTER_NAV_PATTERN = re.compile(
    r'<nav>\s*<a href="/">Home</a>\s*<a href="/about/">About</a>\s*<a href="/contact/">Contact</a>\s*<a href="/privacy/">Privacy</a>\s*</nav>',
    re.DOTALL
)
FOOTER_NAV_REPLACEMENT = '''<nav>
<a href="/">Home</a>
<a href="/how-it-works/">How It Works</a>
<a href="/about/">About</a>
<a href="/contact/">Contact</a>
<a href="/privacy/">Privacy</a>
<a href="/terms/">Terms</a>
</nav>'''


def patch(path):
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"error: {e}"

    rel = str(path.relative_to(ROOT)).replace("\\", "/")

    if rel in SKIP_LIST:
        return None

    original = content
    changes = []

    # 1. Header nav — add How It Works
    # Only patch the FIRST <nav> in the document (the header)
    if 'href="/how-it-works/"' not in content:
        header_match = HEADER_NAV_PATTERN.search(content)
        if header_match:
            content = HEADER_NAV_PATTERN.sub(HEADER_NAV_REPLACEMENT, content, count=1)
            changes.append("added How It Works to header nav")

    # 2. Footer nav — rebuild with all 6 links
    if FOOTER_NAV_PATTERN.search(content):
        # Check if it already has how-it-works and terms
        footer_match = FOOTER_NAV_PATTERN.search(content)
        footer_html = footer_match.group(0)
        if '/how-it-works/' not in footer_html or '/terms/' not in footer_html:
            content = FOOTER_NAV_PATTERN.sub(FOOTER_NAV_REPLACEMENT, content, count=1)
            changes.append("rebuilt footer nav with How It Works + Terms")
    else:
        # Fallback: try inline footer pattern
        inline_footer = re.compile(
            r'<footer>\s*<nav>\s*<a href="/">Home</a>\s*<a href="/about/">About</a>\s*<a href="/contact/">Contact</a>\s*<a href="/privacy/">Privacy</a>\s*</nav>',
            re.DOTALL
        )
        if inline_footer.search(content):
            content = inline_footer.sub(
                '<footer>\n<nav>\n<a href="/">Home</a>\n<a href="/how-it-works/">How It Works</a>\n<a href="/about/">About</a>\n<a href="/contact/">Contact</a>\n<a href="/privacy/">Privacy</a>\n<a href="/terms/">Terms</a>\n</nav>',
                content,
                count=1
            )
            changes.append("rebuilt footer nav (inline fallback)")

    if content != original:
        path.write_text(content, encoding="utf-8")
        return changes
    return None


def main():
    patched = []
    errors = []
    skipped = []

    for p in sorted(ROOT.rglob("*.html")):
        if ".git" in p.parts:
            continue
        result = patch(p)
        rel = p.relative_to(ROOT)
        if result is None:
            skipped.append(rel)
        elif isinstance(result, str) and result.startswith("error"):
            errors.append((rel, result))
        else:
            patched.append((rel, result))

    print(f"\n=== PATCHED {len(patched)} FILES ===")
    for f, changes in patched:
        print(f"  ✓ {f}")
        for c in changes:
            print(f"      - {c}")

    print(f"\n=== SKIPPED {len(skipped)} FILES ===")
    for f in skipped[:10]:
        print(f"  - {f}")
    if len(skipped) > 10:
        print(f"  ... and {len(skipped) - 10} more")

    if errors:
        print(f"\n=== ERRORS ({len(errors)}) ===")
        for f, e in errors:
            print(f"  ✗ {f}: {e}")


if __name__ == "__main__":
    main()
