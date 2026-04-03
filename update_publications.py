#!/usr/bin/env python3
"""
Scrape Google Scholar for publications and update the publications section
in index.html. Filters to journal articles only (items with a venue/journal).
Resolves DOIs via CrossRef API.
"""

import re
import time
import urllib.parse
import json
from collections import defaultdict

import requests
from scholarly import scholarly

SCHOLAR_ID = "TDKOII8AAAAJ"
AUTHOR_BOLD_NAME = "Cropper, S."
CROSSREF_API = "https://api.crossref.org/works"

# Manual overrides for publications where Scholar metadata is incomplete.
# Keyed by a lowercase substring of the title.
MANUAL_OVERRIDES = {
    "western united states dynamically downscaled dataset": {
        "journal": "Geoscientific Model Development",
        "doi": "https://doi.org/10.5194/gmd-17-2265-2024",
    },
}

# Author string replacements to fix Scholar metadata quirks.
# Applied after initial formatting, before bolding.
AUTHOR_FIXES = {
    "Team, U. C. f. C. S.": "the Center for Climate Science Team",
}

# Venues that are conferences/presentations, not peer-reviewed journals
EXCLUDE_VENUES = re.compile(
    r"AGU|EGU|Fall Meeting|Spring Meeting|Abstracts|Conference|Symposium|Workshop|Poster|Presentation",
    re.IGNORECASE,
)


def fetch_publications():
    """Fetch all publications from Google Scholar profile."""
    author = scholarly.search_author_id(SCHOLAR_ID)
    author = scholarly.fill(author, sections=["publications"])
    pubs = []
    seen_titles = set()
    for pub in author.get("publications", []):
        filled = scholarly.fill(pub)
        bib = filled.get("bib", {})

        title = bib.get("title", "")
        journal = bib.get("journal", "").strip()
        pub_url = filled.get("pub_url", "")

        # Check for manual overrides (preferred over Scholar metadata)
        for key, override in MANUAL_OVERRIDES.items():
            if key in title.lower():
                if "journal" in override:
                    journal = override["journal"]
                if "doi" in override:
                    pub_url = override["doi"]
                break

        # Filter: only include entries that have a journal/venue
        if not journal:
            continue

        # Filter: exclude conference abstracts and presentations
        if EXCLUDE_VENUES.search(journal):
            continue

        # Deduplicate by normalized title
        title_key = re.sub(r"\W+", " ", title).strip().lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        pubs.append({
            "title": title,
            "author": bib.get("author", ""),
            "year": str(bib.get("pub_year", "")),
            "journal": journal,
            "pub_url": pub_url,
        })
        # Be polite to Scholar
        time.sleep(1)

    return pubs


def resolve_doi(title):
    """Look up a DOI via CrossRef using the article title."""
    try:
        params = {
            "query.bibliographic": title,
            "rows": 1,
            "select": "DOI,title",
        }
        headers = {"User-Agent": "CropperGHPages/1.0 (mailto:croppers@ucla.edu)"}
        resp = requests.get(CROSSREF_API, params=params, headers=headers, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("message", {}).get("items", [])
        if items:
            candidate_title = items[0].get("title", [""])[0].lower()
            # Accept if titles are reasonably similar
            if _title_similarity(title.lower(), candidate_title) > 0.75:
                return "https://doi.org/" + items[0]["DOI"]
    except Exception:
        pass
    return None


def _title_similarity(a, b):
    """Simple word-overlap similarity between two strings."""
    words_a = set(re.findall(r"\w+", a))
    words_b = set(re.findall(r"\w+", b))
    if not words_a or not words_b:
        return 0.0
    intersection = words_a & words_b
    return len(intersection) / max(len(words_a), len(words_b))


def format_authors(author_str):
    """Convert Scholar author format to 'LastName, F. I.' style with bolded self."""
    # Split on " and " to get individual authors
    authors = [a.strip() for a in author_str.split(" and ") if a.strip()]
    formatted = []
    for author in authors:
        # Scholar typically gives "FirstName LastName" or "F LastName"
        # Convert to "LastName, F." style
        parts = author.split()
        if len(parts) >= 2:
            last = parts[-1]
            initials = " ".join(p[0] + "." for p in parts[:-1])
            name = f"{last}, {initials}"
        else:
            name = author
        # Normalize underscore artifacts (e.g. "C_W" -> "C. W.")
        name = re.sub(r"(\w)_(\w)", r"\1. \2.", name)
        formatted.append(name)

    result = ", ".join(formatted)

    # Apply known author fixes
    for bad, good in AUTHOR_FIXES.items():
        result = result.replace(bad, good)

    # Bold our author
    result = re.sub(
        r"Cropper, S\.\s*(?:J\.)?",
        "<b>Cropper, S.</b>",
        result,
    )
    return result


def build_publications_html(pubs):
    """Build the HTML for the publications section, grouped by year."""
    by_year = defaultdict(list)
    for pub in pubs:
        by_year[pub["year"]].append(pub)

    html_parts = []
    for year in sorted(by_year.keys(), reverse=True):
        html_parts.append(f"                    <h3>{year}</h3>")
        html_parts.append("                    <ul>")
        for pub in by_year[year]:
            authors = format_authors(pub["author"])
            title = pub["title"]
            journal = pub["journal"]

            # Use pub_url if it's already a DOI (e.g. from manual override),
            # otherwise resolve via CrossRef
            if pub["pub_url"] and "doi.org" in pub["pub_url"]:
                doi_url = pub["pub_url"]
            else:
                doi_url = resolve_doi(title)
                if not doi_url and pub["pub_url"]:
                    doi_url = pub["pub_url"]
            # Be polite to CrossRef
            time.sleep(0.5)

            link_html = ""
            if doi_url:
                link_html = f' <a href="{doi_url}">Access Publication</a>'

            html_parts.append("                        <li>")
            html_parts.append(
                f'                            <p>{authors} ({year}). '
                f'"{title}" '
                f"<em>{journal}</em>.{link_html}</p>"
            )
            html_parts.append("                        </li>")
        html_parts.append("                    </ul>")

    return "\n".join(html_parts)


def update_index_html(pub_html):
    """Replace the publications section in index.html."""
    with open("index.html", "r", encoding="utf-8") as f:
        content = f.read()

    # Match the inner content of the publications section
    pattern = (
        r'(<section id="publications" class="section">)\n'
        r'(.*?)'
        r'(\n\s*</section>)'
    )
    replacement = rf'\1\n{pub_html}\3'
    new_content, count = re.subn(pattern, replacement, content, flags=re.DOTALL)

    if count == 0:
        raise RuntimeError("Could not find publications section in index.html")

    with open("index.html", "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"Updated index.html with {pub_html.count('<li>')} publications.")


def main():
    print("Fetching publications from Google Scholar...")
    pubs = fetch_publications()
    print(f"Found {len(pubs)} journal publications.")

    if not pubs:
        print("No publications found — skipping update.")
        return

    print("Resolving DOIs and building HTML...")
    pub_html = build_publications_html(pubs)

    print("Updating index.html...")
    update_index_html(pub_html)
    print("Done.")


if __name__ == "__main__":
    main()
