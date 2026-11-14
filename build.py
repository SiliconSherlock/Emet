#!/usr/bin/env python3
"""Build the Emet static website from the data files.

    python3 build.py

Reads   data/claims.json            the claims and the passages listed against them
        data/texts/tanakh.json      JPS 1917 English + Hebrew text (public domain)
        data/texts/kjv.json         King James Version text (public domain)
        data/chabad_chapters.json   Chabad.org chapter IDs, for links
        site/style.css              the one stylesheet
        site/workbench.js           the one script (search and filters on the front page)
Writes  docs/                       the finished website (GitHub Pages serves this folder)

Uses only the Python standard library and does not touch the network.

Every piece of text from the data files is HTML-escaped before it is written,
so nothing in the data can add markup or scripts to a page. When it finishes,
the build runs check_output() over everything it wrote and refuses to finish
if any page contains a script other than site/workbench.js, an inline event
handler, a frame other than the front page's reader pane, or loads anything
from another website.
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
SCRIPT = "workbench.js"

# One policy for every page. Scripts, styles and frames may come only from this
# site (there is exactly one script, workbench.js, and one frame, the reader
# pane on the front page). Nothing else may be loaded, and the browser blocks
# all network requests from the script (default-src 'none'). Forms may submit
# only to this site. Links to Chabad.org and Sefaria still work as links.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "frame-src 'self'; base-uri 'none'; form-action 'self'")

ROLE_ORDER = {"cited": 0, "context": 1, "reply": 2}
ROLE_GROUP = {
    "cited": "The verse the claim cites",
    "context": "Read it in context",
    "reply": "Also cited in Orthodox responses",
}

REF_RE = re.compile(r"^(?P<c1>\d+):(?P<v1>\d+)(?:-(?:(?P<c2>\d+):)?(?P<v2>\d+))?$")
CITE_RE = re.compile(r"^(?P<book>.+) (?P<ref>\d+:\d+(?:-(?:\d+:)?\d+)?)$")

SEFARIA_BOOK = {
    "Samuel I": "I Samuel", "Samuel II": "II Samuel",
    "Kings I": "I Kings", "Kings II": "II Kings",
    "Chronicles I": "I Chronicles", "Chronicles II": "II Chronicles",
}

# Citations use King James book names; TaNaKh passages use Chabad.org names.
# The book filter uses the Chabad.org name for TaNaKh books.
KJV_TO_TANAKH = {
    "1 Samuel": "Samuel I", "2 Samuel": "Samuel II",
    "1 Kings": "Kings I", "2 Kings": "Kings II",
    "1 Chronicles": "Chronicles I", "2 Chronicles": "Chronicles II",
    "Song of Solomon": "Song of Songs",
}
TANAKH_TO_KJV = {v: k for k, v in KJV_TO_TANAKH.items()}

BOOK_GROUPS = [
    ("Torah", ["Genesis", "Exodus", "Leviticus", "Numbers", "Deuteronomy"]),
    ("Prophets", ["Joshua", "Judges", "Samuel I", "Samuel II", "Kings I", "Kings II",
                  "Isaiah", "Jeremiah", "Ezekiel", "Hosea", "Joel", "Amos", "Obadiah",
                  "Jonah", "Micah", "Nahum", "Habakkuk", "Zephaniah", "Haggai",
                  "Zechariah", "Malachi"]),
    ("Writings", ["Psalms", "Proverbs", "Job", "Song of Songs", "Ruth", "Lamentations",
                  "Ecclesiastes", "Esther", "Daniel", "Ezra", "Nehemiah",
                  "Chronicles I", "Chronicles II"]),
    ("New Testament", ["Matthew", "Mark", "Luke", "John", "Acts", "Romans",
                       "1 Corinthians", "2 Corinthians", "Galatians", "Ephesians",
                       "Philippians", "Colossians", "1 Thessalonians", "2 Thessalonians",
                       "1 Timothy", "2 Timothy", "Titus", "Philemon", "Hebrews", "James",
                       "1 Peter", "2 Peter", "1 John", "2 John", "3 John", "Jude",
                       "Revelation"]),
]
BOOK_ORDER = [b for _, books in BOOK_GROUPS for b in books]

# The reader pane on the front page. The frame may only show this site's own
# pages, which run no script; the sandbox also stops it from running script,
# submitting forms, or navigating the main window except when clicked.
READER_IFRAME = ('<iframe id="reader" name="reader" title="Selected claim" src="welcome.html" '
                 'sandbox="allow-same-origin allow-popups allow-popups-to-escape-sandbox '
                 'allow-top-navigation-by-user-activation"></iframe>')
SCRIPT_TAG = f'<script src="{SCRIPT}" defer></script>'


def esc(text):
    return html.escape(str(text), quote=True)


def load(name):
    return json.loads((DATA / name).read_text("utf-8"))


def claim_number(claim_id):
    return int(claim_id.split("-")[1])


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def cite_book(cite):
    """The book a citation is from, under its book-filter name."""
    book = CITE_RE.match(cite)["book"]
    return KJV_TO_TANAKH.get(book, book)


def passage_anchor(p):
    return f'p-{slug(p["book"])}-{slug(p["ref"])}'


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


# ---------------------------------------------------------------- page frames

def head(title, up, description="", script=False):
    js = f"\n{SCRIPT_TAG}" if script else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>{esc(title)}</title>
<meta name="description" content="{esc(description)}">
<link rel="stylesheet" href="{up}style.css">{js}
</head>"""


