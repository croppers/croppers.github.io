"""Generate the parts of the site that are not hand-written.

Notes live in content/notes/<slug>.md. Each becomes /notes/<slug>/, so the URL
never carries a file extension and survives a change of generator. One piece of
front matter feeds the note page, the homepage list, the notes index, the
sitemap and the feed, so a title or a date is only ever typed once.

    ./.venv/bin/python build.py           # publish
    ./.venv/bin/python build.py --drafts  # include drafts, marked noindex

Hand-written files are edited only between their marker comments; everything
outside a marker pair is left exactly as found.
"""

import html
import json
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

# Beyond this many, the homepage list stops and defers to the notes index.
HOMEPAGE_NOTES = 5


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


def parse_front_matter(text, source):
    """Read the leading --- block.

    Deliberately not YAML: the fields are flat strings, and a real parser is a
    dependency this site would otherwise not need.
    """
    if not text.startswith("---"):
        raise ValueError(f"{source}: no front matter")

    _, block, body = text.split("---", 2)
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
        title=fields["title"],
        date=datetime.strptime(fields["date"], "%Y-%m-%d"),
        description=fields["description"],
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
    <title>{html.escape(title)} | Stephen Cropper</title>
    <link rel="canonical" href="{canonical}">
    <link rel="stylesheet" href="/style.css">
    <link rel="icon" href="/img/earth.ico" type="image/x-icon">
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
        <p class="breadcrumb"><a href="/">Stephen Cropper</a></p>
    </header>

    <main id="content">
        <article class="note">
{draft_notice}            <h1>{html.escape(note.title)}</h1>
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
    """The one list shape used on the homepage and the notes index."""
    pad = " " * indent
    items = []
    for note in notes:
        flag = " (draft)" if note.draft else ""
        items.append(
            f"{pad}    <li>\n"
            f'{pad}        <a href="{note.path}">{html.escape(note.title)}</a>\n'
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
        <p class="breadcrumb"><a href="/">Stephen Cropper</a></p>
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


def render_homepage_section(notes):
    if not notes:
        return ""

    shown = notes[:HOMEPAGE_NOTES]
    if len(notes) > len(shown):
        heading = (
            '            <div class="section-heading">\n'
            "                <h2>Notes</h2>\n"
            '                <a href="/notes/">All notes</a>\n'
            "            </div>"
        )
    else:
        heading = "            <h2>Notes</h2>"

    return (
        '        <section id="notes">\n'
        f"{heading}\n"
        f"{render_list(shown, 12)}\n"
        "        </section>"
    )


def render_feed(notes):
    updated = notes[0].stamp if notes else datetime.now(timezone.utc).isoformat()
    entries = "\n".join(
        f"""    <entry>
        <title>{html.escape(note.title)}</title>
        <link href="{note.url}"/>
        <id>{note.url}</id>
        <updated>{note.stamp}</updated>
        <summary>{html.escape(note.description)}</summary>
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
    return "\n".join(
        f"    <url>\n"
        f"        <loc>{note.url}</loc>\n"
        f"        <lastmod>{note.iso_date}</lastmod>\n"
        f"    </url>"
        for note in notes
    )


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
        ROOT / "index.html", "notes", render_homepage_section(notes)
    )
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
