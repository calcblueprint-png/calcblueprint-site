#!/usr/bin/env python3
"""Add FAQPage schema to calculator pages with various FAQ structures."""
import os
import re
import json

SKIP = {"scripts", ".github", "node_modules"}


def extract_faqs(html):
    """Extract 3 Q&A pairs from the FAQ section using multiple pattern attempts."""
    faqs = []

    # Try multiple section heading variations
    section_markers = [
        "Frequently Asked Questions",
        "FAQ",
        "Common Questions",
    ]

    idx = -1
    for marker in section_markers:
        idx = html.find(marker)
        if idx != -1:
            break

    if idx == -1:
        return faqs

    section = html[idx:idx + 12000]

    # Pattern 1: <h3>Question</h3><p>Answer</p>
    matches = re.findall(
        r"<h[234][^>]*>(.*?)</h[234]>\s*<p[^>]*>(.*?)</p>",
        section,
        re.DOTALL
    )

    # Pattern 2: <details><summary>Question</summary><p>Answer</p></details>
    if len(matches) < 3:
        details_matches = re.findall(
            r"<summary[^>]*>(.*?)</summary>\s*<p[^>]*>(.*?)</p>",
            section,
            re.DOTALL
        )
        matches.extend(details_matches)

    # Pattern 3: <strong>Question</strong> followed by <p>Answer</p>
    if len(matches) < 3:
        strong_matches = re.findall(
            r"<strong[^>]*>(.*?)</strong>\s*(?:<br\s*/?>)?\s*<p[^>]*>(.*?)</p>",
            section,
            re.DOTALL
        )
        matches.extend(strong_matches)

    for q, a in matches[:3]:
        q_clean = re.sub(r"<[^>]+>", "", q).strip()
        a_clean = re.sub(r"<[^>]+>", "", a).strip()
        # Skip if question doesn't look like a question
        if not q_clean or not a_clean:
            continue
        if len(q_clean) < 10 or len(q_clean) > 200:
            continue
        faqs.append((q_clean, a_clean))
        if len(faqs) >= 3:
            break

    return faqs


def patch(path):
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()

    if "FAQPage" in html:
        print(f"  Already has FAQPage: {path}")
        return False

    faqs = extract_faqs(html)
    if len(faqs) < 3:
        print(f"  Not enough FAQs ({len(faqs)}): {path}")
        return False

    schema = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": q,
                "acceptedAnswer": {"@type": "Answer", "text": a}
            }
            for q, a in faqs
        ]
    }

    script_block = (
        '\n<script type="application/ld+json">\n'
        + json.dumps(schema, separators=(",", ":"))
        + '\n</script>\n'
    )

    html = html.replace("</head>", script_block + "</head>", 1)

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  Patched: {path}")
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
