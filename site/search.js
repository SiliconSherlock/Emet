/*
 * Emet search box. This is the site's only script, and the front page is the
 * only page that loads it.
 *
 * As you type, it shows or hides the claims already listed on the front page.
 * That is all it does:
 *
 *  - It reads only text that is already on the page. build.py gives each claim
 *    in the list a data-search attribute (the claim, its verse references and
 *    book names) and a data-n attribute (the claim number).
 *  - It hides the claims that do not match, shows one line of status text,
 *    and keeps the search in the address bar (?q=...) so a search can be
 *    bookmarked or shared.
 *  - If the search is a claim number, such as 42 or C-042, pressing Enter
 *    opens that claim's page.
 *  - It loads nothing, sends nothing and stores nothing: no network requests,
 *    no cookies, no local storage. The page's Content Security Policy
 *    (default-src 'none') would block network requests anyway.
 *  - It never turns text into HTML, so whatever is typed stays plain text.
 *
 * The search boxes on other pages are plain HTML forms that open the front
 * page with ?q=... in its address. This script then picks that up.
 */
"use strict";

(function () {
  const form = document.getElementById("search");
  const input = document.getElementById("q");
  const status = document.getElementById("search-status");
  const list = document.getElementById("claims");
  const heading = document.getElementById("list-heading");
  const numbers = document.getElementById("numbers");
  if (!form || !input || !status || !list || !heading) {
    return;
  }

  const items = Array.from(list.children);
  const total = items.length;
  const claimNumbers = new Set(items.map((item) => item.dataset.n));

  // "42", "042", "C-042", "c42" -> "42", if there is a claim 42. Otherwise null.
  function claimNumber(query) {
    const match = /^\s*c?\s*-?\s*0*(\d+)\s*$/i.exec(query);
    if (match && claimNumbers.has(match[1])) {
      return match[1];
    }
    return null;
  }

  // "Isaiah 53, virgin" -> ["isaiah", "53", "virgin"]
  function searchWords(query) {
    return query
      .toLowerCase()
      .replace(/[“”‘’"',;()]/g, " ")
      .split(/\s+/)
      .filter((word) => word !== "");
  }

  function showStatus(text, number) {
    status.textContent = text;
    if (number) {
      const link = document.createElement("a");
      link.className = "go";
      link.href = number + "/";
      link.textContent = "Open claim " + number + " →";
      status.append(" ", link);
    }
  }

  // Keep the search in the address bar, so it can be shared or bookmarked.
  function rememberInAddress(query) {
    const url = new URL(window.location.href);
    if (query.trim() === "") {
      url.searchParams.delete("q");
    } else {
      url.searchParams.set("q", query);
    }
    window.history.replaceState(null, "", url);
  }

  function filter() {
    const query = input.value;
    const words = searchWords(query);
    const number = claimNumber(query);
    const searching = words.length > 0;

    // A claim is shown if it contains every word typed, in any order.
    let shown = 0;
    for (const item of items) {
      const text = item.dataset.search;
      const matches = item.dataset.n === number || words.every((word) => text.includes(word));
      item.hidden = !matches;
      if (matches) {
        shown += 1;
      }
    }

    if (numbers) {
      numbers.hidden = searching;
    }
    if (!searching) {
      heading.textContent = "All " + total + " claims";
      showStatus("", null);
    } else if (shown === 0) {
      heading.textContent = "No matching claims";
      showStatus("No claims match “" + query.trim() + "”. Try fewer words, or browse by book.", null);
    } else {
      heading.textContent = shown === 1 ? "1 matching claim" : shown + " matching claims";
      showStatus(shown + " of " + total + " claims match.", number);
    }
    rememberInAddress(query);
  }

  // Pressing Enter: a claim number opens that claim. Anything else has
  // already been filtered as it was typed, so the page stays where it is.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const number = claimNumber(input.value);
    if (number) {
      window.location.href = number + "/";
    }
  });

  input.addEventListener("input", filter);

  // Arriving from a search box on another page (?q=...).
  const arriving = new URL(window.location.href).searchParams.get("q") || "";
  if (arriving !== "") {
    const number = claimNumber(arriving);
    if (number) {
      window.location.replace(number + "/");
      return;
    }
    input.value = arriving;
    filter();
  }
})();
