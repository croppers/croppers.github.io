"""Generate the parts of the site that are not hand-written.

Notes live in content/notes/<slug>.md. Each becomes /notes/<slug>/, so the URL
never carries a file extension and survives a change of generator. One piece of
front matter feeds the note page, the notes index, the sitemap and the feed.
The homepage's Substack section is hand-written and is not replaced by this
script.

    ./.venv/bin/python build.py           # publish
    ./.venv/bin/python build.py --drafts  # include drafts, marked noindex

Hand-written files are edited only between their marker comments; everything
outside a marker pair is left exactly as found.
"""

import html
import json
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import markdown

SITE = "https://cropper.info"
ROOT = Path(__file__).parent
SOURCE = ROOT / "content" / "notes"
OUTPUT = ROOT / "notes"

def text(value):
    """Escape for element content, where quotes need no escaping."""
    return html.escape(value, quote=False)


# smarty handles the body, but front matter never reaches the renderer, so a
# title would keep straight quotes while the prose under it curled them.
SMART = (
    (r"(?<=\w)'(?=\w)", "’"),
    (r'"([^"]*)"', "“\\1”"),
    (r"---", "—"),
    (r"--", "–"),
)


def smarten(value):
    for pattern, replacement in SMART:
        value = re.sub(pattern, replacement, value)
    return value


# --------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Note:
    slug: str
    title: str
    date: datetime
    description: str
    draft: bool
    body: str

    @property
    def path(self):
        return f"/notes/{self.slug}/"

    @property
    def url(self):
        return f"{SITE}{self.path}"

    @property
    def iso_date(self):
        return self.date.date().isoformat()

    @property
    def stamp(self):
        """RFC 3339, which is what Atom wants."""
        return self.date.replace(tzinfo=timezone.utc).isoformat()

    @property
    def human_date(self):
        return f"{self.date:%B} {self.date.day}, {self.date:%Y}"


def parse_front_matter(raw, source):
    """Read the leading --- block.

    Deliberately not YAML: the fields are flat strings, and a real parser is a
    dependency this site would otherwise not need.
    """
    if not raw.startswith("---"):
        raise ValueError(f"{source}: no front matter")

    _, block, body = raw.split("---", 2)
    fields = {}
    for line in block.strip().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"{source}: cannot read front-matter line {line!r}")
        value = value.strip()
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        fields[key.strip()] = value
    return fields, body


def read_note(path):
    fields, body = parse_front_matter(path.read_text(encoding="utf-8"), path.name)
    for required in ("title", "date", "description"):
        if not fields.get(required):
            raise ValueError(f"{path.name}: front matter needs a {required}")

    renderer = markdown.Markdown(extensions=["extra", "smarty"])
    return Note(
        slug=path.stem,
        title=smarten(fields["title"]),
        date=datetime.strptime(fields["date"], "%Y-%m-%d"),
        description=smarten(fields["description"]),
        draft=fields.get("draft", "").lower() in ("true", "yes", "1"),
        body=renderer.convert(body),
    )


def load_notes(include_drafts):
    if not SOURCE.is_dir():
        return []
    notes = [read_note(path) for path in sorted(SOURCE.glob("*.md"))]
    if not include_drafts:
        notes = [note for note in notes if not note.draft]
    return sorted(notes, key=lambda note: note.date, reverse=True)


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------

def head(title, description, canonical, extra=""):
    """The shared document head. Mirrors index.html so pages match."""
    return f"""    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="author" content="Stephen Cropper">
    <meta name="description" content="{html.escape(description)}">
{extra}    <meta property="og:title" content="{html.escape(title)}">
    <meta property="og:description" content="{html.escape(description)}">
    <meta property="og:url" content="{canonical}">
    <meta property="og:site_name" content="Stephen Cropper">
    <meta name="twitter:card" content="summary">
    <title>{text(title)} | Stephen Cropper</title>
    <link rel="canonical" href="{canonical}">
    <link rel="stylesheet" href="/style.css">
    <link rel="icon" href="/img/earth.ico?v=2" type="image/x-icon">
    <link rel="alternate" type="application/atom+xml" title="Notes by Stephen Cropper" href="/feed.xml">"""


def render_note_page(note):
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "BlogPosting",
        "headline": note.title,
        "description": note.description,
        "datePublished": note.iso_date,
        "url": note.url,
        "mainEntityOfPage": note.url,
        "author": {
            "@type": "Person",
            "@id": f"{SITE}/#stephen-cropper",
            "name": "Stephen Cropper",
            "url": f"{SITE}/",
        },
    }, indent=4)

    robots = '    <meta name="robots" content="noindex">\n' if note.draft \
        else '    <meta name="robots" content="index, follow, max-image-preview:large">\n'
    meta = (
        f'{robots}    <meta property="og:type" content="article">\n'
        f'    <meta property="article:published_time" content="{note.iso_date}">\n'
    )
    draft_notice = '        <p class="draft-notice">Draft &mdash; not published.</p>\n' \
        if note.draft else ""

    return f"""<!doctype html>
<html lang="en">
<head>
{head(note.title, note.description, note.url, meta)}
    <script type="application/ld+json">
    {schema}
    </script>
</head>
<body>
    <a class="skip-link" href="#content">Skip to content</a>

    <header class="site-header">
        <p class="breadcrumb"><a href="/">Home</a></p>
    </header>

    <main id="content">
        <article class="note">
{draft_notice}            <h1>{text(note.title)}</h1>
            <p class="meta">{note.human_date}</p>
{note.body}
        </article>
    </main>

    <footer>
        <a href="/notes/">All notes</a>
    </footer>
</body>
</html>
"""


