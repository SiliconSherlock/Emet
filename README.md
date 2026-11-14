# Emet

A small static website to follow a debate as it happens. Each evangelical
claim has a short number. When the number is called out, the audience opens
it, for example `https://<your-site>/42`, and sees:

- the claim, in one sentence;
- the verses it cites, quoted from the King James Version;
- the TaNaKh passages listed in answer, in Hebrew and in English (JPS 1917),
  with the verses the claim cites highlighted in their context, and links to
  each chapter on Chabad.org (with Rashi) and Sefaria.

There are 188 claims (C-001 to C-188) and 586 TaNaKh passages. You can also
browse by verse at `/verses/`.

> **Status: unverified draft.** The passage lists were compiled from general
> knowledge of the passages usually cited on each side. They have not yet been
> checked against Rabbi Singer's teaching or any other rabbinic source, and
> nothing on the site is attributed to anyone. See "Verifying a passage" below.

For the security review, see [SECURITY.md](SECURITY.md).

## How it is put together

```
data/claims.json            the content: every claim and its passages (edit this)
data/chabad_chapters.json   Chabad.org chapter IDs, used to build links
data/texts/tanakh.json      Hebrew + JPS 1917 English text (downloaded, public domain)
data/texts/kjv.json         King James Version text (downloaded, public domain)
site/style.css              the one stylesheet
build.py                    turns the data into the website (standard-library Python)
tools/fetch_texts.py        downloads verse text for newly added chapters
docs/                       the generated website; GitHub Pages serves this folder
```

The finished site is plain HTML and CSS. It has no JavaScript, no cookies, no
forms, no tracking, and loads nothing from any other website.

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
  `/001` and `/C-001` also work.
- `cited`: the verses the evangelical cites, in **King James** numbering.
- `response`: optional. Leave it empty, or write the answer in plain text;
  separate paragraphs with a blank line. When filled in, it is shown under the
  claim with the heading "Response". Plain text only: any HTML is shown as text.

### A passage

```json
{ "book": "Micah", "ref": "5:1", "role": "cited", "kjv": "5:2",
  "verified": false, "source": null }
```

- `book`: Chabad.org book name, e.g. `Isaiah`, `Psalms`, `Samuel I`, `Kings II`.
- `ref`: chapter:verse in **Chabad.org (Hebrew)** numbering: `7:14`, `7:10-16`, `52:13-53:12`.
- `role`: one of
  - `cited`: the verse the claim cites (shown first, always open);
  - `context`: the verses around it (folded, with the cited verse highlighted);
  - `reply`: also commonly cited in Orthodox responses.
- `kjv`: optional. The King James numbering when it differs.
- `note`: optional. A short note shown in italics.
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

## Previewing on your own computer

```bash
python3 -m http.server --directory docs 8000
```

Then open http://localhost:8000/ in a browser.

## Where the data came from

The claims and passage lists were transcribed from the document "Emet:
Evangelical claims, the verses they cite, and the TaNaKh passages listed in
answer" (13 November 2026), and checked against that document's own index of
passages. Verse texts were downloaded by `tools/fetch_texts.py` from Sefaria
(JPS 1917 English and Hebrew, both public domain) and bible-api.com (King James
Version, public domain).
