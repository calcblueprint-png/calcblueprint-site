#!/usr/bin/env python3
"""
Add author byline to all calculator pages on calcblueprint.com.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

BYLINE = '<p style="color:#777;font-size:.85rem;margin:.5rem 0 1.25rem">By Emiliano · Last updated 2026-09-27</p>'

SKIP_LIST = {
    "index.html",
    "404.html",
    "about/index.html",
    "how-it-works/index.html",
    "contact/index.html",
    "privacy/index.html",
    "terms/index.html",
    "thank-you/index.html",
}

H1_REGEX = re.compile(r'(\n[ \t]*)(<h1[^>]*>.*?</h1>)', re.DOTALL)


def patch(path):
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        return f"error: {e}"

    rel = str(path.relative_to(ROOT)).replace("\\", "/")

    if rel in SKIP_LIST:
        return None

    if 'By Emiliano · Last updated' in content:
        return None

    match = H1_REGEX.search(content)
    if not match:
        return "no-h1"

    indent = match.group(1)
    h1_block = match.group(2)
    replacement = f"{indent}{h1_block}\n{indent}{BYLINE}"

    content = content[:match.start()] + replacement + content[match.end():]
    path.write_text(content, encoding="utf-8")
    return "added byline"


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
        if isinstance(result, str) and result.startswith("error"):
            errors.append((rel, result))
        elif result == "no-h1":
            errors.append((rel, "no H1 found"))
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
