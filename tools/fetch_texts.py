#!/usr/bin/env python3
"""Download the public-domain verse texts the site quotes.

You only need to run this when you add a passage from a chapter that is not
yet in data/texts/. The site itself never contacts these services: the text is
saved into data/texts/*.json and committed with the rest of the data.

Sources (all public domain):
  - English TaNaKh: "The Holy Scriptures: A New Translation (JPS 1917)", via Sefaria
  - Hebrew TaNaKh:  "Tanach with Nikkud", via Sefaria
  - King James Version (for the verses an evangelical cites), via bible-api.com

Usage:  python3 tools/fetch_texts.py
Uses only the Python standard library. Already-downloaded chapters are skipped.
"""

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLAIMS = ROOT / "data" / "claims.json"
OUT_DIR = ROOT / "data" / "texts"
TANAKH_OUT = OUT_DIR / "tanakh.json"
KJV_OUT = OUT_DIR / "kjv.json"

USER_AGENT = "emet-static-site-text-fetch/1.0"

JPS_1917 = "The Holy Scriptures: A New Translation (JPS 1917)"
HEBREW = "Tanach with Nikkud"

# Book names as used in claims.json -> Sefaria names.
SEFARIA_BOOK = {
    "Samuel I": "I Samuel", "Samuel II": "II Samuel",
    "Kings I": "I Kings", "Kings II": "II Kings",
    "Chronicles I": "I Chronicles", "Chronicles II": "II Chronicles",
}

# Book names as cited (KJV style) -> USFM codes used by bible-api.com.
USFM = {
    "Genesis": "GEN", "Exodus": "EXO", "Leviticus": "LEV", "Numbers": "NUM",
    "Deuteronomy": "DEU", "Joshua": "JOS", "Judges": "JDG", "Ruth": "RUT",
    "1 Samuel": "1SA", "2 Samuel": "2SA", "1 Kings": "1KI", "2 Kings": "2KI",
    "1 Chronicles": "1CH", "2 Chronicles": "2CH", "Ezra": "EZR",
    "Nehemiah": "NEH", "Esther": "EST", "Job": "JOB", "Psalms": "PSA",
    "Proverbs": "PRO", "Ecclesiastes": "ECC", "Song of Solomon": "SNG",
    "Isaiah": "ISA", "Jeremiah": "JER", "Lamentations": "LAM",
    "Ezekiel": "EZK", "Daniel": "DAN", "Hosea": "HOS", "Joel": "JOL",
    "Amos": "AMO", "Obadiah": "OBA", "Jonah": "JON", "Micah": "MIC",
    "Nahum": "NAM", "Habakkuk": "HAB", "Zephaniah": "ZEP", "Haggai": "HAG",
    "Zechariah": "ZEC", "Malachi": "MAL",
    "Matthew": "MAT", "Mark": "MRK", "Luke": "LUK", "John": "JHN",
    "Acts": "ACT", "Romans": "ROM", "1 Corinthians": "1CO",
    "2 Corinthians": "2CO", "Galatians": "GAL", "Ephesians": "EPH",
    "Philippians": "PHP", "Colossians": "COL", "1 Thessalonians": "1TH",
    "2 Thessalonians": "2TH", "1 Timothy": "1TI", "2 Timothy": "2TI",
    "Titus": "TIT", "Philemon": "PHM", "Hebrews": "HEB", "James": "JAS",
    "1 Peter": "1PE", "2 Peter": "2PE", "1 John": "1JN", "2 John": "2JN",
    "3 John": "3JN", "Jude": "JUD", "Revelation": "REV",
}

# Sefaria's copy of JPS 1917 keeps a few footnote letters glued to the next
# word ("athey" for "they"). Each fix names the verse and the exact text, and
# is applied every time this script runs.
JPS_FIXES = [
    ("Genesis", 4, 1, "have agotten", "have gotten"),
    ("Exodus", 23, 31, "unto athe River", "unto the River"),
    ("Psalms", 132, 6, "field of athe wood", "field of the wood"),
    ("Zechariah", 12, 10, "because athey have", "because they have"),
    ("Judges", 6, 24, "called it a‘Adonai-shalom’", "called it ‘Adonai-shalom’"),
]

