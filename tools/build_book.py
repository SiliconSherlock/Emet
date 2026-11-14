#!/usr/bin/env python3
"""Build the Emet book as a PDF, from the same data as the website.

    python3 tools/build_book.py

Writes  book/emet-book.html   the print layout (intermediate file)
        book/Emet.pdf         the book, rendered by Google Chrome (headless)

Uses only the Python standard library, plus a local copy of Google Chrome or
Chromium to turn the HTML into a PDF. Nothing is downloaded. The stylesheet is
site/book.css.
"""

import datetime
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import build  # noqa: E402  (the website builder: data loading, checks, helpers)
from build import esc, verse_list, claim_number, CITE_RE, ROLE_ORDER  # noqa: E402

OUT = ROOT / "book"
HTML = OUT / "emet-book.html"
PDF = OUT / "Emet.pdf"
CSS = ROOT / "site" / "book.css"

ROLE_HEADING = {
    "cited": "The verse the claim cites",
    "context": "The verse in its context",
    "reply": "Other TaNaKh passages",
}

CHROME_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
]


def anchor(claim):
    return f"c{claim_number(claim['id'])}"


# ---------------------------------------------------------------- claim pages

def kjv_quote(cite, kjv):
    m = CITE_RE.match(cite)
    chapters = kjv[m["book"]]
    verses = verse_list(m["ref"], chapters)
    multi = len({c for c, _ in verses}) > 1
    body = " ".join(f'<sup>{esc(f"{c}:{v}" if multi else v)}</sup>{esc(chapters[str(c)][v - 1])}'
                    for c, v in verses)
    return f'<div class="kjv"><p class="ref">{esc(cite)} <span class="ed">KJV</span></p><p>{body}</p></div>'


def passage(p, tanakh, highlight):
    book, ref = p["book"], p["ref"]
    chapters = tanakh[book]
    verses = verse_list(ref, {c: t["en"] for c, t in chapters.items()})
    multi = len({c for c, _ in verses}) > 1
    rows = []
    for c, v in verses:
        label = f"{c}:{v}" if multi else str(v)
        cls = ' class="hl"' if (c, v) in highlight else ""
        rows.append(f'<tr{cls}><th>{esc(label)}</th>'
                    f'<td class="en">{esc(chapters[str(c)]["en"][v - 1])}</td>'
                    f'<td class="he" lang="he" dir="rtl">{esc(chapters[str(c)]["he"][v - 1])}</td></tr>')
    kjv = f' <span class="kjvnum">KJV {esc(p["kjv"])}</span>' if p.get("kjv") else ""
    ok = ' <span class="verified">&#10003; verified</span>' if p.get("verified") else ""
    return (f'<div class="passage {p["role"]}"><p class="ref">{esc(book)} {esc(ref)}{kjv}{ok}</p>'
            f'<table class="verses">{"".join(rows)}</table></div>')


def claim_section(claim, tanakh, kjv):
    passages = sorted(claim["passages"], key=lambda p: ROLE_ORDER[p["role"]])
    highlight = {}
    for p in passages:
        if p["role"] == "cited":
            chapters = {c: t["en"] for c, t in tanakh[p["book"]].items()}
            highlight.setdefault(p["book"], set()).update(verse_list(p["ref"], chapters))

    flags = build.claim_flags(claim)
    check = ""
    if flags:
        items = "".join(
            f'<li><strong>{esc(build.FLAG_SHORT[f["kind"]])}.</strong> '
            + esc(build.FLAG_TEXT[f["kind"]].format(
                nt=build.and_list(f.get("nt", [])) if f.get("nt") else "",
                tanakh=f.get("tanakh", ""), named=f.get("named", "")))
            + "</li>" for f in flags)
        check = f'<ul class="check">{items}</ul>'

    groups = []
    for role in ROLE_ORDER:
        these = [p for p in passages if p["role"] == role]
        if these:
            groups.append(f'<p class="role {role}">{esc(ROLE_HEADING[role])}</p>' + "".join(
                passage(p, tanakh, set() if role == "cited" else highlight.get(p["book"], set()))
                for p in these))

    return f"""<section class="claim" style="page: {anchor(claim)}">
<div class="claim-head"><h2 class="claim-id" id="{anchor(claim)}">{esc(claim['id'])}</h2>
<p class="claim-text">{esc(claim['claim'])}</p></div>
{check}
<p class="side">The claim cites</p>
{''.join(kjv_quote(c, kjv) for c in claim['cited'])}
<p class="side">The TaNaKh</p>
{''.join(groups)}
</section>"""


