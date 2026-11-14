/*
 * Emet workbench. This is the site's only script, and the front page is the
 * only page that loads it. Everything on the site still works without it:
 * the list of claims is plain links, and each claim has its own page.
 *
 * What it does, all within the front page:
 *
 *  - Search and filter. As you type, or pick a book, it shows or hides the
 *    claims already listed on the page. build.py gives each claim in the list
 *    these attributes:
 *        data-n        the claim number
 *        data-search   the claim, its verse references and book names
 *        data-cites    the books the claim cites
 *        data-answers  the books its TaNaKh passages come from
 *    Words typed are highlighted in the results with <mark> elements.
 *  - Reader. On a wide screen, clicking a claim shows it in the reader pane
 *    beside the list, by pointing the pane's frame at that claim's own page
 *    on this site (for claim 42, "42/panel.html"). On a narrow screen the
 *    reader pane is hidden and links open the claim's page as usual.
 *  - Keys. "/" jumps to the search box; the up and down arrows step through
 *    the results. A claim number and Enter opens that claim.
 *  - Address bar. The search, filters and chosen claim are kept in the address
 *    (?q=...&book=...&in=...&c=...) so a view can be bookmarked or shared.
 *    The search boxes on other pages send people here the same way.
 *
 * What it does not do: it loads nothing, sends nothing and stores nothing.
 * No network requests, no cookies, no local storage. The page's Content
 * Security Policy (default-src 'none') would block network requests anyway.
 * It never turns text into HTML: it only sets textContent, attributes, and
 * the hidden property, so whatever is typed stays plain text.
 */
"use strict";

