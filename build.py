#!/usr/bin/env python3
"""Build the Emet static website from the data files.

    python3 build.py

Reads   data/claims.json            the claims and the passages listed against them
        data/texts/tanakh.json      JPS 1917 English + Hebrew text (public domain)
        data/texts/kjv.json         King James Version text (public domain)
        data/chabad_chapters.json   Chabad.org chapter IDs, for links
        site/style.css              the one stylesheet
Writes  docs/                       the finished website (GitHub Pages serves this folder)

Uses only the Python standard library and does not touch the network.

Every piece of text from the data files is HTML-escaped before it is written,
so nothing in the data can add markup or scripts to a page. When it finishes,
the build runs check_output() over everything it wrote and refuses to finish
if any page contains a script, an inline event handler, an iframe/object/embed,
or loads anything from another website.
"""

import html
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "docs"

# One policy for every page: no scripts, nothing loaded from other sites,
# no forms. Links to other sites (Chabad.org, Sefaria) still work as links.
CSP = ("default-src 'none'; style-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'none'")

ROLE_ORDER = {"cited": 0, "context": 1, "reply": 2}
ROLE_LABEL = {
    "cited": "The verse the claim cites",
    "context": "The verses around it",
    "reply": "Also commonly cited in Orthodox responses",
}

REF_RE = re.compile(r"^(?P<c1>\d+):(?P<v1>\d+)(?:-(?:(?P<c2>\d+):)?(?P<v2>\d+))?$")
CITE_RE = re.compile(r"^(?P<book>.+) (?P<ref>\d+:\d+(?:-(?:\d+:)?\d+)?)$")

SEFARIA_BOOK = {
    "Samuel I": "I Samuel", "Samuel II": "II Samuel",
    "Kings I": "I Kings", "Kings II": "II Kings",
    "Chronicles I": "I Chronicles", "Chronicles II": "II Chronicles",
}


def esc(text):
    return html.escape(str(text), quote=True)


def load(name):
    return json.loads((DATA / name).read_text("utf-8"))


def claim_number(claim_id):
    return int(claim_id.split("-")[1])


# ---------------------------------------------------------------- references

def verse_list(ref, chapters):
    """[(chapter, verse), ...] for a ref like '7:10-16' or '52:13-53:12'.

    `chapters` maps chapter number (str) -> list of verses, used to know where
    a chapter ends when a range crosses into the next one.
    """
    m = REF_RE.match(ref)
    if not m:
        raise ValueError(f"Cannot read reference {ref!r}")
    c1, v1 = int(m["c1"]), int(m["v1"])
    c2 = int(m["c2"]) if m["c2"] else c1
    v2 = int(m["v2"]) if m["v2"] else v1
    out = []
    for c in range(c1, c2 + 1):
        first = v1 if c == c1 else 1
        last = v2 if c == c2 else len(chapters[str(c)])
        out.extend((c, v) for v in range(first, last + 1))
    return out


def chabad_url(book, ref, chabad):
    chapter = int(ref.split(":")[0])
    if book == "Genesis":
        aid = chabad["genesis_chapter_ids"][chapter - 1]
    else:
        aid = chabad["first_chapter_id"][book] + chapter - 1
    return f"https://www.chabad.org/library/bible_cdo/aid/{aid}/showrashi/true"


def sefaria_url(book, ref):
    name = SEFARIA_BOOK.get(book, book).replace(" ", "_")
    return f"https://www.sefaria.org/{name}.{ref.replace(':', '.')}?lang=bi&with=Rashi"


# ---------------------------------------------------------------- page parts

def page(title, body, depth, description=""):
    """Wrap `body` in the shared page frame. `depth` = folders below docs/."""
    up = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{up}style.css">
</head>
<body>
<header class="top">
  <a class="brand" href="{up or './'}">Emet</a>
  <nav>
    <a href="{up or './'}">All claims</a>
    <a href="{up}verses/">By verse</a>
    <a href="{up}about/">About</a>
  </nav>
