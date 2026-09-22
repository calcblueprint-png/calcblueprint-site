#!/usr/bin/env python3
"""Add complete Open Graph + Twitter Card + favicon to every page missing them."""
import os
import re

SKIP = {"scripts", ".github", "node_modules"}
SITE = "https://calcblueprint.com"


def patch(path):
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    original = html

    # Extract page info
    title_m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    desc_m = re.search(r'<meta name="description" content="(.*?)"', html)
    canon_m = re.search(r'<link rel="canonical" href="(.*?)"', html)

    title = title_m.group(1).strip() if title_m else "CalcBlueprint"
    desc = desc_m.group(1).strip() if desc_m else "Free construction calculators for contractors and DIY."
    canonical = canon_m.group(1).strip() if canon_m else f"{SITE}/"

    to_add = []

    # Open Graph
    if 'property="og:type"' not in html:
        to_add.append('<meta property="og:type" content="website">')
    if 'property="og:url"' not in html:
        to_add.append(f'<meta property="og:url" content="{canonical}">')
    if 'property="og:title"' not in html:
        to_add.append(f'<meta property="og:title" content="{title}">')
    if 'property="og:description"' not in html:
        to_add.append(f'<meta property="og:description" content="{desc}">')
    if 'property="og:image"' not in html:
        to_add.append(f'<meta property="og:image" content="{SITE}/og-image.png">')

    # Twitter Card
    if 'name="twitter:card"' not in html:
        to_add.append('<meta name="twitter:card" content="summary_large_image">')
    if 'name="twitter:url"' not in html:
        to_add.append(f'<meta name="twitter:url" content="{canonical}">')
    if 'name="twitter:title"' not in html:
        to_add.append(f'<meta name="twitter:title" content="{title}">')
    if 'name="twitter:description"' not in html:
        to_add.append(f'<meta name="twitter:description" content="{desc}">')
    if 'name="twitter:image"' not in html:
        to_add.append(f'<meta name="twitter:image" content="{SITE}/og-image.png">')

    # Favicon
    if 'rel="icon"' not in html:
        to_add.append('<link rel="icon" href="/favicon.ico">')

    if not to_add:
        print(f"  ✓ Complete: {path}")
        return False

    if "</head>" not in html:
        print(f"  ✗ No </head>: {path}")
        return False

    block = "\n".join(to_add) + "\n"
    html = html.replace("</head>", block + "</head>", 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  ✅ {path} (+{len(to_add)} tags)")
    return True


def main():
    patched = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for file in files:
            if file == "index.html":
                path = os.path.join(root, file)
                if patch(path):
                    patched += 1
    print(f"\nPatched: {patched}")


if __name__ == "__main__":
    main()
