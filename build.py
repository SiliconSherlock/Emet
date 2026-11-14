#!/usr/bin/env python3
"""Build the Emet static website from the data files.

    python3 build.py

Reads   data/claims.json            the claims and the passages listed against them
        data/texts/tanakh.json      JPS 1917 English + Hebrew text (public domain)
        data/texts/kjv.json         King James Version text (public domain)
        data/chabad_chapters.json   Chabad.org chapter IDs, for links
        site/style.css              the one stylesheet
        site/search.js              the one script (the search box)
Writes  docs/                       the finished website (GitHub Pages serves this folder)

Uses only the Python standard library and does not touch the network.

Every piece of text from the data files is HTML-escaped before it is written,
so nothing in the data can add markup or scripts to a page. When it finishes,
the build runs check_output() over everything it wrote and refuses to finish
if any page contains a script other than site/search.js, an inline event
handler, an iframe/object/embed, or loads anything from another website.
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

# One policy for every page. Scripts and styles may come only from this site
# (there is exactly one script, search.js). Nothing else may be loaded, and the
# browser blocks all network requests from the script (default-src 'none').
# Search boxes may submit only to this site. Links to Chabad.org and Sefaria
# still work as ordinary links.
CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; "
       "base-uri 'none'; form-action 'self'")

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
# Book pages use the Chabad.org name for TaNaKh books.
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


def esc(text):
    return html.escape(str(text), quote=True)


def load(name):
    return json.loads((DATA / name).read_text("utf-8"))


def claim_number(claim_id):
    return int(claim_id.split("-")[1])


def slug(book):
    return book.lower().replace(" ", "-")


def cite_book(cite):
    """The book a citation is from, under its book-page name."""
    book = CITE_RE.match(cite)["book"]
    return KJV_TO_TANAKH.get(book, book)


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

def page(title, body, depth, description="", header_search=True, script=False):
    """Wrap `body` in the shared page frame. `depth` = folders below docs/."""
    up = "../" * depth
    home = up or "./"
    search = f"""
  <form class="top-search" role="search" action="{home}" method="get">
    <label class="visually-hidden" for="top-q">Search claims</label>
    <input id="top-q" type="search" name="q" placeholder="Search claims or a number" autocomplete="off">
    <button type="submit">Search</button>
  </form>""" if header_search else ""
    # Only the front page loads the script; every other page has none.
    js = '\n<script src="search.js" defer></script>' if script else ""
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
</head>
<body>
<header class="top"><div class="top-inner">
  <a class="brand" href="{home}">Emet <span lang="he">אמת</span></a>
  <nav>
    <a href="{home}">Claims</a>
    <a href="{up}books/">Books</a>
    <a href="{up}verses/">Passages</a>
    <a href="{up}about/">About</a>
  </nav>{search}
</div></header>
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

    badges = []
    if p.get("kjv"):
        badges.append(f'<span class="badge">KJV: {esc(p["kjv"])}</span>')
    if p.get("verified"):
        badges.append(f'<span class="badge verified">&#10003; verified</span>')
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
<span class="links"><a class="btn" href="{esc(chabad_url(book, ref, chabad))}">Chabad.org + Rashi</a>
<a class="btn" href="{esc(sefaria_url(book, ref))}">Sefaria</a></span>
</div>"""

    # The verse the claim cites is always open. Context is folded away, and
    # long reply passages are too, so the page stays short on a phone.
    if p["role"] == "cited" or (p["role"] == "reply" and len(verses) <= 6):
        return f"""<section class="passage {p['role']}">
<div class="p-head">{title}</div>
{inner}
</section>"""
    return f"""<details class="passage {p['role']}">
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
    head = f'<h3>{esc(cite)}</h3><span class="ed">KJV</span>'
    if len(verses) > 8:
        return f"""<details class="cite" id="cite-{index}">
<summary class="cite-head">{head}<span class="count">{len(verses)} verses</span><span class="toggle"></span></summary>
<blockquote>{body}</blockquote>
</details>"""
    return f"""<div class="cite" id="cite-{index}">
