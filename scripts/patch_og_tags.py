#!/usr/bin/env python3
"""One-time patch: add OG + Twitter tags to pages missing them."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://calcblueprint.com"
OG_IMAGE = f"{BASE_URL}/og-image.png"

HEAD_CLOSE = re.compile(r'</head>', re.IGNORECASE)
TITLE_PATTERN = re.compile(r'<title>([^<]+)</title>', re.IGNORECASE)
DESC_PATTERN = re.compile(r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']+)["\']', re.IGNORECASE)
CANONICAL_PATTERN = re.compile(r'<link\s+rel=["\']canonical["\']\s+href=["\']([^"\']+)["\']', re.IGNORECASE)
OG_TITLE_PATTERN = re.compile(r'<meta\s+property=["\']og:title["\']', re.IGNORECASE)


def slug_to_url(path):
    rel = path.relative_to(ROOT)
    if len(rel.parts) == 1:
        return f"{BASE_URL}/"
    return f"{BASE_URL}/{rel.parts[0]}/"


def build_og_block(title, desc, url):
    title = title.replace('"', '&quot;')
    desc = desc.replace('"', '&quot;')
    return "\n".join([
        '<meta property="og:type" content="website">',
        f'<meta property="og:url" content="{url}">',
        f'<meta property="og:title" content="{title}">',
        f'<meta property="og:description" content="{desc}">',
        f'<meta property="og:image" content="{OG_IMAGE}">',
        '<meta name="twitter:card" content="summary_large_image">',
        f'<meta name="twitter:title" content="{title}">',
        f'<meta name="twitter:description" content="{desc}">',
        f'<meta name="twitter:image" content="{OG_IMAGE}">',
    ])


def patch(path):
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"error: {e}"

    if OG_TITLE_PATTERN.search(content):
        return None

    title_match = TITLE_PATTERN.search(content)
    desc_match = DESC_PATTERN.search(content)
    canonical_match = CANONICAL_PATTERN.search(content)

    title = title_match.group(1).strip() if title_match else "CalcBlueprint"
    desc = desc_match.group(1).strip() if desc_match else "Free construction calculators."
    url = canonical_match.group(1).strip() if canonical_match else slug_to_url(path)

    og_block = build_og_block(title, desc, url)
    head_close = HEAD_CLOSE.search(content)
    if not head_close:
        return "no-head"

    content = content[:head_close.start()] + og_block + "\n" + content[head_close.start():]
    path.write_text(content, encoding="utf-8")
    return "added OG tags"


def main():
    patched = []
    errors = []
    for p in sorted(ROOT.rglob("*.html")):
        if ".git" in p.parts:
            continue
        result = patch(p)
        rel = p.relative_to(ROOT)
        if result is None:
            continue
        if isinstance(result, str) and (result.startswith("error") or result == "no-head"):
            errors.append((rel, result))
        else:
            patched.append(rel)

    print(f"\n=== PATCHED {len(patched)} FILES ===")
    for f in patched:
        print(f"  ✓ {f}")
    if errors:
        print(f"\n=== ERRORS ({len(errors)}) ===")
        for f, e in errors:
            print(f"  ✗ {f}: {e}")


if __name__ == "__main__":
    main()
