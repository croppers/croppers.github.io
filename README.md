# cropper.info

A hand-written static site published by GitHub Pages from `main` at `/`.
`index.html` and `style.css` are edited directly. The publication list and
the local notes archive are generated. The homepage links to the Substack page
instead of listing local notes.

## Writing a note

Create `content/notes/<slug>.md`. The slug becomes the URL, so pick it
carefully — it is meant to be permanent.

```markdown
---
title: "What the April 1 snowpack index hides"
date: "2026-08-03"
description: "One sentence. Used for search results and the feed."
---

The body, in Markdown. Tables, footnotes, code blocks and block quotes
all work.
```

Then build and commit:

```bash
./.venv/bin/python build.py
```

That writes `/notes/<slug>/index.html`, rebuilds `/notes/`, refreshes
`feed.xml`, and updates the notes entries in `sitemap.xml`. The homepage
Substack section is hand-written and is left alone.

Add `draft: true` to the front matter to keep a note out of the homepage,
the sitemap and the feed. `build.py --drafts` renders drafts locally so you
can read them; those pages carry `noindex`, and should not be committed.

The homepage's Substack section links to `https://page.substack.com/`.

## Updating publications

```bash
./.venv/bin/python update_publications.py
```

Pulls from Google Scholar and rewrites the `<!-- publications:* -->` region.

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt
```

Use the venv rather than the system Python — the Anaconda install on this
machine has broken package metadata and cannot import `markdown`.

## Previewing

```bash
python3 serve.py        # http://localhost:8131
```

Serves from the repository root, so `/notes/` and the absolute asset paths
resolve the way they do in production.

Use this rather than `python3 -m http.server`, which sends no `Cache-Control`
and lets the browser reuse a stale `style.css` after a rebuild. That one is
genuinely hard to diagnose &mdash; the markup is right and the stylesheet on
disk is right, and what you are looking at is the previous stylesheet applied
to the new page.