def page(title, body, depth, description="", workbench=False):
    """A full page with the site header. `depth` = folders below docs/."""
    up = "../" * depth
    home = up or "./"
    search = "" if workbench else f"""
  <form class="top-search" role="search" action="{home}" method="get">
    <label class="visually-hidden" for="top-q">Search claims</label>
    <input id="top-q" type="search" name="q" placeholder="Search, or a claim number" autocomplete="off">
    <button type="submit">Search</button>
  </form>"""
    footer = "" if workbench else f"""
<footer>
  <p><strong>Unverified draft.</strong> Verse lists have not yet been checked against
  Rabbi Singer or any other rabbinic source. <a href="{up}about/">About this site</a>.</p>
</footer>"""
    return f"""{head(title, up, description, script=workbench)}
<body class="{'app' if workbench else 'doc'}">
<header class="top"><div class="top-inner">
  <a class="brand" href="{home}">Emet <span lang="he">אמת</span></a>
  <nav>
    <a href="{home}"{' aria-current="page"' if workbench else ''}>Claims</a>
    <a href="{up}verses/">Passages</a>
    <a href="{up}about/">About</a>
  </nav>{search}
</div></header>
<main{' class="wide"' if workbench else ''}>
{body}
</main>{footer}
</body>
</html>
"""


def panel(title, body, up):
    """A bare page for the front page's reader pane: no header or footer."""
    return f"""{head(title, up)}
<body class="panel">
{body}
</body>
</html>
"""


# ---------------------------------------------------------------- page parts

def verses_html(verses, chapter_text, lang, highlight, show_chapter):
    parts = []
    for c, v in verses:
        text = chapter_text[str(c)][lang][v - 1] if lang else chapter_text[str(c)][v - 1]
        label = f"{c}:{v}" if show_chapter else str(v)
        cls = ' class="hl"' if (c, v) in highlight else ""
        parts.append(f'<span{cls}><sup>{esc(label)}</sup>{esc(text)}</span>')
    return " ".join(parts)


def passage_html(p, anchor, tanakh, chabad, highlight, ext):
    book, ref = p["book"], p["ref"]
    chapters = tanakh[book]
    verses = verse_list(ref, {c: t["en"] for c, t in chapters.items()})
    multi_chapter = len({c for c, _ in verses}) > 1

    badges = []
    if p.get("kjv"):
        badges.append(f'<span class="badge">KJV: {esc(p["kjv"])}</span>')
    if p.get("verified"):
        badges.append('<span class="badge verified">&#10003; verified</span>')
    note = f'<p class="note">{esc(p["note"])}</p>' if p.get("note") else ""
    source = f'<p class="source">Source: {esc(p["source"])}</p>' if p.get("source") else ""

    en = verses_html(verses, chapters, "en", highlight, multi_chapter)
    he = verses_html(verses, chapters, "he", highlight, multi_chapter)
    count = f'{len(verses)} verse{"s" if len(verses) != 1 else ""}'
    title = f'<h4>{esc(book)} {esc(ref)}</h4>{"".join(badges)}'

    inner = f"""<div class="p-body">
{note}<div class="he" lang="he" dir="rtl">{he}</div>
<div class="en">{en}</div>
{source}</div>
<div class="p-foot">
<span class="attrib">JPS 1917 · Hebrew verse numbering</span>
<span class="links"><a class="btn" href="{esc(chabad_url(book, ref, chabad))}"{ext}>Chabad.org + Rashi</a>
<a class="btn" href="{esc(sefaria_url(book, ref))}"{ext}>Sefaria</a></span>
</div>"""

    # The verse the claim cites is always open. Context is folded away, and
    # long reply passages are too, so the page stays short on a phone.
    if p["role"] == "cited" or (p["role"] == "reply" and len(verses) <= 6):
        return f"""<section class="passage {p['role']}" id="{anchor}">
<div class="p-head">{title}</div>
{inner}
</section>"""
    return f"""<details class="passage {p['role']}" id="{anchor}">
<summary class="p-head">{title}<span class="count">{count}</span><span class="toggle"></span></summary>
{inner}
</details>"""


