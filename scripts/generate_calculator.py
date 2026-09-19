#!/usr/bin/env python3
"""
CalcBlueprint — Automated Calculator Generator
Generates one new construction calculator page per run using Gemini API.
"""
import os
import json
import re
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable is not set")
    sys.exit(1)

# Try these models in order — current free-tier models as of late 2026
MODEL_CANDIDATES = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

QUEUE_FILE = "scripts/queue.json"
TIMEOUT_PER_ATTEMPT = 60  # seconds per API call
MAX_RETRIES_PER_MODEL = 2


def load_queue():
    with open(QUEUE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def pick_next(queue):
    for i, item in enumerate(queue):
        if item.get("status") != "done":
            return i, item
    return None, None


def save_queue(queue):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(queue, f, indent=2)


def build_prompt(item):
    return f"""You are an expert web developer and construction industry writer.

Generate a complete single-file HTML page for a calculator with these specs:

- Calculator name: {item['name']}
- Slug: {item['slug']}
- Purpose: {item['description']}
- Inputs: {item['inputs']}
- Formula/logic: {item['formula']}

REQUIREMENTS:
1. Output ONLY the full HTML file, starting with <!DOCTYPE html> and ending with </html>. No markdown fences, no explanation.
2. Use this exact structure and style (dark navy header #1a2332, amber accent #f5a623, background #f7f7f5).
3. Include: header with logo "Calc<span>Blueprint</span>" linking to "/", nav with About and Contact links.
4. Include a calculator-box with labeled inputs and a Calculate button. Add a unit toggle at the top of the calculator-box with two buttons: "Imperial (US)" and "Metric". Imperial uses feet, inches, pounds, cubic yards. Metric uses meters, centimeters, kilograms, cubic meters. Switching the toggle must swap the input labels (Length in feet → Length in meters) and recalculate using the metric formula when Metric is selected. Default to Imperial. Convert results between unit systems correctly: 1 foot = 0.3048 m, 1 inch = 2.54 cm, 1 pound = 0.4536 kg, 1 cubic yard = 0.7646 cubic meters. Display the correct unit label next to every result value.
5. Include a result-box that shows after clicking Calculate with a list of result rows.
6. Include 3 long-form content sections below the calculator: "How to Calculate [X]", "What Affects [X]", and "Frequently Asked Questions" with 3 Q&As each. Each section should be 100-200 words with real construction industry detail.
7. Immediately below the calculator (before the content sections), include a collapsible "How this calculator works" section using <details> and <summary> tags. Inside, write 2-3 sentences explaining the formula in plain English, and one line stating the authoritative source for the formula (e.g., "Formula based on ACI 318 Building Code Requirements for Structural Concrete" or "Coverage rates per NRCA Roofing Manual and manufacturer specifications" or "Material coverage per ASTM standards"). Choose the correct authoritative source for the specific calculator type.
8. Include a footer that contains: navigation links (Home, About, Contact, Privacy) followed by a small citation line in this exact format: "Formula source: [Authoritative Source]. Results are estimates for planning — verify with a licensed professional before ordering materials." Year 2026. The [Authoritative Source] must be chosen correctly for the calculator type:
   - Concrete calculators: "ACI 318 Building Code Requirements for Structural Concrete"
   - Roofing calculators: "NRCA Roofing Manual and manufacturer installation guides"
   - Tile/flooring calculators: "TCNA Handbook for Ceramic, Glass, and Stone Tile Installation"
   - Painting calculators: "Paint manufacturer coverage specifications and ASTM D523"
   - Fence/deck calculators: "IRC (International Residential Code) and AWPA standards"
   - Insulation calculators: "DOE (Department of Energy) recommended R-values and manufacturer specs"
   - HVAC calculators: "ASHRAE Handbook of Fundamentals and ACCA Manual J"
   - Electrical calculators: "NEC (National Electrical Code) and NFPA 70"
   - Landscaping calculators: "State agricultural extension service recommendations"
9. Include the JSON-LD schema block: {{"@context":"https://schema.org","@type":"WebApplication","name":"{item['name']}","applicationCategory":"UtilityApplication","operatingSystem":"Web","offers":{{"@type":"Offer","price":"0","priceCurrency":"USD"}}}}
10. Include this GA4 snippet in the head exactly:
<script async src="https://www.googletagmanager.com/gtag/js?id=G-DHN9J7B497"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-DHN9J7B497');</script>
11. Include this in the head:
<link rel="canonical" href="https://calcblueprint.com/{item['slug']}/">
<title>{item['name']} — CalcBlueprint</title>
<meta name="description" content="{item['description']}">
12. All JavaScript must be inline at the bottom of the body. Use plain vanilla JS.
13. The calculator must work correctly with the formula: {item['formula']}
14. Mobile responsive. No external CSS or JS libraries.
15. The unit toggle must be visually clear — two buttons side by side, with the active one highlighted in the amber accent color.

Output the full HTML file now:"""

def call_gemini_once(prompt, model):
    """Single API call. Raises exceptions on failure."""
    url = BASE_URL.format(model=model, key=API_KEY)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 8192,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT_PER_ATTEMPT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def call_gemini_with_retries(prompt, model):
    """Try a model up to MAX_RETRIES_PER_MODEL times with backoff."""
    last_error = None
    for attempt in range(MAX_RETRIES_PER_MODEL):
        try:
            print(f"  Attempt {attempt + 1}/{MAX_RETRIES_PER_MODEL} with {model}")
            data = call_gemini_once(prompt, model)
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            print(f"  HTTP {e.code}: {error_body[:200]}")
            last_error = e
            # 503, 429, 500, 502, 504 are retryable
            if e.code in (429, 500, 502, 503, 504):
                backoff = 5 * (attempt + 1)
                print(f"  Retryable error — waiting {backoff}s before retry")
                time.sleep(backoff)
                continue
            else:
                # 400, 401, 403, 404 — not retryable, break out
                raise
        except (TimeoutError, urllib.error.URLError) as e:
            print(f"  Network/timeout error: {e}")
            last_error = e
            backoff = 5 * (attempt + 1)
            print(f"  Waiting {backoff}s before retry")
            time.sleep(backoff)
            continue
        except Exception as e:
            print(f"  Unexpected error: {e}")
            last_error = e
            break
    raise RuntimeError(f"All attempts failed for {model}: {last_error}")


def generate_with_fallback(prompt):
    errors = []
    for model in MODEL_CANDIDATES:
        print(f"Trying model: {model}")
        try:
            result = call_gemini_with_retries(prompt, model)
            print(f"✅ Success with model: {model}")
            return result
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print(f"Model {model} not found, trying next...")
                errors.append(f"{model}: 404 not found")
                continue
            elif e.code in (429, 503):
                print(f"Model {model} overloaded/unavailable, trying next...")
                errors.append(f"{model}: {e.code}")
                continue
            else:
                errors.append(f"{model}: HTTP {e.code}")
                print(f"Non-retryable error with {model}, trying next...")
                continue
        except Exception as e:
            errors.append(f"{model}: {e}")
            print(f"Model {model} failed: {e}")
            continue
    raise RuntimeError(f"All models failed.\nErrors:\n" + "\n".join(errors))


def extract_html(text):
    text = text.strip()
    text = re.sub(r"^```html\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    start = text.find("<!DOCTYPE html>")
    if start == -1:
        start = text.find("<html")
    end = text.rfind("</html>")
    if start == -1 or end == -1:
        raise ValueError("Could not extract HTML from model output")
    return text[start:end + len("</html>")]


def write_page(slug, html):
    os.makedirs(slug, exist_ok=True)
    path = os.path.join(slug, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {path} ({len(html)} bytes)")


def update_sitemap(slug):
    path = "sitemap.xml"
    with open(path, "r", encoding="utf-8") as f:
        sitemap = f.read()
    url = f"https://calcblueprint.com/{slug}/"
    if url in sitemap:
        print("URL already in sitemap, skipping")
        return
    entry = f'<url><loc>{url}</loc><priority>0.9</priority></url>\n'
    sitemap = sitemap.replace("</urlset>", entry + "</urlset>")
    with open(path, "w", encoding="utf-8") as f:
        f.write(sitemap)
    print(f"Added {url} to sitemap")


def update_homepage(slug, name, description):
    path = "index.html"
    with open(path, "r", encoding="utf-8") as f:
        home = f.read()
    if f'href="/{slug}/"' in home:
        print("Homepage link already exists, skipping")
        return
    card = f'<a href="/{slug}/" class="card"><h3>{name}</h3><p>{description}</p></a>\n'
    marker = "</div></main>"
    idx = home.rfind(marker)
    if idx == -1:
        print("Could not find insert marker in homepage")
        return
    home = home[:idx] + card + home[idx:]
    with open(path, "w", encoding="utf-8") as f:
        f.write(home)
    print(f"Added {name} to homepage")


def main():
    queue = load_queue()
    idx, item = pick_next(queue)
    if item is None:
        print("Queue empty — all calculators generated")
        return

    print(f"Generating: {item['name']} ({item['slug']})")
    prompt = build_prompt(item)
    raw = generate_with_fallback(prompt)
    html = extract_html(raw)
    write_page(item["slug"], html)
    update_sitemap(item["slug"])
    update_homepage(item["slug"], item["name"], item["description"])

    queue[idx]["status"] = "done"
    queue[idx]["generated_at"] = datetime.utcnow().isoformat() + "Z"
    save_queue(queue)
    print("Done.")


if __name__ == "__main__":
    main()
