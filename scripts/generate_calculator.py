#!/usr/bin/env python3
"""
CalcBlueprint — Automated Calculator Generator
Generates one new construction calculator page per run using Gemini API.
"""
import os
import json
import re
import sys
import urllib.request
import urllib.error
from datetime import datetime

API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("ERROR: GEMINI_API_KEY environment variable is not set")
    sys.exit(1)

# Try these models in order (newest free-tier models first)
MODEL_CANDIDATES = [
    "gemini-3.8-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
]

BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"

QUEUE_FILE = "scripts/queue.json"


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
4. Include a calculator-box with labeled inputs and a Calculate button.
5. Include a result-box that shows after clicking Calculate with a list of result rows.
6. Include 3 long-form content sections below the calculator: "How to Calculate [X]", "What Affects [X]", and "Frequently Asked Questions" with 3 Q&As each. Each section should be 100-200 words with real construction industry detail.
7. Include a footer with links: Home, About, Contact, Privacy. Year 2026.
8. Include the JSON-LD schema block: {{"@context":"https://schema.org","@type":"WebApplication","name":"{item['name']}","applicationCategory":"UtilityApplication","operatingSystem":"Web","offers":{{"@type":"Offer","price":"0","priceCurrency":"USD"}}}}
9. Include this GA4 snippet in the head exactly:
<script async src="https://www.googletagmanager.com/gtag/js?id=G-DHN9J7B497"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','G-DHN9J7B497');</script>
10. Include this in the head:
<link rel="canonical" href="https://calcblueprint.com/{item['slug']}/">
<title>{item['name']} — CalcBlueprint</title>
<meta name="description" content="{item['description']}">
11. All JavaScript must be inline at the bottom of the body. Use plain vanilla JS.
12. The calculator must work correctly with the formula: {item['formula']}
13. Mobile responsive. No external CSS or JS libraries.

Output the full HTML file now:"""


def call_gemini(prompt, model):
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
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8")
        print(f"HTTP {e.code} for model {model}: {error_body}")
        raise
    return data["candidates"][0]["content"]["parts"][0]["text"]


def generate_with_fallback(prompt):
    last_error = None
    for model in MODEL_CANDIDATES:
        print(f"Trying model: {model}")
        try:
            result = call_gemini(prompt, model)
            print(f"Success with model: {model}")
            return result
        except urllib.error.HTTPError as e:
            last_error = e
            if e.code == 404:
                print(f"Model {model} not found, trying next...")
                continue
            else:
                # 400/403/429 etc — don't retry with another model
                raise
        except Exception as e:
            last_error = e
            print(f"Unexpected error with {model}: {e}")
            continue
    raise RuntimeError(f"All models failed. Last error: {last_error}")


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