def citation_html(index, cite, kjv):
    m = CITE_RE.match(cite)
    book, ref = m["book"], m["ref"]
    chapters = kjv[book]
    verses = verse_list(ref, chapters)
    multi = len({c for c, _ in verses}) > 1
    body = verses_html(verses, chapters, None, set(), multi)
    head_html = f'<h3>{esc(cite)}</h3><span class="ed">KJV</span>'
    if len(verses) > 8:
        return f"""<details class="cite" id="cite-{index}">
<summary class="cite-head">{head_html}<span class="count">{len(verses)} verses</span><span class="toggle"></span></summary>
<blockquote>{body}</blockquote>
</details>"""
    return f"""<div class="cite" id="cite-{index}">
<div class="cite-head">{head_html}</div>
<blockquote>{body}</blockquote>
</div>"""


def response_html(text):
    if not text.strip():
        return ""
    paras = "".join(f"<p>{esc(p.strip())}</p>" for p in text.split("\n\n") if p.strip())
    return f'<section class="response card"><h2>Response</h2>{paras}</section>'


def cited_books(claim):
    return sorted({cite_book(c) for c in claim["cited"]}, key=BOOK_ORDER.index)


def answer_books(claim):
    return sorted({p["book"] for p in claim["passages"]}, key=BOOK_ORDER.index)


def search_text(claim):
    """Everything the search box should find this claim by, in lower case."""
    parts = [claim["id"], str(claim_number(claim["id"])), claim["claim"], claim.get("response", "")]
    for cite in claim["cited"]:
        parts.append(cite)
        parts.append(cite_book(cite))  # so "Samuel I" finds "1 Samuel 7:12"
    for p in claim["passages"]:
        parts.append(f'{p["book"]} {p["ref"]}')
        parts.append(TANAKH_TO_KJV.get(p["book"], ""))  # so "1 Samuel" finds "Samuel I"
        parts.extend(p.get(k) or "" for k in ("kjv", "note", "source"))
    return " ".join(x for x in parts if x).lower()


def anchors_for(passages):
    """A unique id for each passage on a claim page, in display order."""
    seen, out = {}, []
    for p in passages:
        a = passage_anchor(p)
        seen[a] = seen.get(a, 0) + 1
        out.append(a if seen[a] == 1 else f"{a}-{seen[a]}")
    return out


# ---------------------------------------------------------------- claim pages

