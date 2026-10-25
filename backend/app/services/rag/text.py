"""Turning documents into searchable passages: PDF pages, web pages, and ~350-word chunks that keep their page."""

import html as html_lib
import io
import re
from typing import Optional

WORDS_PER_CHUNK = 350
OVERLAP_WORDS = 60
MIN_PAGE_WORDS = 40   # a shorter page joins the next one (cover pages, tables of contents)

Page = tuple[Optional[int], str]   # (page number or None, text)


def clean(text: str) -> str:
    text = text.replace("\x00", " ").replace("­", "")
    text = re.sub(r"-\n(?=[a-z])", "", text)          # words broken over a line: "assess-\nment"
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{2,}", "\n\n", text)
    return text.strip()


def pdf_pages(data: bytes, max_pages: int = 300) -> list[Page]:
    """Text of each page. Scanned PDFs (images only) give no text: the caller reports that."""
    from pypdf import PdfReader   # imported here so the app starts without pypdf

    reader = PdfReader(io.BytesIO(data))
    out: list[Page] = []
    for i, page in enumerate(reader.pages[:max_pages], start=1):
        try:
            t = clean(page.extract_text() or "")
        except Exception:   # one broken page should not stop the whole report
            t = ""
        if t:
            out.append((i, t))
    return out


def html_text(html: str) -> tuple[str, str]:
    """(title, readable text) from a web page, without scripts, menus and footers where possible."""
    title_m = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    title = html_lib.unescape(re.sub(r"\s+", " ", title_m.group(1))).strip() if title_m else ""
    body = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav|aside|form)[^>]*>.*?</\1>", " ", html)
    article = re.search(r"(?is)<article[^>]*>(.*?)</article>", body)
    if article and len(article.group(1)) > 500:
        body = article.group(1)
    body = re.sub(r"(?i)<br\s*/?>|</p>|</h[1-6]>|</li>|</div>", "\n", body)
    body = re.sub(r"<[^>]+>", " ", body)
    body = html_lib.unescape(body)
    lines = [l.strip() for l in body.splitlines()]
    # Keep lines that read like sentences; drops menus and share buttons
    text = "\n".join(l for l in lines if len(l.split()) >= 6)
    return title[:300], clean(text)


def chunk_pages(pages: list[Page], size: int = WORDS_PER_CHUNK, overlap: int = OVERLAP_WORDS) -> list[dict]:
    """Passages of about `size` words with some overlap, each tagged with the page it starts on."""
    merged: list[Page] = []
    carry_page, carry = None, ""
    for page, text in pages:
        if carry:
            text = carry + "\n" + text
            page = carry_page
            carry = ""
        if len(text.split()) < MIN_PAGE_WORDS:
            carry_page, carry = page, text
            continue
        merged.append((page, text))
    if carry:
        if merged:
            p, t = merged[-1]
            merged[-1] = (p, t + "\n" + carry)
        else:
            merged.append((carry_page, carry))

    chunks: list[dict] = []
    step = max(1, size - overlap)
    for page, text in merged:
        words = text.split()
        start = 0
        while start < len(words):
            chunks.append({"page": page, "text": " ".join(words[start:start + size])})
            if start + size >= len(words):
                break
            start += step
    return [c for c in chunks if c["text"].strip()]