</header>
<main>
{body}
</main>
<footer>
  <p><strong>Unverified draft.</strong> Verse lists have not yet been checked against
  Rabbi Singer or any other rabbinic source. <a href="{up}about/">About this site</a>.</p>
</footer>
</body>
</html>
"""


def verses_html(verses, chapter_text, lang, highlight, show_chapter):
    parts = []
    for c, v in verses:
        text = chapter_text[str(c)][lang][v - 1] if lang else chapter_text[str(c)][v - 1]
        label = f"{c}:{v}" if show_chapter else str(v)
        cls = ' class="hl"' if (c, v) in highlight else ""
        parts.append(f'<span{cls}><sup>{esc(label)}</sup>{esc(text)}</span>')
    return " ".join(parts)


def passage_html(p, tanakh, chabad, highlight):
    book, ref = p["book"], p["ref"]
    chapters = tanakh[book]
    verses = verse_list(ref, {c: t["en"] for c, t in chapters.items()})
    multi_chapter = len({c for c, _ in verses}) > 1

    meta = [f'<span class="role role-{p["role"]}">{esc(ROLE_LABEL[p["role"]])}</span>']
    if p.get("kjv"):
        meta.append(f'<span class="kjvnum">KJV numbers this {esc(p["kjv"])}</span>')
    if p.get("verified"):
        meta.append(f'<span class="verified" title="Verified against {esc(p.get("source") or "")}">'
                    f'&#10003; verified</span>')
    note = f'<p class="note">{esc(p["note"])}</p>' if p.get("note") else ""
    source = (f'<p class="source">Source: {esc(p["source"])}</p>' if p.get("source") else "")

    en = verses_html(verses, chapters, "en", highlight, multi_chapter)
    he = verses_html(verses, chapters, "he", highlight, multi_chapter)
    links = (f'<p class="links"><a href="{esc(chabad_url(book, ref, chabad))}">Chabad.org with Rashi</a>'
             f' · <a href="{esc(sefaria_url(book, ref))}">Sefaria</a></p>')

    text = f"""<div class="he" lang="he" dir="rtl">{he}</div>
<div class="en">{en}</div>
<p class="attrib">JPS 1917 translation. Hebrew and Chabad.org verse numbering.</p>"""

    # The verse the claim cites is always open. Context is folded away, and
    # long reply passages are too, so the page stays short on a phone.
    is_open = p["role"] == "cited" or (p["role"] == "reply" and len(verses) <= 6)
    heading = f'<h3>{esc(book)} {esc(ref)}</h3>'
    if is_open:
        return f"""<section class="passage {p['role']}">
{heading}
<p class="meta">{' '.join(meta)}</p>
{note}{text}
{source}{links}
</section>"""
    return f"""<section class="passage {p['role']}">
<details>
<summary>{heading}<span class="meta">{' '.join(meta)}</span><span class="count">{len(verses)} verses &middot; show</span></summary>
{note}{text}
{source}{links}
</details>
</section>"""


def citation_html(cite, kjv):
    m = CITE_RE.match(cite)
    book, ref = m["book"], m["ref"]
    chapters = kjv[book]
    verses = verse_list(ref, chapters)
    multi = len({c for c, _ in verses}) > 1
    body = verses_html(verses, chapters, None, set(), multi)
    if len(verses) > 8:
        return f"""<details class="cite">
<summary><h3>{esc(cite)} <span class="ed">KJV</span></h3><span class="count">{len(verses)} verses &middot; show</span></summary>
<blockquote>{body}</blockquote>
</details>"""
    return f"""<div class="cite">
