# Security review notes

This is written for whoever reviews the site before it goes live. In short:
the published website is static HTML and one CSS file. It contains **no
JavaScript at all**, no forms, no cookies, no analytics, no third-party
resources, and nothing that runs on a server.

## What gets published

Only the `docs/` folder is published (GitHub Pages, "deploy from branch",
folder `/docs`). It contains:

| Files | What they are |
|---|---|
| `docs/index.html` | list of claims |
| `docs/<n>/index.html` | one page per claim (`/1` … `/188`) |
| `docs/<0nn>/`, `docs/C-0nn/`, `docs/c-0nn/` | one-line forwarding pages (`<meta http-equiv="refresh">`) so `/042` and `/C-042` reach `/42` |
| `docs/verses/index.html` | index by verse |
| `docs/about/index.html` | about page |
| `docs/404.html` | not-found page |
| `docs/style.css` | the only stylesheet |
| `docs/.nojekyll` | empty; tells GitHub Pages not to process the files |

There are no images, fonts, scripts, or other file types.

## Protections in every page

Every HTML page carries this Content Security Policy:

```
default-src 'none'; style-src 'self'; img-src 'self'; base-uri 'none'; form-action 'none'
```

With `default-src 'none'` and no `script-src`, the browser refuses to run any
script, inline or external, even if one were somehow added. The page may load
only its own stylesheet from its own site. Every page also sets
`<meta name="referrer" content="no-referrer">`, so following a link to
Chabad.org or Sefaria does not tell those sites which claim the reader was on.

Outbound links go only to `www.chabad.org` and `www.sefaria.org`. They are
ordinary links: nothing from those sites is loaded or embedded.

## How the pages are made

`build.py` (about 500 lines, Python standard library only, no network access)
reads the JSON files in `data/` and writes `docs/`.

- All text from the data files goes through `html.escape()` before it is
  written. A claim or response containing `<script>` would appear on the page
  as the literal text `<script>`.
- After writing, `check_output()` scans every published file and makes the
  build fail if it finds a `<script>` tag, an inline event handler
  (`onclick=` etc.), a `javascript:` URL, an `iframe`/`object`/`embed`/`form`/
  `input`/`base` tag, a stylesheet or media file loaded from another site, a
  page without the Content Security Policy, or any file type other than HTML
  and CSS.

`tools/fetch_texts.py` is a separate helper, run by hand, that downloads
public-domain verse text from `www.sefaria.org` and `bible-api.com` into
`data/texts/`. It is not part of the website and the website never calls
those services. It sends no personal data, only Bible references.

## Checking it yourself

From the repository root:

```bash
python3 build.py
```

rebuilds the site and runs the safety check.

These should all print nothing:

```bash
grep -ril "<script" docs/
```

```bash
grep -rilE " on[a-z]+=" docs/
```

```bash
grep -rhoE '(src|href)="https?://[^"]*' docs/ | grep -vE 'href="https://www\.(chabad|sefaria)\.org/' | sort -u
```

```bash
find docs -type f ! -name '*.html' ! -name '*.css' ! -name '.nojekyll'
```

This should print the same number as the count of HTML files (every page has the policy):

```bash
grep -rl "Content-Security-Policy" docs/ | wc -l
```

```bash
find docs -name '*.html' | wc -l
```

## Hosting settings

On GitHub: **Settings → Pages → Enforce HTTPS** should be ticked. If the
repository has more than one maintainer, consider protecting the `main` branch
so changes need a review.
