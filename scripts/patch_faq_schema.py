#!/usr/bin/env python3
"""Add FAQPage schema to calculator pages with various FAQ structures."""
import os
import re
import json

SKIP = {"scripts", ".github", "node_modules"}


def clean(text):
    text = re.sub(r"<[^>]+>", "", text)
    text = text.replace("&pi;", "pi").replace("&amp;", "&")
    text = text.replace("&nbsp;", " ").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&deg;", " degrees").replace("&#39;", "'").replace("&quot;", '"')
    return text.strip()


def extract_faqs(html):
    """Try every known FAQ structure and return the first 3 Q&A pairs found."""
    faqs = []

    # Find FAQ section
    section_markers = ["Frequently Asked Questions", "FAQ", "Common Questions"]
    idx = -1
    for marker in section_markers:
        idx = html.find(marker)
        if idx != -1:
            break

    if idx == -1:
        return faqs

    section = html[idx:idx + 15000]

    # Pattern 1: <p class="faq-question">Q</p><p class="faq-answer">A</p>
    matches = re.findall(
        r'<p[^>]*class="faq-question"[^>]*>(.*?)</p>\s*<p[^>]*class="faq-answer"[^>]*>(.*?)</p>',
        section,
        re.DOTALL | re.IGNORECASE
    )

    # Pattern 2: <p class="faq-question">Q</p><p>A</p> (plain answer paragraph)
    if len(matches) < 3:
        p_matches = re.findall(
            r'<p[^>]*class="faq-question"[^>]*>(.*?)</p>\s*<p[^>]*>(.*?)</p>',
            section,
            re.DOTALL | re.IGNORECASE
        )
        for q, a in p_matches:
            # Skip if this is already captured (answer with faq-answer class)
            if not any(q.strip() == existing[0].strip() for existing in matches):
                matches.append((q, a))

    # Pattern 3: <h3>Q</h3><p>A</p> or <h4>Q</h4><p>A</p>
    if len(matches) < 3:
        h_matches = re.findall(
            r"<h[234][^>]*>(.*?)</h[234]>\s*<p[^>]*>(.*?)</p>",
            section,
            re.DOTALL
        )
        matches.extend(h_matches)

    # Pattern 4: <details><summary>Q</summary><p>A</p>
    if len(matches) < 3:
        details_matches = re.findall(
            r"<summary[^>]*>(.*?)</summary>\s*<p[^>]*>(.*?)</p>",
            section,
            re.DOTALL
        )
        matches.extend(details_matches)

    for q, a in matches:
        q_clean = clean(q)
        a_clean = clean(a)
        if not q_clean or not a_clean:
            continue
        if len(q_clean) < 10 or len(q_clean) > 200:
            continue
        if len(a_clean) < 20:
            continue
        # Skip if the "answer" is actually another question
        if a_clean.lower().endswith("?") and len(a_clean) < 100:
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
