#!/usr/bin/env python3
"""Add JSON-LD structured data to info pages that don't have it."""
import os
import re
import json

SITE = "https://calcblueprint.com"
SITE_NAME = "CalcBlueprint"

SKIP = {"scripts", ".github", "node_modules"}

SCHEMA_BY_FOLDER = {
    "": "homepage",
    "about": "about",
    "contact": "contact",
    "privacy": "webpage",
    "terms": "webpage",
}


def build_schema(kind, page_url, title, description):
    if kind == "homepage":
        return {
            "@context": "https://schema.org",
            "@graph": [
                {
                    "@type": "WebSite",
                    "name": SITE_NAME,
                    "url": SITE,
                    "description": description,
                },
                {
                    "@type": "Organization",
                    "name": SITE_NAME,
                    "url": SITE,
                    "logo": f"{SITE}/og-image.png",
                },
            ],
        }
    elif kind == "about":
        return {
            "@context": "https://schema.org",
            "@type": "AboutPage",
            "name": title,
            "url": page_url,
            "description": description,
            "mainEntity": {
                "@type": "Organization",
                "name": SITE_NAME,
                "url": SITE,
                "logo": f"{SITE}/og-image.png",
            },
        }
    elif kind == "contact":
        return {
            "@context": "https://schema.org",
            "@type": "ContactPage",
            "name": title,
            "url": page_url,
            "description": description,
        }
    else:
        return {
            "@context": "https://schema.org",
            "@type": "WebPage",
            "name": title,
            "url": page_url,
            "description": description,
            "isPartOf": {"@type": "WebSite", "name": SITE_NAME, "url": SITE},
        }


def patch(path, folder):
    if folder not in SCHEMA_BY_FOLDER:
        return False

    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    original = html

    head_match = re.search(r"<head>(.*?)</head>", html, re.DOTALL)
    if not head_match:
        print(f"  ✗ No <head>: {path}")
        return False
    head = head_match.group(1)

    if "application/ld+json" in head:
        print(f"  ✓ Already has schema: {path}")
        return False

    title_m = re.search(r"<title>(.*?)</title>", html, re.DOTALL)
    desc_m = re.search(r'<meta name="description" content="(.*?)"', html)
    title = title_m.group(1).strip() if title_m else SITE_NAME
    desc = desc_m.group(1).strip() if desc_m else ""

    page_url = f"{SITE}/{folder}/" if folder else f"{SITE}/"
    kind = SCHEMA_BY_FOLDER[folder]
    schema = build_schema(kind, page_url, title, desc)

    script_block = (
        '\n<script type="application/ld+json">\n'
        + json.dumps(schema, separators=(",", ":"))
        + "\n</script>\n"
    )

    html = html.replace("</head>", script_block + "</head>", 1)

    if html != original:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"  ✅ Added {kind} schema: {path}")
        return True
    return False


def main():
    patched = 0
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for file in files:
            if file == "index.html":
                folder = os.path.basename(root) if root != "." else ""
                path = os.path.join(root, file)
                if patch(path, folder):
                    patched += 1
    print(f"\nPatched: {patched}")


if __name__ == "__main__":
    main()
