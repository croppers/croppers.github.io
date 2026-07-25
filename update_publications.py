#!/usr/bin/env python3
"""Update the title-first publication list in index.html from Google Scholar."""

from __future__ import annotations

import html
import re
import time
from collections import defaultdict

import requests
from scholarly import scholarly

SCHOLAR_ID = "TDKOII8AAAAJ"
CROSSREF_API = "https://api.crossref.org/works"

MANUAL_OVERRIDES = {
    "forced component estimation statistical method intercomparison project": {
        "authors": [
            "Robert C. J. Wills",
            "Clara Deser",
            "Karen A. McKinnon",
            "Adam Phillips",
            "Stephen Po-Chedley",
            "Sebastian Sippel",
            "Anna L. Merrifield",
            "Constantin Bône",
            "Céline Bonfils",
            "Gustau Camps-Valls",
            "Stephen Cropper",
            "Charlotte Connolly",
            "Shiheng Duan",
            "Homer Durand",
            "Alexander Feigin",
            "M. A. Fernandez",
            "Guillaume Gastineau",
            "Andrei Gavrilov",
            "Emily Gordon",
            "Moritz Günther",
            "Maren Höver",
            "Sergey Kravtsov",
            "Yan-Ning Kuo",
            "Justin Lien",
            "Gavin D. Madakumbura",
            "Nathan Mankovich",
            "Matthew Newman",
            "Jamin Rader",
            "Jia-Rui Shi",
            "Sang-Ik Shin",
            "Gherardo Varando",
        ],
    },
    "temporal coverage over density": {
        "journal": "Preprint",
        "doi": "https://arxiv.org/abs/2606.07898",
        "authors": [
            "Karandeep Singh",
            "Stefan Rahimi",
            "Chad W. Thackeray",
            "Stephen Cropper",
            "Alex Hall",
        ],
    },
    "soil water percolation and nutrient fluxes": {
        "authors": [
            "Jardel Ramos Rodrigues",
            "Kurt C. Solander",
            "Stephen Cropper",
            "Brent D. Newman",
            "Adam D. Collins",
            "Jeffrey M. Warren",
            "Robinson Negron-Juarez",
            "Bruno O. Gimenez",
            "Gustavo Carvalho Spanner",
            "Valdiek da Silva Menezes",
            "Eduardo Antonio Ríos-Villamizar",
            "Regison Costa de Oliveira",
            "Sávio José Filgueiras Ferreira",
            "Niro Higuchi",
        ],
    },
    "western united states dynamically downscaled dataset": {
        "journal": "Geoscientific Model Development",
        "doi": "https://doi.org/10.5194/gmd-17-2265-2024",
        "authors": [
            "Stefan Rahimi",
            "Lei Huang",
            "Jesse Norris",
            "Alex Hall",
            "Naomi Goldenson",
            "Will Krantz",
            "Benjamin Bass",
            "Chad Thackeray",
            "Henry Lin",
            "Di Chen",
            "Eli Dennis",
            "Ethan Collins",
            "Zachary J. Lebo",
            "Emily Slinskey",
            "Sara Graves",
            "Surabhi Biyani",
            "Bowen Wang",
            "Stephen Cropper",
            "UCLA Center for Climate Science Team",
        ],
    },
    "revisiting a constraint on equilibrium climate sensitivity": {
        "authors": [
            "Stephen Cropper",
            "Chad W. Thackeray",
            "Julien Emile-Geay",
        ],
    },
    "comparing deuterium excess": {
        "authors": [
            "Stephen Cropper",
            "Kurt Solander",
            "Brent D. Newman",
            "Obbe A. Tuinenburg",
            "Arie Staal",
            "Jolanda J. E. Theeuwen",
            "Chonggang Xu",
        ],
    },
}

EXCLUDE_VENUES = re.compile(
    r"AGU|EGU|Fall Meeting|Spring Meeting|Abstracts|Conference|Symposium|"
    r"Workshop|Poster|Presentation",
    re.IGNORECASE,
)


def fetch_publications() -> list[dict[str, str]]:
    """Fetch unique journal publications from the configured Scholar profile."""
    author = scholarly.fill(
        scholarly.search_author_id(SCHOLAR_ID),
        sections=["publications"],
    )
    publications: list[dict[str, str]] = []
    seen_titles: set[str] = set()

    for publication in author.get("publications", []):
        filled = scholarly.fill(publication)
        bibliography = filled.get("bib", {})
        title = str(bibliography.get("title") or "").strip()
        journal = str(bibliography.get("journal") or "").strip()
        publication_url = str(filled.get("pub_url") or "").strip()
        raw_authors = bibliography.get("author") or []
        if isinstance(raw_authors, list):
            authors = [str(author).strip() for author in raw_authors if author]
        elif isinstance(raw_authors, str):
            authors = [
                author.strip()
                for author in raw_authors.split(" and ")
                if author.strip()
            ]
        else:
            authors = []

        for key, override in MANUAL_OVERRIDES.items():
            if key in title.lower():
                journal = override.get("journal", journal)
                publication_url = override.get("doi", publication_url)
                authors = override.get("authors", authors)
                break

        if not title or not journal or EXCLUDE_VENUES.search(journal):
            continue

        title_key = re.sub(r"\W+", " ", title).strip().lower()
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)
        publications.append(
            {
                "title": title,
                "year": str(bibliography.get("pub_year") or "").strip(),
                "journal": journal,
                "url": publication_url,
                "authors": authors,
            }
        )
        time.sleep(1)

    return publications