<h3>{esc(cite)} <span class="ed">KJV</span></h3>
<blockquote>{body}</blockquote>
</div>"""


def response_html(text):
    if not text.strip():
        return ""
    paras = "".join(f"<p>{esc(p.strip())}</p>" for p in text.split("\n\n") if p.strip())
    return f'<section class="response"><h2>Response</h2>{paras}</section>'


# ---------------------------------------------------------------- pages

def claim_page(i, claims, tanakh, kjv, chabad, status_note):
    claim = claims[i]
    n = claim_number(claim["id"])
    passages = sorted(claim["passages"], key=lambda p: ROLE_ORDER[p["role"]])

    # Verses the claim itself cites, highlighted wherever they appear in a
    # wider passage on the same page.
    highlight = {}
    for p in passages:
        if p["role"] == "cited":
            chapters = {c: t["en"] for c, t in tanakh[p["book"]].items()}
            highlight.setdefault(p["book"], set()).update(verse_list(p["ref"], chapters))

    prev_link = (f'<a rel="prev" href="../{claim_number(claims[i - 1]["id"])}/">&larr; '
                 f'{esc(claims[i - 1]["id"])}</a>') if i > 0 else "<span></span>"
    next_link = (f'<a rel="next" href="../{claim_number(claims[i + 1]["id"])}/">'
                 f'{esc(claims[i + 1]["id"])} &rarr;</a>') if i + 1 < len(claims) else "<span></span>"

    body = f"""<article class="claim">
<p class="claim-id">{esc(claim['id'])}</p>
<h1>{esc(claim['claim'])}</h1>
<p class="draft">{esc(claim.get('status_note') or status_note)}</p>
{response_html(claim.get('response', ''))}
<section class="cited-by-claim">
<h2>What the claim cites</h2>
{''.join(citation_html(c, kjv) for c in claim['cited'])}
</section>
<section class="tanakh">
<h2>The TaNaKh passages</h2>
<p class="hint">Highlighted verses are the ones the claim cites.</p>
{''.join(passage_html(p, tanakh, chabad, set() if p['role'] == 'cited' else highlight.get(p['book'], set())) for p in passages)}
</section>
<nav class="prevnext">{prev_link}<a href="../">All claims</a>{next_link}</nav>
</article>"""
    return page(f"{claim['id']}: {claim['claim']} · Emet", body, depth=1,
                description=claim["claim"])


def index_page(doc):
    claims = doc["claims"]
    grid = "\n".join(
        f'<a href="{claim_number(c["id"])}/" title="{esc(c["claim"])}">{claim_number(c["id"])}</a>'
        for c in claims)
    items = "\n".join(
        f'<li><a href="{claim_number(c["id"])}/"><span class="id">{esc(c["id"])}</span> '
        f'{esc(c["claim"])}</a></li>' for c in claims)
    body = f"""<section class="hero">
<h1>Emet</h1>
<p class="sub">{esc(doc['subtitle'])}</p>
<p class="howto">Following a debate? When a claim number is called out, tap it below,
or add the number to this site's address, for example <code>/42</code>.</p>
</section>
<nav class="grid" aria-label="Claims by number">
{grid}
</nav>
<section>
<h2>All {len(claims)} claims</h2>
<ol class="claim-list">
{items}
</ol>
</section>"""
    return page("Emet: evangelical claims and the TaNaKh passages listed in answer",
                body, depth=0, description=doc["subtitle"])


def verses_page(doc, chabad_books):
    by_book = {}
    for c in doc["claims"]:
        for p in c["passages"]:
            by_book.setdefault(p["book"], {}).setdefault(p["ref"], []).append(c["id"])

    def key(ref):
        m = REF_RE.match(ref)
        return (int(m["c1"]), int(m["v1"]), int(m["c2"] or m["c1"]), int(m["v2"] or m["v1"]))

    sections = []
    for book in chabad_books:
        if book not in by_book:
            continue
        rows = []
        for ref in sorted(by_book[book], key=key):
            ids = sorted(set(by_book[book][ref]))
            links = ", ".join(f'<a href="../{claim_number(i)}/">{esc(i)}</a>' for i in ids)
            rows.append(f"<tr><th>{esc(ref)}</th><td>{links}</td></tr>")
        slug = book.lower().replace(" ", "-")
        sections.append(f'<section id="{esc(slug)}"><h2>{esc(book)}</h2>'
                        f'<table class="verse-index">{"".join(rows)}</table></section>')
    toc = " · ".join(f'<a href="#{esc(b.lower().replace(" ", "-"))}">{esc(b)}</a>'
                     for b in chabad_books if b in by_book)
    body = f"""<h1>TaNaKh passages</h1>