<div class="cite-head">{head}</div>
<blockquote>{body}</blockquote>
</div>"""


def response_html(text):
    if not text.strip():
        return ""
    paras = "".join(f"<p>{esc(p.strip())}</p>" for p in text.split("\n\n") if p.strip())
    return f'<section class="response card"><h2>Response</h2>{paras}</section>'


def claim_books(claim):
    """Every book a claim cites or is answered from, in canonical order."""
    books = {cite_book(c) for c in claim["cited"]} | {p["book"] for p in claim["passages"]}
    return sorted(books, key=BOOK_ORDER.index)


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


def claim_card(claim, up, refs=None, searchable=False):
    """One claim as a card in a list. `refs` replaces the line of citations."""
    n = claim_number(claim["id"])
    line = refs if refs is not None else "Cites " + " · ".join(claim["cited"])
    data = f' data-n="{n}" data-search="{esc(search_text(claim))}"' if searchable else ""
    return (f'<li{data}><a class="card claim-card" href="{up}{n}/">'
            f'<span class="id">{esc(claim["id"])}</span>'
            f'<span class="text">{esc(claim["claim"])}</span>'
            f'<span class="refs">{esc(line)}</span></a></li>')


# ---------------------------------------------------------------- pages

def claim_page(i, claims, tanakh, kjv, chabad, status_note):
    claim = claims[i]
    passages = sorted(claim["passages"], key=lambda p: ROLE_ORDER[p["role"]])

    # Verses the claim itself cites, highlighted wherever they appear in a
    # wider passage on the same page.
    highlight = {}
    for p in passages:
        if p["role"] == "cited":
            chapters = {c: t["en"] for c, t in tanakh[p["book"]].items()}
            highlight.setdefault(p["book"], set()).update(verse_list(p["ref"], chapters))

    groups = []
    for role in ROLE_ORDER:
        these = [p for p in passages if p["role"] == role]
        if not these:
            continue
        hint = ('<p class="hint">Highlighted verses are the ones the claim cites.</p>'
                if role == "context" and highlight else "")
        cards = "".join(passage_html(p, tanakh, chabad,
                                     set() if role == "cited" else highlight.get(p["book"], set()))
                        for p in these)
        groups.append(f'<h3 class="group-h {role}">{esc(ROLE_GROUP[role])}</h3>{hint}{cards}')

    chips = "".join(f'<li><a class="chip" href="#cite-{k}">{esc(c)}</a></li>'
                    for k, c in enumerate(claim["cited"], 1))
    books = " · ".join(f'<a href="../books/{slug(b)}/">{esc(b)}</a>' for b in claim_books(claim))

    def nav_link(j, rel, label):
        if not 0 <= j < len(claims):
            return "<span></span>"
        return f'<a class="btn" rel="{rel}" href="../{claim_number(claims[j]["id"])}/">{label}</a>'

    prev_link = nav_link(i - 1, "prev", f'&larr; {esc(claims[i - 1]["id"])}' if i > 0 else "")
    next_link = nav_link(i + 1, "next", f'{esc(claims[i + 1]["id"])} &rarr;' if i + 1 < len(claims) else "")

    body = f"""<article class="claim">
<header class="card claim-head">
<p class="claim-id">{esc(claim['id'])}</p>
<h1>{esc(claim['claim'])}</h1>
<ul class="chips" aria-label="Verses the claim cites">{chips}</ul>
<p class="books-line">More claims from: {books}</p>
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
<nav class="prevnext">{prev_link}<a class="btn" href="../">All claims</a>{next_link}</nav>
</article>"""
    return page(f"{claim['id']}: {claim['claim']} · Emet", body, depth=1,
                description=claim["claim"])


def index_page(doc):
    claims = doc["claims"]
    grid = "\n".join(
        f'<a href="{claim_number(c["id"])}/" title="{esc(c["claim"])}">{claim_number(c["id"])}</a>'
        for c in claims)
    cards = "\n".join(claim_card(c, "", searchable=True) for c in claims)
    body = f"""<section class="hero">
<h1>Emet <span lang="he">אמת</span></h1>
<p class="sub">{esc(doc['subtitle'])}</p>
<form class="big-search" id="search" role="search" action="./" method="get">
  <label for="q">Find a claim by number, keyword or verse</label>
  <div class="search-row">
    <input id="q" type="search" name="q" placeholder="e.g. 42, virgin, Isaiah 53" autocomplete="off" spellcheck="false">
    <button type="submit">Search</button>
  </div>
