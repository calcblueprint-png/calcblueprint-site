#!/usr/bin/env python3
"""
Zero-cost GEO (Generative Engine Optimization) audit.
Checks AI crawler access, llms.txt, schema, and citability.
Runs on GitHub Actions with no paid APIs.
"""
import os
import re
import json
import urllib.request
import urllib.error
import time
from xml.etree import ElementTree

try:
    from bs4 import BeautifulSoup
except ImportError:
    os.system("pip install beautifulsoup4")
    from bs4 import BeautifulSoup

SITE_URL = os.environ.get("SITE_URL", "https://calcblueprint.com")
SITEMAP_URL = f"{SITE_URL}/sitemap.xml"
REPORT_FILE = "geo_report.json"

AI_CRAWLERS = [
    "GPTBot",
    "ChatGPT-User",
    "ClaudeBot",
    "Claude-Web",
    "PerplexityBot",
    "Google-Extended",
    "anthropic-ai",
    "CCBot",
    "Bytespider",
    "Amazonbot",
]

UA = "Mozilla/5.0 (compatible; GEOAuditBot/1.0)"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.read().decode("utf-8", errors="replace")


def get_sitemap_urls():
    try:
        status, xml = fetch(SITEMAP_URL)
        root = ElementTree.fromstring(xml)
        ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        return [loc.text for loc in root.findall(".//sm:loc", ns)]
    except Exception as e:
        print(f"Sitemap failed: {e}")
        return []


def check_robots():
    print("\n=== AI CRAWLER ACCESS ===")
    try:
        status, robots = fetch(f"{SITE_URL}/robots.txt")
    except Exception as e:
        return {"error": str(e), "blocked": []}

    blocked = []
    for crawler in AI_CRAWLERS:
        pattern = rf"User-agent:\s*{crawler}\s*\n(.*?)(?=\nUser-agent|\Z)"
        match = re.search(pattern, robots, re.IGNORECASE | re.DOTALL)
        if match and "Disallow: /" in match.group(1):
            blocked.append(crawler)
            print(f"  BLOCKED: {crawler}")
        else:
            print(f"  Allowed: {crawler}")

    return {"blocked": blocked, "robots_content": robots[:2000]}


def check_llms_txt():
    print("\n=== LLMS.TXT ===")
    try:
        status, content = fetch(f"{SITE_URL}/llms.txt")
        if status == 200:
            lines = content.split("\n")
            has_title = any(l.startswith("# ") for l in lines)
            has_description = any(l.startswith("> ") for l in lines)
            has_sections = any(l.startswith("## ") for l in lines)
            print(f"  Found ({len(lines)} lines)")
            print(f"  Title: {has_title}")
            print(f"  Description: {has_description}")
            print(f"  Sections: {has_sections}")
            return {"found": True, "lines": len(lines), "title": has_title, "desc": has_description, "sections": has_sections}
    except Exception:
        pass
    print("  Missing")
    return {"found": False}


def check_schema(soup):
    print("\n=== SCHEMA ===")
    schemas = []
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if "@graph" in data:
                    for node in data["@graph"]:
                        schemas.append(node.get("@type", "Unknown"))
                else:
                    schemas.append(data.get("@type", "Unknown"))
        except Exception:
            pass
    print(f"  Schema types found: {', '.join(schemas) if schemas else 'None'}")
    return schemas


def check_citability(soup):
    print("\n=== CITABILITY ===")

    main = soup.find("main") or soup.find("article") or soup.body
    if not main:
        print("  No main content found")
        return {"score": 0, "notes": ["No main content found"]}

    notes = []
    score = 100

    paragraphs = main.find_all("p")
    long_paragraphs = [p for p in paragraphs if len(p.get_text().split()) > 150]
    if long_paragraphs:
        notes.append(f"{len(long_paragraphs)} paragraphs over 150 words")
        score -= min(20, len(long_paragraphs) * 5)

    text = main.get_text()
    stats = len(re.findall(r"\$[\d,]+|\d+%|\d+\.\d+|\d+ (?:billion|million|thousand)", text))
    if stats < 5:
        notes.append(f"Only {stats} statistics found (aim for 10+)")
        score -= 10
    else:
        notes.append(f"{stats} statistics found")

    lists = main.find_all(["ul", "ol"])
    if len(lists) < 2:
        notes.append(f"Only {len(lists)} lists (aim for 3+)")
        score -= 5
    else:
        notes.append(f"{len(lists)} lists found")

    tables = main.find_all("table")
    if len(tables) >= 1:
        notes.append(f"{len(tables)} data table(s) found")

    headings = main.find_all(["h2", "h3"])
    question_headings = [
        h for h in headings
        if "?" in h.get_text() or h.get_text().strip().lower().startswith(
            ("how", "what", "why", "when", "where")
        )
    ]
    if question_headings:
        notes.append(f"{len(question_headings)} question-based headings")

    print(f"  Citability score: {max(0, score)}/100")
    for note in notes:
        print(f"    - {note}")

    return {"score": max(0, score), "notes": notes}


def audit_page(url):
    print(f"\n{'=' * 60}")
    print(f"PAGE: {url}")
    print(f"{'=' * 60}")

    try:
        status, html = fetch(url)
    except Exception as e:
        print(f"  Failed to fetch: {e}")
        return {"url": url, "error": str(e)}

    soup = BeautifulSoup(html, "html.parser")

    schemas = check_schema(soup)
    citability = check_citability(soup)

    has_canonical = bool(soup.find("link", attrs={"rel": "canonical"}))
    has_og = bool(soup.find("meta", attrs={"property": "og:title"}))
    has_description = bool(soup.find("meta", attrs={"name": "description"}))
    has_h1 = bool(soup.find("h1"))
    word_count = len(soup.get_text().split())

    return {
        "url": url,
        "schemas": schemas,
        "citability_score": citability["score"],
        "citability_notes": citability["notes"],
        "word_count": word_count,
        "meta": {
            "canonical": has_canonical,
            "og": has_og,
            "description": has_description,
            "h1": has_h1,
        },
    }


def main():
    print(f"\n{'#' * 60}")
    print(f"# GEO AUDIT: {SITE_URL}")
    print(f"# {time.strftime('%Y-%m-%d %H:%M')}")
    print(f"{'#' * 60}")

    robots = check_robots()
    llms = check_llms_txt()

    urls = get_sitemap_urls()
    print(f"\n\nFound {len(urls)} pages in sitemap\n")

    results = []
    total_citability = 0

    for url in urls:
        result = audit_page(url)
        results.append(result)
        if "citability_score" in result:
            total_citability += result["citability_score"]
        time.sleep(0.3)

    avg_citability = total_citability / len(results) if results else 0

    print(f"\n\n{'=' * 60}")
    print(f"SITE-LEVEL SUMMARY")
    print(f"{'=' * 60}")
    print(f"AI crawlers blocked: {len(robots.get('blocked', []))}")
    print(f"llms.txt present: {llms.get('found', False)}")
    print(f"Average citability score: {avg_citability:.1f}/100")
    print(f"Pages audited: {len(results)}")

    report = {
        "site": SITE_URL,
        "audited_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "robots": robots,
        "llms_txt": llms,
        "avg_citability": avg_citability,
        "pages": results,
    }

    with open(REPORT_FILE, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\nReport saved to {REPORT_FILE}")

    if robots.get("blocked"):
        print(f"\nWARNING: {len(robots['blocked'])} AI crawlers blocked")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
