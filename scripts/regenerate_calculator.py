#!/usr/bin/env python3
"""
CalcBlueprint — Regenerate Existing Calculator Pages
Overwrites existing pages with the updated prompt (unit toggle + source citations + metric content).
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

MODEL_CANDIDATES = [
    "gemini-3.5-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
REGEN_FILE = "scripts/regenerate_list.json"
TIMEOUT_PER_ATTEMPT = 60
MAX_RETRIES_PER_MODEL = 2


def load_regen_list():
    with open(REGEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_regen_list(items):
    with open(REGEN_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=2)


def pick_next(items):
    for i, item in enumerate(items):
        if item.get("status") != "done":
            return i, item
    return None, None


def build_prompt(item):
    return f"""You are an expert web developer and construction industry writer.

Regenerate a complete single-file HTML page for an EXISTING calculator with these specs:

- Calculator name: {item['name']}
- Slug: {item['slug']}
- Purpose: {item['description']}
- Inputs: {item['inputs']}
- Formula/logic: {item['formula']}

REQUIREMENTS:
1. Output ONLY the full HTML file, starting with <!DOCTYPE html> and ending with </html>. No markdown fences, no explanation.
2. Use this exact CSS structure and design system. The <style> block must begin with `*{margin:0;padding:0;box-sizing:border-box}` and use `font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif`. Header must be `background:#1a2332;border-bottom:3px solid #f5a623`. The calculator Calculate button must be `background:#f5a623;color:#1a2332` (amber, NOT grey, NOT navy). Do NOT use CSS custom properties (var(--x)). Do NOT use `sans-serif` alone as the body font. Follow the exact class names: `.logo`, `.container`, `.calculator-box`, `.form-group`, `.result-box`, `.result-row`, `.lead-form`. Wrap the main content in `<main><div class="container">...</div></main>`.
3. Include: header with logo "Calc<span>Blueprint</span>" linking to "/", nav with About and Contact links.
4. Include a calculator-box with labeled inputs and a Calculate button. Add a unit toggle at the top of the calculator-box with two buttons: "Imperial (US)" and "Metric". Imperial uses feet, inches, pounds, cubic yards. Metric uses meters, centimeters, kilograms, cubic meters. Switching the toggle must swap the input labels (Length in feet → Length in meters) and recalculate using the metric formula when Metric is selected. Default to Imperial. Convert results between unit systems correctly: 1 foot = 0.3048 m, 1 inch = 2.54 cm, 1 pound = 0.4536 kg, 1 cubic yard = 0.7646 cubic meters. Display the correct unit label next to every result value.
5. Include a result-box that shows after clicking Calculate with a list of result rows.
6. Include 3 long-form content sections below the calculator: "How to Calculate [X]", "What Affects [X]", and "Frequently Asked Questions" with 3 Q&As each. Each section should be 100-200 words with real construction industry detail. Every content section must be wrapped in <section class="content-section"> and the CSS must include: .content-section { background-color: #ffffff; border-radius: 8px; padding: 2rem; margin-bottom: 2rem; }. Do NOT create content sections without a white card background.
7. IMPORTANT: In the content sections, mention BOTH imperial and metric units where relevant. For example, "Standard residential slabs are 4 inches (10 cm) thick" or "A typical driveway ranges from 2 to 3 inches (5 to 8 cm)". This makes the content useful for global readers and improves SEO for metric queries.
8. Immediately below the calculator (before the content sections), include a collapsible "How this calculator works" section using <details> and <summary> tags. Inside, write 2-3 sentences explaining the formula in plain English, and one line stating the authoritative source for the formula.
9. Include a footer that contains: navigation links (Home, About, Contact, Privacy) followed by a small citation line in this exact format: "Formula source: [Authoritative Source]. Results are estimates for planning — verify with a licensed professional before ordering materials." Year 2026. Choose the correct authoritative source for the calculator type:
   - Concrete calculators: "ACI 318 Building Code Requirements for Structural Concrete"
   - Roofing calculators: "NRCA Roofing Manual and manufacturer installation guides"
   - Tile/flooring calculators: "TCNA Handbook for Ceramic, Glass, and Stone Tile Installation"
   - Painting calculators: "Paint manufacturer coverage specifications and ASTM D523"
   - Fence/deck calculators: "IRC (International Residential Code) and AWPA standards"
   - Insulation calculators: "DOE (Department of Energy) recommended R-values and manufacturer specs"
   - HVAC calculators: "ASHRAE Handbook of Fundamentals and ACCA Manual J"
   - Electrical calculators: "NEC (National Electrical Code) and NFPA 70"
   - Asphalt/paving calculators: "Asphalt Institute MS-22 and NAPA specifications"
   - Masonry/brick/block calculators: "TMS 402/602 and ASTM C270"
   - Gravel/aggregate calculators: "AASHTO M147 and state DOT aggregate specifications"
   - Lumber/wood calculators: "AWC (American Wood Council) NDS and SPIB grading rules"
   - Landscaping calculators: "State agricultural extension service recommendations"
10. Include the JSON-LD schema block: {{"@context":"https://schema.org","@type":"WebApplication","name":"{item['name']}","applicationCategory":"UtilityApplication","operatingSystem":"Web","offers":{{"@type":"Offer","price":"0","priceCurrency":"USD"}}}}
11. Include this GA4 snippet in the head exactly:
<script async src="https://www.googletagmanager.com/gtag/js?id=G-DHN9J7B497"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-DHN9J7B497');</script>
12. Include this in the head:
<link rel="canonical" href="https://calcblueprint.com/{item['slug']}/">
<title>{item['name']} — CalcBlueprint</title>
<meta name="description" content="{item['description']}">
13. All JavaScript must be inline at the bottom of the body. Use plain vanilla JS.
14. The calculator must work correctly with the formula: {item['formula']}
15. Mobile responsive. No external CSS or JS libraries.
16. The unit toggle must be visually clear — two buttons side by side, with the active one highlighted in the amber accent color.

Output the full HTML file now:"""


def call_gemini_once(prompt, model):
    url = BASE_URL.format(model=model, key=API_KEY)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.4,
            "maxOutputTokens": 32768,
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
            if e.code in (429, 500, 502, 503, 504):
                backoff = 5 * (attempt + 1)
                print(f"  Retryable error — waiting {backoff}s")
                time.sleep(backoff)
                continue
            else:
                raise
        except (TimeoutError, urllib.error.URLError) as e:
            print(f"  Network/timeout error: {e}")
            last_error = e
            time.sleep(5 * (attempt + 1))
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
    if start != -1 and end != -1:
        return text[start:end + len("</html>")]
    if start != -1:
        print("WARNING: Truncated response. Closing tags.")
        truncated = text[start:]
        if "<body" in truncated:
            if "</body>" not in truncated:
                truncated += "\n</body>"
            if "</html>" not in truncated:
                truncated += "\n</html>"
            return truncated
        raise ValueError("Response truncated before body started")
    print(f"ERROR: No HTML in response. First 500 chars: {text[:500]}")
    raise ValueError("Could not extract HTML")


def overwrite_page(slug, html):
    """Overwrite the existing index.html for a calculator."""
    path = os.path.join(slug, "index.html")
    if not os.path.exists(path):
        print(f"WARNING: {path} does not exist. Creating it.")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Overwrote {path} ({len(html)} bytes)")


def main():
    items = load_regen_list()
    idx, item = pick_next(items)
    if item is None:
        print("All regeneration items complete")
        return

    print(f"Regenerating: {item['name']} ({item['slug']})")
    prompt = build_prompt(item)
    raw = generate_with_fallback(prompt)
    html = extract_html(raw)
    overwrite_page(item["slug"], html)

    items[idx]["status"] = "done"
    items[idx]["regenerated_at"] = datetime.utcnow().isoformat() + "Z"
    save_regen_list(items)
    print("Done.")


if __name__ == "__main__":
    main()