<p>Every passage on this site, in Chabad.org book order and numbering, with the claims it is listed under.</p>
<p class="toc">{toc}</p>
{''.join(sections)}"""
    return page("By verse · Emet", body, depth=1,
                description="Every TaNaKh passage on the site, with the claims it answers.")


def about_page(doc, counts):
    body = f"""<h1>About this site</h1>
<p>Each claim has an ID, the verses it cites, and the TaNaKh passages listed against it.
It holds verse citations, not commentary.</p>
<ul>
<li>The verses a claim cites are given in the numbering of the King James Version, and quoted from it.</li>
<li>TaNaKh passages use the book names and verse numbering of the Chabad.org edition, which
sometimes differ from the King James Version; where they do, the passage says so. Each passage
links to its chapter on Chabad.org, with Rashi, and to Sefaria.</li>
<li>{counts['sourced']} of {counts['passages']} passages name a source, and
{counts['verified']} of {counts['passages']} have been verified against that source.
A verified passage is marked &#10003;.</li>
</ul>
<h2>Status</h2>
<p class="draft">{esc(doc['status_note'])}</p>
<h2>Texts quoted</h2>
<ul>
<li>English TaNaKh: <em>The Holy Scriptures According to the Masoretic Text: A New Translation</em>
(Jewish Publication Society, 1917). Public domain. Text from Sefaria.</li>
<li>Hebrew TaNaKh: <em>Tanach with Nikkud</em>. Public domain. Text from Sefaria.</li>
<li>Verses cited by the claims: King James Version. Public domain. Text from bible-api.com.</li>
</ul>
<p>The JPS 1917 translation is used because it is in the public domain and follows the Hebrew
verse numbering. For a modern translation and Rashi's commentary, follow the Chabad.org link
beside each passage.</p>
<h2>Privacy and safety</h2>
<p>This site is plain HTML and one stylesheet. It runs no scripts, sets no cookies, has no
forms, collects nothing, and loads nothing from any other website. Each page carries a
Content Security Policy that tells the browser to enforce this.</p>"""
    return page("About · Emet", body, depth=1, description="About the Emet site and its sources.")


def not_found_page():
    # GitHub Pages serves this page for any unknown address, at any depth, so
    # it cannot use relative links or the stylesheet. It stands alone.
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>Not found · Emet</title>
</head>
<body>
<h1>Page not found</h1>
<p>To open a claim, put its number after the site's address, for example
<code>/42</code> for claim C-042.</p>
<p>Go back to the site's front page to see every claim.</p>
</body>
</html>
"""


def alias_page(target):
    """A tiny page that forwards /042/ and /C-042/ to the real page /42/."""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta http-equiv="refresh" content="0; url=../{target}/">