def title_similarity(left: str, right: str) -> float:
    """Return a conservative word-overlap score for two publication titles."""
    left_words = set(re.findall(r"\w+", left.lower()))
    right_words = set(re.findall(r"\w+", right.lower()))
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / max(len(left_words), len(right_words))


def resolve_doi(title: str) -> str | None:
    """Resolve a publication title through Crossref when Scholar has no DOI."""
    try:
        response = requests.get(
            CROSSREF_API,
            params={"query.bibliographic": title, "rows": 1, "select": "DOI,title"},
            headers={
                "User-Agent": "CropperGHPages/1.0 (mailto:croppers@uci.edu)"
            },
            timeout=15,
        )
        response.raise_for_status()
        items = response.json().get("message", {}).get("items", [])
        if items:
            candidate = items[0].get("title", [""])[0]
            if title_similarity(title, candidate) > 0.75:
                return f"https://doi.org/{items[0]['DOI']}"
    except (KeyError, IndexError, requests.RequestException, ValueError):
        return None
    return None


def publication_url(publication: dict[str, str]) -> str | None:
    """Prefer a DOI, falling back to Scholar's publication URL."""
    existing = publication["url"]
    if "doi.org" in existing:
        return existing
    resolved = resolve_doi(publication["title"])
    time.sleep(0.5)
    return resolved or existing or None


def format_author(author: str) -> str:
    """Escape an author name and emphasize Stephen Cropper."""
    escaped = html.escape(author)
    if re.search(r"\bCropper\b", author, re.IGNORECASE):
        return f"<strong>{escaped}</strong>"
    return escaped


def format_authors(authors: list[str]) -> str:
    """Format complete short lists and compact long collaborations."""
    if len(authors) <= 7:
        displayed = authors
    else:
        displayed = authors[:3]
        cropper = next(
            (author for author in authors if re.search(r"\bCropper\b", author)),
            None,
        )
        if cropper and cropper not in displayed:
            displayed = [*displayed, "…", cropper]
        displayed = [*displayed, "et al."]
    return ", ".join(format_author(author) for author in displayed)


def build_publications_html(publications: list[dict[str, str]]) -> str:
    """Build a compact title-first publication list in reverse chronological order."""
    by_year: defaultdict[str, list[dict[str, str]]] = defaultdict(list)
    for publication in publications:
        by_year[publication["year"]].append(publication)

    lines = ['            <ol class="publication-list">']
    for year in sorted(by_year, reverse=True):
        for publication in by_year[year]:
            title = html.escape(publication["title"])
            journal = html.escape(publication["journal"])
            year_text = html.escape(year)
            url = publication_url(publication)
            authors = format_authors(publication.get("authors", []))
            title_html = f"<cite>{title}</cite>"
            if url:
                title_html = f'<a href="{html.escape(url, quote=True)}">{title_html}</a>'
            lines.extend(
                [
                    "                <li>",
                    f"                    {title_html}",
                    f'                    <span class="publication-authors">{authors}</span>',
                    f'                    <span class="publication-meta">{journal} · {year_text}</span>',
                    "                </li>",
                ]
            )
    lines.append("            </ol>")
    return "\n".join(lines)


def update_index_html(publications_html: str) -> None:
    """Replace only the generated publication list between stable markers."""
    with open("index.html", encoding="utf-8") as stream:
        content = stream.read()

    pattern = (
        r"(?P<start>\s*<!-- publications:start -->)\n"
        r".*?"
        r"(?P<end>\n\s*<!-- publications:end -->)"
    )
    replacement = (
        r"\g<start>\n"
        + publications_html
        + r"\g<end>"
    )
    updated, count = re.subn(pattern, replacement, content, flags=re.DOTALL)
    if count != 1:
        raise RuntimeError(
            f"Expected one publications marker block in index.html, found {count}"
        )

    with open("index.html", "w", encoding="utf-8") as stream:
        stream.write(updated)


def main() -> None:
    print("Fetching journal publications from Google Scholar...")
    publications = fetch_publications()
    if not publications:
        raise RuntimeError("No publications found; index.html was not changed")
    update_index_html(build_publications_html(publications))
    print(f"Updated index.html with {len(publications)} publications.")


if __name__ == "__main__":
    main()