def render_list(notes, indent):
    """Render the notes index list."""
    pad = " " * indent
    items = []
    for note in notes:
        flag = " (draft)" if note.draft else ""
        items.append(
            f"{pad}    <li>\n"
            f'{pad}        <a href="{note.path}">{text(note.title)}</a>\n'
            f"{pad}        <span>{note.human_date}{flag}</span>\n"
            f"{pad}    </li>"
        )
    return f'{pad}<ol class="note-list">\n' + "\n".join(items) + f"\n{pad}</ol>"


def render_notes_index(notes):
    description = (
        "Short pieces by Stephen Cropper on climate modelling, data, "
        "and the things that go wrong in between."
    )
    meta = (
        '    <meta name="robots" content="index, follow">\n'
        '    <meta property="og:type" content="website">\n'
    )
    return f"""<!doctype html>
<html lang="en">
<head>
{head("Notes", description, SITE + "/notes/", meta)}
</head>
<body>
    <a class="skip-link" href="#content">Skip to content</a>

    <header class="site-header">
        <p class="breadcrumb"><a href="/">Home</a></p>
    </header>

    <main id="content">
        <section id="notes">
            <h2>Notes</h2>
{render_list(notes, 12)}
        </section>
    </main>
</body>
</html>
"""


def render_feed(notes):
    updated = notes[0].stamp if notes else datetime.now(timezone.utc).isoformat()
    entries = "\n".join(
        f"""    <entry>
        <title>{text(note.title)}</title>
        <link href="{note.url}"/>
        <id>{note.url}</id>
        <updated>{note.stamp}</updated>
        <summary>{text(note.description)}</summary>
    </entry>"""
        for note in notes
    )
    return f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>Notes by Stephen Cropper</title>
    <link href="{SITE}/"/>
    <link rel="self" href="{SITE}/feed.xml"/>
    <id>{SITE}/</id>
    <updated>{updated}</updated>
    <author>
        <name>Stephen Cropper</name>
    </author>
{entries}
</feed>
"""


def render_sitemap_entries(notes):
    if not notes:
        return ""

    def entry(loc, lastmod):
        return (
            f"    <url>\n"
            f"        <loc>{loc}</loc>\n"
            f"        <lastmod>{lastmod}</lastmod>\n"
            f"    </url>"
        )

    # The index is a real page and was being left out of the sitemap.
    rows = [entry(f"{SITE}/notes/", notes[0].iso_date)]
    rows += [entry(note.url, note.iso_date) for note in notes]
    return "\n".join(rows)


# --------------------------------------------------------------------------
# Writing
# --------------------------------------------------------------------------

def replace_between_markers(path, name, replacement):
    """Swap the text between <!-- name:start --> and <!-- name:end -->."""
    text = path.read_text(encoding="utf-8")
    start, end = f"<!-- {name}:start -->", f"<!-- {name}:end -->"
    if start not in text or end not in text:
        raise ValueError(f"{path.name}: missing {start} / {end}")

    before, _, rest = text.partition(start)
    _, _, after = rest.partition(end)
    body = f"\n{replacement}\n" if replacement else "\n"
    # Keep the markers on their own lines at the indent they already had.
    indent = before[before.rfind("\n") + 1:]
    path.write_text(
        f"{before}{start}{body}{indent}{end}{after}", encoding="utf-8"
    )


def build(include_drafts=False):
    notes = load_notes(include_drafts)

    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    for note in notes:
        directory = OUTPUT / note.slug
        directory.mkdir(parents=True)
        (directory / "index.html").write_text(
            render_note_page(note), encoding="utf-8"
        )
        print(f"  built {note.path}{' (draft)' if note.draft else ''}")

    if notes:
        OUTPUT.mkdir(exist_ok=True)
        (OUTPUT / "index.html").write_text(
            render_notes_index(notes), encoding="utf-8"
        )
        print(f"  built /notes/ ({len(notes)} notes)")

    published = [note for note in notes if not note.draft]
    (ROOT / "feed.xml").write_text(render_feed(published), encoding="utf-8")
    replace_between_markers(
        ROOT / "sitemap.xml", "notes", render_sitemap_entries(published)
    )

    if not notes:
        print("  no notes yet — homepage section omitted")
    drafts = [note for note in notes if note.draft]
    if drafts:
        print(f"  {len(drafts)} draft(s) rendered noindex — do not commit")


if __name__ == "__main__":
    build(include_drafts="--drafts" in sys.argv)