</form>
<p id="search-status" class="search-status" role="status" aria-live="polite"></p>
<p class="quick">Or browse <a href="books/">by book</a> or <a href="verses/">by TaNaKh passage</a>.</p>
</section>
<section id="numbers" class="card numbers">
<h2>Jump to a claim number</h2>
<nav class="grid" aria-label="Claims by number">
{grid}
</nav>
</section>
<section>
<h2 id="list-heading">All {len(claims)} claims</h2>
<ol id="claims" class="claim-cards">
{cards}
</ol>
</section>"""
    return page("Emet: evangelical claims and the TaNaKh passages listed in answer",
                body, depth=0, description=doc["subtitle"], header_search=False, script=True)


def book_index(claims):
    """{book: {"cite": [claim, ...], "answer": [(claim, [refs])...]}} in claim order."""
    index = {}
    for c in claims:
        for b in {cite_book(x) for x in c["cited"]}:
            index.setdefault(b, {"cite": [], "answer": []})["cite"].append(c)
        refs = {}
        for p in sorted(c["passages"], key=lambda p: ROLE_ORDER[p["role"]]):
            refs.setdefault(p["book"], [])
            if p["ref"] not in refs[p["book"]]:
                refs[p["book"]].append(p["ref"])
        for b, rs in refs.items():
            index.setdefault(b, {"cite": [], "answer": []})["answer"].append((c, rs))
    return index


def books_page(index):
    sections = []
    for group, books in BOOK_GROUPS:
        tiles = []
        for b in books:
            if b not in index:
                continue
            n = len({c["id"] for c in index[b]["cite"]} | {c["id"] for c, _ in index[b]["answer"]})
            tiles.append(f'<li><a class="card" href="{slug(b)}/"><span class="name">{esc(b)}</span>'
                         f'<span class="n">{n} claim{"s" if n != 1 else ""}</span></a></li>')
        if tiles:
            sections.append(f'<section><h2>{esc(group)}</h2><ul class="book-tiles">{"".join(tiles)}</ul></section>')
    body = f"""<h1>Browse by book</h1>
<p class="lede">Pick a book to see every claim that cites it, and every claim answered
from it.</p>
{''.join(sections)}"""
    return page("Books · Emet", body, depth=1,
                description="Find claims by the book of the Bible they cite or are answered from.")


def book_page(book, entry, is_tanakh):
    up = "../../"
    cite, answer = entry["cite"], entry["answer"]
    parts = []
    jumps = []
    if cite:
        jumps.append(f'<a class="chip" href="#cite">Claims that cite {esc(book)} ({len(cite)})</a>')
        parts.append(f"""<section id="cite">
<h2>Claims that cite {esc(book)}</h2>
<p class="hint">These claims quote {esc(book)} as support.</p>
<ol class="claim-cards">{''.join(claim_card(c, up) for c in cite)}</ol>
</section>""")
    if answer:
        jumps.append(f'<a class="chip" href="#answer">Answered from {esc(book)} ({len(answer)})</a>')
        cards = "".join(claim_card(c, up, refs=f"{book} " + " · ".join(rs)) for c, rs in answer)
        parts.append(f"""<section id="answer">
<h2>Claims answered from {esc(book)}</h2>
<p class="hint">Passages from {esc(book)} are listed in answer to these claims.</p>
<ol class="claim-cards">{cards}</ol>
</section>""")
    if is_tanakh and answer:
        jumps.append(f'<a class="chip" href="{up}verses/#{slug(book)}">{esc(book)} passages index</a>')
    body = f"""<p class="crumbs"><a href="../">All books</a></p>
<h1>{esc(book)}</h1>
<p class="chips jumps">{''.join(jumps)}</p>
{''.join(parts)}"""
    return page(f"{book} · Emet", body, depth=2,
                description=f"Claims that cite {book} or are answered from it.")


def verses_page(doc):
    by_book = {}
    for c in doc["claims"]:
        for p in c["passages"]:
            by_book.setdefault(p["book"], {}).setdefault(p["ref"], []).append(c["id"])

    def key(ref):
        m = REF_RE.match(ref)
        return (int(m["c1"]), int(m["v1"]), int(m["c2"] or m["c1"]), int(m["v2"] or m["v1"]))

    books = [b for b in BOOK_ORDER if b in by_book]
    sections = []
    for book in books:
        rows = []
        for ref in sorted(by_book[book], key=key):
            ids = sorted(set(by_book[book][ref]))
            links = " ".join(f'<a class="chip" href="../{claim_number(i)}/">{esc(i)}</a>' for i in ids)
            rows.append(f"<tr><th>{esc(ref)}</th><td>{links}</td></tr>")
        sections.append(f'<section id="{esc(slug(book))}" class="card verse-book">'
                        f'<h2>{esc(book)} <a class="more" href="../books/{slug(book)}/">all {esc(book)} claims</a></h2>'
                        f'<table class="verse-index">{"".join(rows)}</table></section>')
    toc = "".join(f'<a class="chip" href="#{esc(slug(b))}">{esc(b)}</a>' for b in books)
    body = f"""<h1>TaNaKh passages</h1>