<link rel="canonical" href="../{target}/">
<title>Emet</title>
</head>
<body><p><a href="../{target}/">Continue to claim {target}</a></p></body>
</html>
"""


# ---------------------------------------------------------------- checks

def validate(doc, tanakh, kjv, chabad):
    errors = []
    seen = set()
    for c in doc["claims"]:
        if not re.fullmatch(r"C-\d{3}", c["id"]) or c["id"] in seen:
            errors.append(f"bad or duplicate id {c['id']!r}")
        seen.add(c["id"])
        for cite in c["cited"]:
            m = CITE_RE.match(cite)
            try:
                verse_list(m["ref"], kjv[m["book"]])
            except Exception as e:  # noqa: BLE001 - report every problem at once
                errors.append(f"{c['id']}: no KJV text for {cite!r} ({e}); run tools/fetch_texts.py")
        for p in c["passages"]:
            if p["role"] not in ROLE_ORDER:
                errors.append(f"{c['id']}: unknown role {p['role']!r}")
            if p["book"] != "Genesis" and p["book"] not in chabad["first_chapter_id"]:
                errors.append(f"{c['id']}: no Chabad.org chapter ID for book {p['book']!r}")
            try:
                verse_list(p["ref"], {k: v["en"] for k, v in tanakh[p["book"]].items()})
            except Exception as e:  # noqa: BLE001
                errors.append(f"{c['id']}: no text for {p['book']} {p['ref']} ({e}); run tools/fetch_texts.py")
    if errors:
        sys.exit("Data problems:\n  " + "\n  ".join(errors))


FORBIDDEN = [
    (re.compile(r"<\s*script", re.I), "a <script> tag"),
    (re.compile(r"<\s*(iframe|object|embed|form|input|base)\b", re.I), "an iframe/object/embed/form/input/base tag"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "an inline event handler (onclick= etc.)"),
    (re.compile(r"javascript:", re.I), "a javascript: link"),
    (re.compile(r"<(link|img|source|video|audio)\b[^>]*\b(href|src)=\"(https?:)?//", re.I),
     "a resource loaded from another website"),
    (re.compile(r"@import|url\(\s*['\"]?(https?:)?//", re.I), "a stylesheet loading from another website"),
]


def check_output():
    problems = []
    for path in sorted(OUT.rglob("*")):
        if path.is_dir():
            continue
        if path.suffix not in {".html", ".css"} and path.name != ".nojekyll":
            problems.append(f"{path.relative_to(ROOT)}: unexpected file type")
            continue
        text = path.read_text("utf-8")
        if path.suffix == ".html" and CSP not in text:
            problems.append(f"{path.relative_to(ROOT)}: missing Content-Security-Policy")
        for pattern, what in FORBIDDEN:
            if pattern.search(text):
                problems.append(f"{path.relative_to(ROOT)}: contains {what}")
    if problems:
        sys.exit("Safety check failed:\n  " + "\n  ".join(problems))


# ---------------------------------------------------------------- main

def write(rel, text):
    path = OUT / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def main():
    doc = load("claims.json")
    tanakh = load("texts/tanakh.json")
    kjv = load("texts/kjv.json")
    chabad = load("chabad_chapters.json")
    validate(doc, tanakh, kjv, chabad)

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    (OUT / ".nojekyll").write_text("")  # serve files as-is, no Jekyll processing
    shutil.copy(ROOT / "site" / "style.css", OUT / "style.css")

    claims = doc["claims"]
    for i, claim in enumerate(claims):
        n = claim_number(claim["id"])
        write(f"{n}/index.html", claim_page(i, claims, tanakh, kjv, chabad, doc["status_note"]))
        # So that /042, /C-042 and /c-042 also reach /42 (GitHub Pages is case-sensitive).
        for alias in {f"{n:03d}", claim["id"], claim["id"].lower()} - {str(n)}:
            write(f"{alias}/index.html", alias_page(n))

    book_order = ["Genesis"] + list(chabad["first_chapter_id"].keys())
    # Chabad.org order: Torah, Prophets, then Writings.
    write("index.html", index_page(doc))
    write("verses/index.html", verses_page(doc, book_order))
    passages = [p for c in claims for p in c["passages"]]
    counts = {"passages": len(passages),
              "sourced": sum(1 for p in passages if p.get("source")),
              "verified": sum(1 for p in passages if p.get("verified"))}
    write("about/index.html", about_page(doc, counts))
    write("404.html", not_found_page())

    check_output()
    print(f"Built {len(claims)} claim pages into {OUT.relative_to(ROOT)}/ - safety check passed.")


if __name__ == "__main__":
    main()
