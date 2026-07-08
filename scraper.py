"""
Daily internship-posting tracker.

For each company in companies.json, loads the career page in a headless
browser (so JS-rendered sites like Workday/Greenhouse/iCIMS actually render),
pulls out any visible lines that mention "intern"/"internship", and compares
them against the last known snapshot in state.json. Any new or changed line
gets appended to CHANGELOG.md with a timestamp.

GitHub Actions commits CHANGELOG.md and state.json after every run. Watching
the repo (see README) makes GitHub email you whenever that commit happens.
"""

import json
import re
import sys
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright

COMPANIES_FILE = "companies.json"
STATE_FILE = "state.json"
CHANGELOG_FILE = "CHANGELOG.md"
NAV_TIMEOUT_MS = 25000


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def extract_intern_lines(text, keywords):
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    hits = []
    for ln in lines:
        low = ln.lower()
        if any(kw in low for kw in keywords) and len(ln) < 300:
            hits.append(ln)
    # de-dupe while preserving order
    seen = set()
    out = []
    for h in hits:
        if h not in seen:
            seen.add(h)
            out.append(h)
    return out


def main():
    companies = load_json(COMPANIES_FILE, [])
    state = load_json(STATE_FILE, {})
    changes = []

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
            )
        )
        for company in companies:
            name = company["name"]
            url = company["url"]
            keywords = [k.lower() for k in company.get("keywords", ["intern"])]
            page = context.new_page()
            try:
                page.goto(url, timeout=NAV_TIMEOUT_MS, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)  # let JS-rendered widgets settle
                body_text = page.inner_text("body")
            except Exception as e:
                print(f"[warn] {name}: failed to load ({e})", file=sys.stderr)
                page.close()
                continue
            page.close()

            current_hits = extract_intern_lines(body_text, keywords)
            prev_hits = set(state.get(name, {}).get("hits", []))
            new_hits = [h for h in current_hits if h not in prev_hits]

            if new_hits:
                changes.append((name, url, new_hits))

            state[name] = {
                "hits": current_hits,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            }
        browser.close()

    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

    if changes:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        with open(CHANGELOG_FILE, "a") as f:
            f.write(f"\n## {ts}\n")
            for name, url, hits in changes:
                f.write(f"\n**{name}** — {url}\n")
                for h in hits:
                    f.write(f"- {h}\n")
        print(f"Found changes for {len(changes)} companies.")
    else:
        print("No new internship-related content detected this run.")


if __name__ == "__main__":
    main()
