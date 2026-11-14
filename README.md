# Emet

A small static website to follow a debate as it happens. Each evangelical
claim has a short number. When the number is called out, the audience opens
it, for example `https://<your-site>/42`, and sees:

- the claim, in one sentence;
- the verses it cites, quoted from the King James Version;
- the TaNaKh passages listed in answer, in Hebrew and in English (JPS 1917),
  with the verses the claim cites highlighted in their context.

The site is self-contained: every text it shows is stored in it, and it links
to no other website, so nothing on it can break because another site changed.
The build refuses any link to another site.

There are 188 claims (C-001 to C-188) and 586 TaNaKh passages.

**In a debate:** type the number after the address (`/42`, `/042` and `/c-042`
all work), or type it in any search box and press Enter.

**For research:** the front page is a workbench. Search by words or verse
(`virgin`, `Isaiah 53`; matches are highlighted), pick a book from the list,
and choose whether the claim *cites* that book or is *answered* from it. On a
wide screen the claim you pick opens in a reader beside the list, and the up
and down arrow keys step through the results. The whole view is kept in the
address, so it can be bookmarked or shared, for example
`/?book=isaiah&in=answers`. There is also an index of every TaNaKh passage at
`/verses/`.

> **Status: unverified draft.** The passage lists were compiled from general
> knowledge of the passages usually cited on each side. They have not yet been
> checked against Rabbi Singer's teaching or any other rabbinic source, and
> nothing on the site is attributed to anyone. See "Verifying a passage" below.

For the security review, see [SECURITY.md](SECURITY.md).

## How it is put together

```
data/claims.json            the content: every claim and its passages (edit this)
data/texts/tanakh.json      Hebrew + JPS 1917 English text (downloaded, public domain)
data/texts/kjv.json         King James Version text (downloaded, public domain)
site/style.css              the one stylesheet
site/workbench.js           the one script: search, filters and reader on the front page
build.py                    turns the data into the website (standard-library Python)
tools/fetch_texts.py        downloads verse text for newly added chapters
docs/                       the generated website; GitHub Pages serves this folder
```

The finished site is static: plain HTML and CSS plus one short, commented
script for the front page's search, filters and reader pane. It has no cookies, no tracking, and loads nothing from any
other website. Everything else works without the script.

## Putting it on GitHub Pages (free)

1. Create a GitHub repository and push this folder to it.
2. In the repository, go to **Settings → Pages**.
3. Under **Build and deployment**, choose **Deploy from a branch**, branch
   `main`, folder `/docs`, and save.
4. After a minute the site is live at
   `https://<github-username>.github.io/<repository-name>/`.
   Claim 42 is then `https://<github-username>.github.io/<repository-name>/42`.
5. Tick **Enforce HTTPS** on the same page.

For an easier address to say aloud in a debate, GitHub Pages can use a custom
domain (Settings → Pages → Custom domain), for example `emet.example.org/42`.

## Changing the content

Everything is in `data/claims.json`. After any change, rebuild and commit both
the data and `docs/`:

```bash
python3 build.py
```

The build stops with a clear message if the data has a mistake (a reference it
cannot read, a passage whose text has not been downloaded yet) or if any page
fails the safety check.

### A claim

```json
{
  "id": "C-001",
  "claim": "Isaiah 7:14 foretells that the Messiah would be born of a virgin, fulfilled in the birth of Jesus.",
  "cited": ["Matthew 1:22-23", "Isaiah 7:14"],
  "response": "",
  "passages": [ ... ]
}
```

- `id`: `C-` and three digits. The page address is the number without zeros: `/1`.
  `/001` and `/c-001` (lower-case c) also work. `/C-001` with a capital C does
  not: GitHub Pages addresses are case-sensitive. The search box accepts either.