# ---------------------------------------------------------------- front and back matter

def front_matter(doc, counts, today):
    return f"""<section class="cover">
<p class="cover-he" lang="he" dir="rtl">אמת</p>
<h1>Emet</h1>
<p class="cover-sub">{esc(doc['subtitle'])}</p>
<p class="cover-count">{counts['claims']} claims &middot; {counts['passages']} TaNaKh passages</p>
<p class="cover-edition">Draft edition &middot; {esc(today)}</p>
</section>

<section class="front">
<h2>How to read this book</h2>
<p>Each claim has its own page, numbered C-001 to C-{counts['claims']:03d}. On it are:</p>
<ol>
<li><strong>The claim</strong>, in one sentence, as it is usually made.</li>
<li><strong>A source check</strong>, where it applies, in fixed wording: the claim cites no verse of
the TaNaKh; the words it quotes are not in the TaNaKh; it follows the ancient Greek translation
rather than the Hebrew; its words differ from the Hebrew; or it names the wrong book.</li>
<li><strong>The claim cites</strong>: the verses given for the claim, quoted from the King James
Version in its own numbering.</li>
<li><strong>The TaNaKh</strong>: the passages listed in answer, verse by verse, with the English of
the Jewish Publication Society translation of 1917 beside the Hebrew. They are grouped as the
verse the claim cites, that verse in its context, and other TaNaKh passages. In a passage of
context, the verse the claim cites is shaded.</li>
</ol>
<p>The book gives citations, not commentary. Verse numbers for the TaNaKh follow the Hebrew text;
where the King James Version numbers a verse differently, its number is given beside the
reference. An index of every TaNaKh passage, by book, is at the end.</p>
<h2>Status of this edition</h2>
<p class="status">{esc(doc['status_note'])}</p>
<p>{counts['verified']} of {counts['passages']} passages have been verified. A verified passage is
marked &#10003;.</p>
<h2>Texts quoted</h2>
<ul>
<li>Hebrew: <em>Tanach with Nikkud</em>. Public domain.</li>
<li>English of the TaNaKh: <em>The Holy Scriptures According to the Masoretic Text: A New
Translation</em>, Jewish Publication Society, 1917. Public domain.</li>
<li>Verses cited by the claims: King James Version. Public domain.</li>
</ul>
</section>"""


def running_heads(claims):
    return "\n".join(f'@page {anchor(c)} {{ @top-right {{ content: "{c["id"]}"; }} }}' for c in claims)


def contents(claims, pages):
    # Page numbers come from a first rendering of the PDF; "000" holds their place.
    items = "".join(f'<li><a href="#{anchor(c)}"><span class="toc-id">{esc(c["id"])}</span>'
                    f'<span class="toc-text">{esc(c["claim"])}</span><span class="toc-fill"></span>'
                    f'<span class="toc-page">{pages.get(c["id"], "000")}</span></a></li>' for c in claims)
    return f'<section class="contents"><h2>Contents</h2><ol class="toc">{items}</ol></section>'


def passage_index(claims):
    by_book = {}
    for c in claims:
        for p in c["passages"]:
            by_book.setdefault(p["book"], {}).setdefault(p["ref"], set()).add(c["id"])

    def key(ref):
        m = build.REF_RE.match(ref)
        return (int(m["c1"]), int(m["v1"]), int(m["c2"] or m["c1"]), int(m["v2"] or m["v1"]))

    parts = []
    for book in [b for b in build.BOOK_ORDER if b in by_book]:
        rows = "".join(
            f'<li><span class="ix-ref">{esc(ref)}</span> '
            + ", ".join(f'<a href="#c{claim_number(i)}">{esc(i)}</a>' for i in sorted(by_book[book][ref]))
            + "</li>" for ref in sorted(by_book[book], key=key))
        parts.append(f'<div class="ix-book"><h3>{esc(book)}</h3><ul>{rows}</ul></div>')
    return f'<section class="index"><h2>Index of TaNaKh passages</h2><div class="ix">{"".join(parts)}</div></section>'