<p class="lede">Every passage on this site, in Chabad.org book order and numbering, with the
claims it is listed under.</p>
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
<li>Use the search box: a number takes you straight to that claim; words or a verse
(for example <em>virgin</em> or <em>Isaiah 53</em>) list every claim that mentions them.</li>
<li>Or browse <a href="../books/">by book</a> or <a href="../verses/">by TaNaKh passage</a>.</li>
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
<p>This site is plain HTML, one stylesheet, and one short script that filters the list of
claims as you type in the search box. It sets no cookies, collects nothing, sends nothing,
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
    (re.compile(r"<\s*(iframe|object|embed|base|frame|applet)\b", re.I), "an iframe/object/embed/base tag"),
    (re.compile(r"\son[a-z]+\s*=", re.I), "an inline event handler (onclick= etc.)"),
    (re.compile(r"javascript:", re.I), "a javascript: link"),
    (re.compile(r"<(link|img|source|video|audio|script)\b[^>]*\b(href|src)=\"(https?:)?//", re.I),
     "a resource loaded from another website"),
    (re.compile(r"<\s*form\b(?![^>]*\baction=\"(\.\./)*(\./)?\")", re.I),
     "a form that submits anywhere but this site's front page"),
    (re.compile(r"<\s*input\b(?![^>]*\btype=\"search\")", re.I), "an input other than a search box"),
    (re.compile(r"@import|url\(\s*['\"]?(https?:)?//", re.I), "a stylesheet loading from another website"),
]

# The only script tag allowed, and only on the front page.
ALLOWED_SCRIPT_TAG = '<script src="search.js" defer></script>'

# Things the script may not do. It needs none of them to filter a list.
FORBIDDEN_JS = [
    "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "Function(",
    "setTimeout(", "setInterval(", "fetch(", "XMLHttpRequest", "WebSocket", "EventSource",
    "sendBeacon", "import(", "importScripts", "Worker(", "cookie", "localStorage",
    "sessionStorage", "indexedDB", "postMessage", "window.open", "http:", "https:",
]


def check_output():
    problems = []
    for path in sorted(OUT.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(OUT).as_posix()
        text = path.read_text("utf-8")
        if path.suffix == ".js":
            if rel != "search.js" or text != (ROOT / "site" / "search.js").read_text("utf-8"):
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
            scripts = re.findall(r"<\s*script\b[^>]*>(?:.*?</\s*script\s*>)?", text, re.I | re.S)
            allowed = [ALLOWED_SCRIPT_TAG] if rel == "index.html" else []
            if scripts != allowed:
                problems.append(f"docs/{rel}: has script tags {scripts!r}, allowed only {allowed!r}")
        for pattern, what in FORBIDDEN_HTML:
            if pattern.search(text):
                problems.append(f"docs/{rel}: contains {what}")
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
    shutil.copy(ROOT / "site" / "search.js", OUT / "search.js")

    claims = doc["claims"]
    for i, claim in enumerate(claims):
        n = claim_number(claim["id"])
        write(f"{n}/index.html", claim_page(i, claims, tanakh, kjv, chabad, doc["status_note"]))
        # So that /042, /C-042 and /c-042 also reach /42 (GitHub Pages is case-sensitive).
        for alias in {f"{n:03d}", claim["id"], claim["id"].lower()} - {str(n)}:
            write(f"{alias}/index.html", alias_page(n))

    write("index.html", index_page(doc))
    index = book_index(claims)
    write("books/index.html", books_page(index))
    tanakh_books = {b for _, books in BOOK_GROUPS[:3] for b in books}
    for book, entry in index.items():
        write(f"books/{slug(book)}/index.html", book_page(book, entry, book in tanakh_books))
    write("verses/index.html", verses_page(doc))
    passages = [p for c in claims for p in c["passages"]]
    counts = {"passages": len(passages),
              "sourced": sum(1 for p in passages if p.get("source")),
              "verified": sum(1 for p in passages if p.get("verified"))}
    write("about/index.html", about_page(doc, counts))
    write("404.html", not_found_page())

    check_output()
    print(f"Built {len(claims)} claim pages and {len(index)} book pages into "
          f"{OUT.relative_to(ROOT)}/ - safety check passed.")


if __name__ == "__main__":
    main()