- `cited`: the verses the evangelical cites, in **King James** numbering.
- `flags`: optional. The source check, shown above the passages in fixed
  wording (no free text can be added). Each flag is one of:

  | `kind` | Fields | Shown as |
  |---|---|---|
  | `not-in-tanakh` | `nt` | The words *nt* quotes are not found in the TaNaKh. |
  | `greek-wording` | `nt`, `tanakh` | *nt* follows the ancient Greek translation of *tanakh*, not the Hebrew. |
  | `words-differ` | `nt`, `tanakh` | The words of *nt* differ from the Hebrew text of *tanakh*. |
  | `wrong-book` | `nt`, `named`, `tanakh` | *nt* names *named* as the source, but the words are found in *tanakh*. |

  `nt` is a list of the claim's own citations; `tanakh` must be one of the
  claim's passages. The build checks both. A claim that cites no TaNaKh verse
  at all is labelled "No TaNaKh verse cited" automatically.
- `response`: optional. Leave it empty, or write the answer in plain text;
  separate paragraphs with a blank line. When filled in, it is shown under the
  claim with the heading "Response". Plain text only: any HTML is shown as text.

### A passage

```json
{ "book": "Micah", "ref": "5:1", "role": "cited", "kjv": "5:2",
  "verified": false, "source": null }
```

- `book`: Hebrew-Bible book name, e.g. `Isaiah`, `Psalms`, `Samuel I`, `Kings II`.
- `ref`: chapter:verse in the **Hebrew numbering of the texts quoted** (JPS 1917 and the
  Hebrew text, as on Sefaria): `7:14`, `7:10-16`, `52:13-53:12`. This is the same as
  Chabad.org's numbering except in a few chapters (Jeremiah 31 and Joshua 21 differ).
- `role`: one of
  - `cited`: the verse the claim cites (shown first, always open);
  - `context`: the verses around it (folded, with the cited verse highlighted);
  - `reply`: other TaNaKh passages on the same question.
- `kjv`: optional. The King James numbering when it differs.
- `verified` / `source`: see below.

Passages from a chapter not yet on the site need their text downloaded once:

```bash
python3 tools/fetch_texts.py
```

### Verifying a passage

Every passage starts as `"verified": false, "source": null`. When someone has
checked a passage against a source (for example a specific Outreach Judaism
lecture, book page, or article), set:

```json
"verified": true, "source": "Let's Get Biblical, vol. 1, ch. 3"
```

The passage then shows a ✓ and the source, and the count on the About page
goes up.

## The book (PDF)

`book/Emet.pdf` is the same content laid out as a book for reading and
printing: US Letter pages, one claim per page (continuing as needed), the
Hebrew and the JPS 1917 English side by side verse by verse, a contents list
with page numbers, an index of passages by book, and PDF bookmarks for every
claim. Rebuild it after changing the data:

```bash
python3 tools/build_book.py
```

Then run `python3 build.py` so the site publishes the new copy: the
website offers it as "Book (PDF)" in the top menu.

It needs Google Chrome (or Chromium) installed, which it runs without a
window to turn `book/emet-book.html` into the PDF; nothing is downloaded. The
layout is in `site/book.css` (page size, fonts, margins). The book uses the
Mac's Iowan Old Style and New Peninim MT fonts, with standard fallbacks
elsewhere.

## Research notes

`tools/review_list.py` writes a verification checklist to `research/`. That
folder holds private working notes and is not kept in the repository (see
`.gitignore`). The website deliberately holds only verse citations against
verse citations: no articles, sources of commentary, or links.

## Previewing on your own computer

```bash
python3 -m http.server --directory docs 8000
```

Then open http://localhost:8000/ in a browser. You can also just double-click
`docs/index.html`: every link points at a file, so the site works from disk
too (the short `/42` addresses need a web server, as on GitHub Pages).

## Where the data came from

The claims and passage lists were transcribed from the document "Emet:
Evangelical claims, the verses they cite, and the TaNaKh passages listed in
answer" (13 November 2026), and checked against that document's own index of
passages. Verse texts were downloaded by `tools/fetch_texts.py` from Sefaria
(JPS 1917 English and Hebrew, both public domain) and bible-api.com (King James
Version, public domain).