def claim_article(i, claims, tanakh, kjv, chabad, status_note, in_panel):
    """The body of a claim: used for the full page /n/ and the reader pane /n/panel.html."""
    claim = claims[i]
    n = claim_number(claim["id"])
    passages = sorted(claim["passages"], key=lambda p: ROLE_ORDER[p["role"]])
    anchors = anchors_for(passages)
    # In the reader pane, site links open in the main window and other sites in a new tab.
    top = ' target="_top"' if in_panel else ""
    ext = ' target="_blank" rel="noopener"' if in_panel else ""

    # Verses the claim itself cites, highlighted wherever they appear in a
    # wider passage on the same page.
    highlight = {}
    for p in passages:
        if p["role"] == "cited":
            chapters = {c: t["en"] for c, t in tanakh[p["book"]].items()}
            highlight.setdefault(p["book"], set()).update(verse_list(p["ref"], chapters))

    groups, toc = [], []
    for role in ROLE_ORDER:
        these = [(p, a) for p, a in zip(passages, anchors) if p["role"] == role]
        if not these:
            continue
        hint = ('<p class="hint">Highlighted verses are the ones the claim cites.</p>'
                if role == "context" and highlight else "")
        cards = "".join(passage_html(p, a, tanakh, chabad,
                                     set() if role == "cited" else highlight.get(p["book"], set()), ext)
                        for p, a in these)
        groups.append(f'<h3 class="group-h {role}">{esc(ROLE_GROUP[role])}</h3>{hint}{cards}')
        toc.extend(f'<li><a class="chip {role}" href="#{a}">{esc(p["book"])} {esc(p["ref"])}</a></li>'
                   for p, a in these)

    cites = "".join(f'<li><a class="chip ext" href="#cite-{k}">{esc(c)}</a></li>'
                    for k, c in enumerate(claim["cited"], 1))

    def book_links(books, where):
        return " ".join(f'<a class="tag" href="../?book={slug(b)}&amp;in={where}"{top}>{esc(b)}</a>'
                        for b in books)

    actions = (f'<a class="btn" href="./" target="_top">Open full page &#8599;</a>' if in_panel
               else f'<a class="btn" href="../?c={n}">Open in workbench</a>')

    return f"""<article class="claim">
<header class="card claim-head">
<div class="claim-top"><p class="claim-id">{esc(claim['id'])}</p>{actions}</div>
<h1>{esc(claim['claim'])}</h1>
<dl class="facts">
<dt>Cites</dt><dd><ul class="chips">{cites}</ul></dd>
<dt>Answered from</dt><dd><ul class="chips">{''.join(toc)}</ul></dd>
<dt>More claims</dt><dd class="tags"><span class="sep">citing</span> {book_links(cited_books(claim), 'cites')}
<span class="sep">answered from</span> {book_links(answer_books(claim), 'answers')}</dd>
</dl>
</header>
<p class="draft">{esc(claim.get('status_note') or status_note)}</p>
{response_html(claim.get('response', ''))}
<section class="cited-by-claim">
<h2>What the claim cites</h2>
{''.join(citation_html(k, c, kjv) for k, c in enumerate(claim['cited'], 1))}
</section>
<section class="tanakh">
<h2>The TaNaKh passages</h2>
{''.join(groups)}
</section>
</article>"""


def claim_page(i, claims, tanakh, kjv, chabad, status_note):
    claim = claims[i]

    def nav_link(j, rel, label):
        if not 0 <= j < len(claims):
            return "<span></span>"
        return f'<a class="btn" rel="{rel}" href="../{claim_number(claims[j]["id"])}/">{label}</a>'

    prev_link = nav_link(i - 1, "prev", f'&larr; {esc(claims[i - 1]["id"])}' if i > 0 else "")
    next_link = nav_link(i + 1, "next", f'{esc(claims[i + 1]["id"])} &rarr;' if i + 1 < len(claims) else "")
    body = (claim_article(i, claims, tanakh, kjv, chabad, status_note, in_panel=False)
            + f'\n<nav class="prevnext">{prev_link}<a class="btn" href="../">All claims</a>{next_link}</nav>')
    return page(f"{claim['id']}: {claim['claim']} · Emet", body, depth=1, description=claim["claim"])


def claim_panel(i, claims, tanakh, kjv, chabad, status_note):
    claim = claims[i]
    body = claim_article(i, claims, tanakh, kjv, chabad, status_note, in_panel=True)
    return panel(f"{claim['id']} · Emet", body, up="../")


# ---------------------------------------------------------------- front page

def book_options(claims):
    counts = {}
    for c in claims:
        for b in set(cited_books(c)) | set(answer_books(c)):
            counts[b] = counts.get(b, 0) + 1
    groups = []
    for group, books in BOOK_GROUPS:
        opts = "".join(f'<option value="{slug(b)}">{esc(b)} ({counts[b]})</option>'
                       for b in books if b in counts)
        if opts:
            groups.append(f'<optgroup label="{esc(group)}">{opts}</optgroup>')
    return "".join(groups)


def result_row(claim):
    n = claim_number(claim["id"])
    cites = " ".join(slug(b) for b in cited_books(claim))
    answers = " ".join(slug(b) for b in answer_books(claim))
    count = len(claim["passages"])
    return (f'<li data-n="{n}" data-search="{esc(search_text(claim))}" '
            f'data-cites="{cites}" data-answers="{answers}">'
            f'<a class="row" href="{n}/">'
            f'<span class="id">{esc(claim["id"])}</span>'
            f'<span class="text">{esc(claim["claim"])}</span>'
            f'<span class="refs">{esc(" · ".join(claim["cited"]))}</span>'
            f'<span class="pcount">{count} passage{"s" if count != 1 else ""}</span>'
            f'</a></li>')