# ---------------------------------------------------------------- main

def bookmark_pages(pdf):
    """{bookmark title: page number} from a PDF written by Chrome.

    Chrome writes plain (uncompressed) objects: each bookmark has a /Title and a
    /Dest pointing at a page object, and the page tree lists pages in order.
    """
    raw = pdf.read_bytes()
    objects = {int(n): body for n, body in re.findall(rb"(?m)^(\d+) 0 obj\s*(.*?)\s*endobj", raw, re.S)}
    root = int(re.search(rb"/Root (\d+) 0 R", raw)[1])
    order = []

    def walk(num):
        body = objects[num]
        kids = re.search(rb"/Kids \[([^\]]*)\]", body)
        if kids and b"/Type /Pages" in body:
            for kid in re.findall(rb"(\d+) 0 R", kids[1]):
                walk(int(kid))
        else:
            order.append(num)

    walk(int(re.search(rb"/Pages (\d+) 0 R", objects[root])[1]))
    page_of = {num: i + 1 for i, num in enumerate(order)}
    out = {}
    for title, dest in re.findall(rb"/Title \(([^)]*)\)\s*/Dest \[(\d+) 0 R", raw):
        out.setdefault(title.decode("latin-1"), page_of.get(int(dest)))
    return out


def render(chrome):
    subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-first-run",
                    f"--user-data-dir={OUT / '.chrome-profile'}",
                    "--no-pdf-header-footer", "--generate-pdf-document-outline",
                    f"--print-to-pdf={PDF}", HTML.as_uri()],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    shutil.rmtree(OUT / ".chrome-profile", ignore_errors=True)


def find_chrome():
    for candidate in CHROME_CANDIDATES:
        path = shutil.which(candidate) or (candidate if Path(candidate).exists() else None)
        if path:
            return path
    sys.exit("Google Chrome or Chromium is needed to make the PDF; book/emet-book.html was written.")


def main():
    doc = build.load("claims.json")
    tanakh = build.load("texts/tanakh.json")
    kjv = build.load("texts/kjv.json")
    build.validate(doc, tanakh, kjv)
    claims = doc["claims"]
    passages = [p for c in claims for p in c["passages"]]
    counts = {"claims": len(claims), "passages": len(passages),
              "verified": sum(1 for p in passages if p.get("verified"))}
    today = datetime.date.today().strftime("%-d %B %Y")

    OUT.mkdir(exist_ok=True)
    shutil.copy(CSS, OUT / "book.css")
    chrome = find_chrome()
    pages = {}
    for _ in range(2):  # first pass finds the page numbers, second prints them
        write_html(doc, counts, today, claims, tanakh, kjv, pages)
        render(chrome)
        pages = {k: v for k, v in bookmark_pages(PDF).items() if k.startswith("C-")}
    missing = [c["id"] for c in claims if c["id"] not in pages]
    if missing:
        sys.exit(f"Could not find the page of {missing[:5]} in the PDF outline.")
    print(f"Wrote {PDF.relative_to(ROOT)} ({PDF.stat().st_size // 1024} KB): "
          f"{counts['claims']} claims, {counts['passages']} passages, {len(order_pages(PDF))} pages.")


def order_pages(pdf):
    return re.findall(rb"/Type /Page\b", pdf.read_bytes())


def write_html(doc, counts, today, claims, tanakh, kjv, pages):
    HTML.write_text(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Emet: {esc(doc['subtitle'])}</title>
<link rel="stylesheet" href="book.css">
<style>
/* Each claim has a named page style, so its number runs at the top of every page it fills. */
{running_heads(claims)}
</style>
</head>
<body>
{front_matter(doc, counts, today)}
{contents(claims, pages)}
{''.join(claim_section(c, tanakh, kjv) for c in claims)}
{passage_index(claims)}
</body>
</html>
""", "utf-8")


if __name__ == "__main__":
    main()