REF_RE = re.compile(r"^(?P<book>.+) (?P<c1>\d+):(?P<v1>\d+)(?:-(?:(?P<c2>\d+):)?(?P<v2>\d+))?$")


def chapters_in(ref_chapter_start, ref_chapter_end):
    return range(int(ref_chapter_start), int(ref_chapter_end) + 1)


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def clean(text):
    """Turn Sefaria's lightly marked-up verse text into plain text."""
    text = re.sub(r'<sup class="footnote-marker">.*?</sup>', "", text)
    text = re.sub(r'<i class="footnote">.*?</i>', "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\{[פס]\}", "", text)  # open/closed paragraph markers
    return re.sub(r"\s+", " ", text).strip()


def load(path):
    return json.loads(path.read_text("utf-8")) if path.exists() else {}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", "utf-8")


def needed():
    doc = json.loads(CLAIMS.read_text("utf-8"))
    tanakh, kjv = set(), set()
    for claim in doc["claims"]:
        for p in claim["passages"]:
            m = REF_RE.match(f"{p['book']} {p['ref']}")
            if not m:
                sys.exit(f"Cannot read passage {p['book']} {p['ref']!r} in {claim['id']}")
            for ch in chapters_in(m["c1"], m["c2"] or m["c1"]):
                tanakh.add((p["book"], ch))
        for cite in claim["cited"]:
            m = REF_RE.match(cite)
            if not m:
                sys.exit(f"Cannot read citation {cite!r} in {claim['id']}")
            for ch in chapters_in(m["c1"], m["c2"] or m["c1"]):
                kjv.add((m["book"], ch))
    return sorted(tanakh), sorted(kjv)


def main():
    tanakh_need, kjv_need = needed()
    tanakh = load(TANAKH_OUT)
    kjv = load(KJV_OUT)

    for book, ch in tanakh_need:
        if str(ch) in tanakh.get(book, {}):
            continue
        sef = SEFARIA_BOOK.get(book, book)
        url = ("https://www.sefaria.org/api/v3/texts/" + urllib.parse.quote(f"{sef}.{ch}")
               + "?version=" + urllib.parse.quote(f"english|{JPS_1917}")
               + "&version=" + urllib.parse.quote(f"hebrew|{HEBREW}"))
        data = get_json(url)
        by_lang = {v["language"]: v["text"] for v in data.get("versions", [])}
        if "en" not in by_lang or "he" not in by_lang:
            sys.exit(f"Sefaria did not return both texts for {book} {ch}: {data.get('warnings')}")
        tanakh.setdefault(book, {})[str(ch)] = {
            "en": [clean(t) for t in by_lang["en"]],
            "he": [clean(t) for t in by_lang["he"]],
        }
        print(f"TaNaKh {book} {ch}: {len(by_lang['en'])} verses")
        save(TANAKH_OUT, tanakh)
        time.sleep(0.5)

    for book, ch in kjv_need:
        if str(ch) in kjv.get(book, {}):
            continue
        data = get_json(f"https://bible-api.com/data/kjv/{USFM[book]}/{ch}")
        verses = data["verses"]
        kjv.setdefault(book, {})[str(ch)] = [re.sub(r"\s+", " ", v["text"]).strip() for v in verses]
        print(f"KJV {book} {ch}: {len(verses)} verses")
        save(KJV_OUT, kjv)
        time.sleep(2.5)  # bible-api.com asks clients to stay under ~15 requests / 30 s

    for book, ch, verse, wrong, right in JPS_FIXES:
        verses = tanakh.get(book, {}).get(str(ch), {}).get("en")
        if verses and wrong in verses[verse - 1]:
            verses[verse - 1] = verses[verse - 1].replace(wrong, right)
            print(f"Fixed {book} {ch}:{verse}: {wrong!r} -> {right!r}")
    save(TANAKH_OUT, tanakh)

    print("Done.")


if __name__ == "__main__":
    main()