def index_page(doc):
    claims = doc["claims"]
    grid = "".join(f'<a href="{claim_number(c["id"])}/">{claim_number(c["id"])}</a>' for c in claims)
    rows = "\n".join(result_row(c) for c in claims)
    body = f"""<div class="workbench">
<aside class="wb-side" aria-label="Find claims">
<p class="intro">{esc(doc['subtitle'])}.</p>
<form id="search" class="filters" role="search" action="./" method="get">
  <label class="field-label" for="q">Search</label>
  <div class="search-row">
    <input id="q" type="search" name="q" placeholder="42, virgin, Isaiah 53" autocomplete="off" spellcheck="false">
    <button type="submit">Go</button>
  </div>
  <p class="kbd-hint">A number + <kbd>Enter</kbd> opens that claim. <kbd>/</kbd> jumps here.</p>
  <label class="field-label" for="book">Book</label>
  <select id="book" name="book"><option value="">All books</option>{book_options(claims)}</select>
  <fieldset id="where" class="seg">
    <legend class="visually-hidden">Where the book appears</legend>
    <label><input type="radio" name="in" value="" checked><span>Anywhere</span></label>
    <label><input type="radio" name="in" value="cites"><span>Cited</span></label>
    <label><input type="radio" name="in" value="answers"><span>In answer</span></label>
  </fieldset>
  <p class="clear"><a href="./">Clear search and filters</a></p>
</form>
<details id="numbers" class="numbers">
<summary>Jump to a claim number</summary>
<nav class="grid" aria-label="Claims by number">{grid}</nav>
</details>
<p class="draft side-draft">Unverified draft. <a href="about/">About this site</a>.</p>
</aside>
<section class="wb-results" aria-labelledby="list-heading">
<div class="results-head">
<h2 id="list-heading">All {len(claims)} claims</h2>
<p id="search-status" class="search-status" role="status" aria-live="polite"></p>
</div>
<ol id="claims" class="results">
{rows}
</ol>
</section>
<section id="reader-pane" class="wb-reader" aria-label="Reader">
{READER_IFRAME}
</section>
</div>"""
    return page("Emet: evangelical claims and the TaNaKh passages listed in answer",
                body, depth=0, description=doc["subtitle"], workbench=True)


def welcome_panel(doc, counts):
    body = f"""<div class="welcome">
<h1>Emet <span lang="he">אמת</span></h1>
<p class="lede">{esc(doc['subtitle'])}.</p>
<p>Pick a claim from the list to read it here. Its full page is one click away.</p>
<h2>Finding claims</h2>
<ul>
<li><strong>By number.</strong> Type <kbd>42</kbd> and press <kbd>Enter</kbd>. In a debate,
the address <code>/42</code> works too.</li>
<li><strong>By words or verse.</strong> <em>virgin</em>, <em>suffering servant</em>,
<em>Isaiah 53</em>. Every word must appear; matches are highlighted.</li>
<li><strong>By book.</strong> Choose a book, then whether the claim <em>cites</em> it or is
<em>answered</em> from it.</li>
<li><strong>Keys.</strong> <kbd>/</kbd> to search, <kbd>&uarr;</kbd> <kbd>&darr;</kbd> to step
through the results.</li>
</ul>
<h2>Reading a claim</h2>
<ul class="legend">
<li><span class="dot cited"></span>The verse the claim cites, in Hebrew and JPS 1917 English.</li>
<li><span class="dot context"></span>The verses around it, folded; the cited verse is highlighted.</li>
<li><span class="dot reply"></span>Passages also cited in Orthodox responses.</li>
</ul>
<p class="stats">{counts['claims']} claims · {counts['passages']} TaNaKh passages ·
{counts['verified']} verified</p>
<p class="draft">{esc(doc['status_note'])}</p>
</div>"""
    return panel("Emet", body, up="")


# ---------------------------------------------------------------- other pages