(function () {
  const form = document.getElementById("search");
  const input = document.getElementById("q");
  const bookSelect = document.getElementById("book");
  const where = document.getElementById("where");
  const list = document.getElementById("claims");
  const heading = document.getElementById("list-heading");
  const status = document.getElementById("search-status");
  const readerPane = document.getElementById("reader-pane");
  const reader = document.getElementById("reader");
  if (!form || !input || !bookSelect || !where || !list || !heading || !status) {
    return;
  }

  const items = Array.from(list.children);
  const total = items.length;
  const byNumber = new Map(items.map((item) => [item.dataset.n, item]));
  const radios = Array.from(where.querySelectorAll("input[type=radio]"));

  // The original text of each result, so highlighting can be redone each time.
  const originals = new Map();
  for (const item of items) {
    for (const part of item.querySelectorAll(".text, .refs")) {
      originals.set(part, part.textContent);
    }
  }

  let selected = null;

  // ------------------------------------------------------------ reading input

  // "42", "042", "C-042", "c42" -> "42", if there is a claim 42. Otherwise null.
  function claimNumber(query) {
    const match = /^\s*c?\s*-?\s*0*(\d+)\s*$/i.exec(query);
    if (match && byNumber.has(match[1])) {
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

  function chosenPlace() {
    const radio = radios.find((r) => r.checked);
    return radio ? radio.value : "";
  }

  function setPlace(value) {
    for (const radio of radios) {
      radio.checked = radio.value === value;
    }
  }

  function bookName() {
    const option = bookSelect.options[bookSelect.selectedIndex];
    return option && option.value ? option.textContent.replace(/\s*\(\d+\)$/, "") : "";
  }

  // ------------------------------------------------------------ filtering

  function hasBook(item, book, place) {
    const cites = item.dataset.cites.split(" ").includes(book);
    const answers = item.dataset.answers.split(" ").includes(book);
    if (place === "cites") {
      return cites;
    }
    if (place === "answers") {
      return answers;
    }
    return cites || answers;
  }

  // Rewrite an element's text with every typed word wrapped in <mark>.
  function highlight(element, words) {
    const text = originals.get(element);
    element.textContent = "";
    const lower = text.toLowerCase();
    const marked = new Array(text.length).fill(false);
    for (const word of words) {
      let at = lower.indexOf(word);
      while (at !== -1) {
        marked.fill(true, at, at + word.length);
        at = lower.indexOf(word, at + word.length);
      }
    }
    let start = 0;
    while (start < text.length) {
      let end = start;
      while (end < text.length && marked[end] === marked[start]) {
        end += 1;
      }
      const piece = text.slice(start, end);
      if (marked[start]) {
        const mark = document.createElement("mark");
        mark.textContent = piece;
        element.append(mark);
      } else {
        element.append(piece);
      }
      start = end;
    }
  }

  function describe(shown, words, book, place) {
    const parts = [];
    if (words.length > 0) {
      parts.push("matching “" + input.value.trim() + "”");
    }
    if (book) {
      const how = place === "cites" ? "citing " : place === "answers" ? "answered from " : "involving ";
      parts.push(how + bookName());
    }
    return parts.join(", ");
  }

  function filter() {
    const words = searchWords(input.value);
    const number = claimNumber(input.value);
    const book = bookSelect.value;
    const place = chosenPlace();
    where.disabled = book === "";

    let shown = 0;
    for (const item of items) {
      const matches =
        item.dataset.n === number ||
        ((book === "" || hasBook(item, book, place)) &&
          words.every((word) => item.dataset.search.includes(word)));
      item.hidden = !matches;
      if (matches) {
        shown += 1;
        for (const part of item.querySelectorAll(".text, .refs")) {
          highlight(part, words);
        }
      }
    }

    const filtering = words.length > 0 || book !== "";
    if (!filtering) {
      heading.textContent = "All " + total + " claims";
    } else {
      heading.textContent = shown === 1 ? "1 claim" : shown + " claims";
    }
    status.textContent = describe(shown, words, book, place);
    if (filtering && shown === 0) {
      status.textContent += ". Nothing matches: try fewer words, or another book.";
    }
    if (number) {
      const link = document.createElement("a");
      link.className = "go";
      link.href = number + "/index.html";
      link.textContent = "Open claim " + number + " →";
      link.addEventListener("click", (event) => {
        if (readerShown()) {
          event.preventDefault();
          select(number, true);
        }
      });
      status.append(" ", link);
    }
    rememberInAddress();
  }

  // ------------------------------------------------------------ reader pane

  function readerShown() {
    return Boolean(readerPane && reader && readerPane.offsetParent !== null);
  }

  function select(number, scrollList) {
    const item = byNumber.get(number);
    if (!item) {
      return;
    }
    if (selected) {
      selected.classList.remove("selected");
      selected.querySelector("a").removeAttribute("aria-current");
    }
    selected = item;
    item.classList.add("selected");
    item.querySelector("a").setAttribute("aria-current", "true");
    if (readerShown()) {
      reader.src = number + "/panel.html";
    }
    if (scrollList) {
      item.scrollIntoView({ block: "nearest" });
    }
    rememberInAddress();
  }

  // Open a claim: in the reader on a wide screen, otherwise its own page.
  function open(number) {
    if (readerShown()) {
      select(number, true);
    } else {
      window.location.href = number + "/index.html";
    }
  }

  function step(direction) {
    const visible = items.filter((item) => !item.hidden);
    if (visible.length === 0) {
      return;
    }
    let index = visible.indexOf(selected);
    index = index === -1 ? 0 : Math.max(0, Math.min(visible.length - 1, index + direction));
    select(visible[index].dataset.n, true);
  }

  // ------------------------------------------------------------ address bar

  function rememberInAddress() {
    const url = new URL(window.location.href);
    const values = {
      q: input.value.trim(),
      book: bookSelect.value,
      in: bookSelect.value ? chosenPlace() : "",
      c: selected ? selected.dataset.n : "",
    };
    for (const [key, value] of Object.entries(values)) {
      if (value) {
        url.searchParams.set(key, value);
      } else {
        url.searchParams.delete(key);
      }
    }
    window.history.replaceState(null, "", url);
  }

  // ------------------------------------------------------------ events

  input.addEventListener("input", filter);
  bookSelect.addEventListener("change", filter);
  for (const radio of radios) {
    radio.addEventListener("change", filter);
  }

  // Enter: a claim number opens that claim. Otherwise the results are
  // already filtered; on a phone, close the keyboard so they can be seen.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const number = claimNumber(input.value);
    if (number) {
      open(number);
    } else {
      input.blur();
    }
  });

  // A plain click on a result shows it in the reader, when there is one.
  // Ctrl/Cmd/Shift-click still opens the claim's page in a new tab or window.
  list.addEventListener("click", (event) => {
    const link = event.target.closest("a.row");
    if (!link || !readerShown() || event.button !== 0 ||
        event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    select(link.parentElement.dataset.n, false);
  });

  document.addEventListener("keydown", (event) => {
    const typing = event.target === input;
    const inField = event.target.closest("input, select, textarea");
    if (event.key === "/" && !inField) {
      event.preventDefault();
      input.focus();
      input.select();
    } else if ((event.key === "ArrowDown" || event.key === "ArrowUp") && readerShown() &&
               (typing || event.target.closest("#claims"))) {
      event.preventDefault();
      step(event.key === "ArrowDown" ? 1 : -1);
    }
  });

  // ------------------------------------------------------------ start-up

  // Arriving with ?q=...&book=...&in=...&c=... (from a link, a bookmark, or
  // a search box on another page).
  const params = new URL(window.location.href).searchParams;
  const arriving = params.get("q") || "";
  const arrivingNumber = claimNumber(arriving);
  if (arrivingNumber && !readerShown()) {
    window.location.replace(arrivingNumber + "/index.html");
    return;
  }
  if (!arrivingNumber) {
    input.value = arriving;
  }
  if (params.get("book") && Array.from(bookSelect.options).some((o) => o.value === params.get("book"))) {
    bookSelect.value = params.get("book");
    setPlace(["cites", "answers"].includes(params.get("in")) ? params.get("in") : "");
  }
  filter();
  const start = arrivingNumber || params.get("c");
  if (start && byNumber.has(start)) {
    select(start, true);
  }
})();
