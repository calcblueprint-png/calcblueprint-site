#!/usr/bin/env python3
"""
Replace broken anchor hrefs (#about, #contact, etc.) with real URLs.
Scans every HTML file and reports any anchor it can't map.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Mapping: broken anchor -> real URL
ANCHOR_MAP = {
    '#home': '/',
    '#about': '/about/',
    '#contact': '/contact/',
    '#privacy': '/privacy/',
    '#terms': '/terms/',
    '#how-it-works': '/how-it-works/',
    '#howitworks': '/how-it-works/',
    '#calculators': '/',
    '#calc': '/',
    '#main': '/',
    '#top': '/',
    '#calculator': '/',
}

# Match href="#..."
ANCHOR_REGEX = re.compile(r'href="(#[^"]*)"')


def patch(path):
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return {"error": str(e)}

    original = content
    changes = []
    unknown = []

    def replace_anchor(match):
        anchor = match.group(1)
        if anchor in ANCHOR_MAP:
            replacement = ANCHOR_MAP[anchor]
            changes.append(f"{anchor} → {replacement}")
            return f'href="{replacement}"'
        else:
            unknown.append(anchor)
            return match.group(0)

    content = ANCHOR_REGEX.sub(replace_anchor, content)

    if content != original:
        path.write_text(content, encoding="utf-8")

    return {
        "changes": changes,
        "unknown": unknown,
        "modified": content != original,
    }


def main():
    patched = []
    unknown_hits = []

    for p in sorted(ROOT.rglob("*.html")):
        if ".git" in p.parts:
            continue
        result = patch(p)
        rel = p.relative_to(ROOT)
        if "error" in result:
            print(f"  ERROR {rel}: {result['error']}")
            continue
        if result["modified"]:
            patched.append((rel, result["changes"]))
        if result["unknown"]:
            unique = sorted(set(result["unknown"]))
            unknown_hits.append((rel, unique))

    print(f"\n=== PATCHED {len(patched)} FILES ===")
    for f, changes in patched:
        print(f"  ✓ {f}")
        for c in changes:
            print(f"      - {c}")

    if unknown_hits:
        print(f"\n=== UNKNOWN ANCHORS ({len(unknown_hits)} files) ===")
        print("These anchors weren't in the mapping — review manually:")
        for f, anchors in unknown_hits:
            print(f"  ⚠ {f}: {', '.join(anchors)}")


if __name__ == "__main__":
    main()