def verses_page(doc):
    by_book = {}
    for c in doc["claims"]:
        passages = sorted(c["passages"], key=lambda p: ROLE_ORDER[p["role"]])
        for p, a in zip(passages, anchors_for(passages)):
            refs = by_book.setdefault(p["book"], {}).setdefault(p["ref"], {})
            refs.setdefault(c["id"], a)

    def key(ref):
        m = REF_RE.match(ref)
        return (int(m["c1"]), int(m["v1"]), int(m["c2"] or m["c1"]), int(m["v2"] or m["v1"]))

    books = [b for b in BOOK_ORDER if b in by_book]
    sections = []
    for book in books:
        rows = []
        for ref in sorted(by_book[book], key=key):
            links = " ".join(f'<a class="chip" href="../{claim_number(i)}/#{a}">{esc(i)}</a>'
                             for i, a in sorted(by_book[book][ref].items()))
            rows.append(f"<tr><th>{esc(ref)}</th><td>{links}</td></tr>")
        sections.append(f'<section id="{slug(book)}" class="card verse-book">'
                        f'<h2>{esc(book)} <a class="more" href="../?book={slug(book)}&amp;in=answers">'
                        f'Open in workbench</a></h2>'
                        f'<table class="verse-index">{"".join(rows)}</table></section>')
    toc = "".join(f'<a class="chip" href="#{slug(b)}">{esc(b)}</a>' for b in books)
    body = f"""<h1>TaNaKh passages</h1>
<p class="lede">Every passage on this site, in Chabad.org book order and numbering. Each claim
link opens that claim at the passage.</p>
<p class="chips toc">{toc}</p>
{''.join(sections)}"""
    return page("Passages · Emet", body, depth=1,
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
<h2>Finding a claim</h2>
<ul>
<li>Type a claim's number after the site's address, for example <code>/42</code>.</li>
<li>On the <a href="../">front page</a>, search by number, words or verse, and filter by book:
claims that cite the book, or that are answered from it. On a wide screen the claim you pick
opens in a reader beside the list.</li>
<li>Or look up a passage in the <a href="../verses/">passage index</a>.</li>
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
<p>This site is static: plain HTML pages, one stylesheet, and one short script that runs the
search and filters on the front page. It sets no cookies, collects nothing, sends nothing,
and loads nothing from any other website. Each page carries a Content Security Policy that
tells the browser to enforce this.</p>"""
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
            if not m or cite_book(cite) not in BOOK_ORDER:
                errors.append(f"{c['id']}: cannot read citation {cite!r}")
                continue
            try:
                verse_list(m["ref"], kjv[m["book"]])
            except Exception as e:  # noqa: BLE001 - report every problem at once
                errors.append(f"{c['id']}: no KJV text for {cite!r} ({e}); run tools/fetch_texts.py")
        for p in c["passages"]:
            if p["role"] not in ROLE_ORDER:
                errors.append(f"{c['id']}: unknown role {p['role']!r}")
            if p["book"] not in BOOK_ORDER:
                errors.append(f"{c['id']}: unknown book {p['book']!r}")
            if p["book"] != "Genesis" and p["book"] not in chabad["first_chapter_id"]:
                errors.append(f"{c['id']}: no Chabad.org chapter ID for book {p['book']!r}")
            try:
                verse_list(p["ref"], {k: v["en"] for k, v in tanakh[p["book"]].items()})
            except Exception as e:  # noqa: BLE001
                errors.append(f"{c['id']}: no text for {p['book']} {p['ref']} ({e}); run tools/fetch_texts.py")
    if errors:
        sys.exit("Data problems:\n  " + "\n  ".join(errors))


# Things no HTML page may contain.
FORBIDDEN_HTML = [
    (re.compile(r"<\s*(object|embed|base|frame|frameset|applet)\b", re.I), "an object/embed/base/frame tag"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "an inline event handler (onclick= etc.)"),
    (re.compile(r"javascript:", re.I), "a javascript: link"),
    (re.compile(r"<(link|img|source|video|audio|script|iframe)\b[^>]*\b(href|src)=\"(https?:)?//", re.I),
     "a resource loaded from another website"),
    (re.compile(r"<\s*form\b(?![^>]*\baction=\"(\.\./)*(\./)?index\.html\")", re.I),
     "a form that submits anywhere but this site's front page"),
    (re.compile(r"<\s*input\b(?![^>]*\btype=\"(search|radio)\")", re.I),
     "an input other than a search box or a filter option"),
    (re.compile(r"@import|url\(\s*['\"]?(https?:)?//", re.I), "a stylesheet loading from another website"),
]

# Things the script may not do. It needs none of them to filter a list.
FORBIDDEN_JS = [
    "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function(",
    "setTimeout(", "setInterval(", "fetch(", "XMLHttpRequest", "WebSocket", "EventSource",
    "sendBeacon", "import(", "importScripts", "Worker(", "cookie", "localStorage",
    "sessionStorage", "indexedDB", "postMessage", "window.open", "http:", "https:",
    "srcdoc", "javascript:", "contentDocument", "contentWindow",
]


def check_output():
    problems = []
    for path in sorted(OUT.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(OUT).as_posix()
        text = path.read_text("utf-8")
        if path.suffix == ".js":
            if rel != SCRIPT or text != (ROOT / "site" / SCRIPT).read_text("utf-8"):
                problems.append(f"docs/{rel}: unexpected script file")
            # Check the code itself, not the comments that explain it.
            code = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
            code = re.sub(r"^\s*//.*$", "", code, flags=re.M)
            for word in FORBIDDEN_JS:
                if word in code:
                    problems.append(f"docs/{rel}: script uses {word!r}")
            continue
        if path.suffix not in {".html", ".css"} and path.name != ".nojekyll":
            problems.append(f"docs/{rel}: unexpected file type")
            continue
        if path.suffix == ".html":
            if CSP not in text:
                problems.append(f"docs/{rel}: missing Content-Security-Policy")
            front = rel == "index.html"
            scripts = re.findall(r"<\s*script\b[^>]*>(?:.*?</\s*script\s*>)?", text, re.I | re.S)
            if scripts != ([SCRIPT_TAG] if front else []):
                problems.append(f"docs/{rel}: unexpected script tags {scripts!r}")
            frames = re.findall(r"<\s*iframe\b[^>]*>", text, re.I)
            if frames != ([READER_IFRAME.split("</iframe>")[0]] if front else []):
                problems.append(f"docs/{rel}: unexpected iframe tags {frames!r}")
        for pattern, what in FORBIDDEN_HTML:
            if pattern.search(text):
                problems.append(f"docs/{rel}: contains {what}")
    if problems:
        sys.exit("Safety check failed:\n  " + "\n  ".join(problems))


# ---------------------------------------------------------------- main

# Links to this site's folders ("../about/", "./", "../?book=isaiah") are
# written as links to the folder's index.html file instead. A web server such
# as GitHub Pages does that by itself, but a page opened straight from disk
# (file://) would otherwise show a directory listing.
FOLDER_LINK = re.compile(r'(\b(?:href|action)="|url=)((?:\.\./|\./)*(?:[^"?#:/]+/)*)(?=[?#"])')


def link_files(text):
    def fix(m):
        folder = m[2]
        return m[1] + folder + "index.html" if folder.endswith("/") else m[0]
    return FOLDER_LINK.sub(fix, text)


def write(rel, text):
    if rel.endswith(".html"):
        text = link_files(text)
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
    shutil.copy(ROOT / "site" / SCRIPT, OUT / SCRIPT)

    claims = doc["claims"]
    for i, claim in enumerate(claims):
        n = claim_number(claim["id"])
        args = (i, claims, tanakh, kjv, chabad, doc["status_note"])
        write(f"{n}/index.html", claim_page(*args))
        write(f"{n}/panel.html", claim_panel(*args))
        # So that /042, /C-042 and /c-042 also reach /42 (GitHub Pages is case-sensitive).
        for alias in {f"{n:03d}", claim["id"], claim["id"].lower()} - {str(n)}:
            write(f"{alias}/index.html", alias_page(n))

    passages = [p for c in claims for p in c["passages"]]
    counts = {"claims": len(claims), "passages": len(passages),
              "sourced": sum(1 for p in passages if p.get("source")),
              "verified": sum(1 for p in passages if p.get("verified"))}
    write("index.html", index_page(doc))
    write("welcome.html", welcome_panel(doc, counts))
    write("verses/index.html", verses_page(doc))
    write("about/index.html", about_page(doc, counts))
    write("404.html", not_found_page())

    check_output()
    print(f"Built {len(claims)} claims (full pages and reader panels) into "
          f"{OUT.relative_to(ROOT)}/ - safety check passed.")


if __name__ == "__main__":
    main()
