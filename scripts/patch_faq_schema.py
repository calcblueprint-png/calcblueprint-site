#!/usr/bin/env python3
"""Add FAQPage schema to calculator pages that have FAQ content but no FAQ schema."""
import os
import re
import json

SKIP = {"scripts", ".github", "node_modules"}


def extract_faqs(html):
    """Extract 3 Q&A pairs from the FAQ section."""
    faqs = []
    idx = html.find("Frequently Asked Questions")
    if idx == -1:
        return faqs
    section = html[idx:idx + 8000]

    matches = re.findall(
        r"<h3[^>]*>(.*?)</h3>\s*<p[^>]*>(.*?)</p>",
        section,
        re.DOTALL
    )
    for q, a in matches[:3]:
        q_clean = re.sub(r"<[^>]+>", "", q).strip()
        a_clean = re.sub(r"<[^>]+>", "", a).strip()
        if q_clean and a_clean:
            faqs.append((q_clean, a_clean))
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
        + "\n</script>\n"
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
