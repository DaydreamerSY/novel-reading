"""Export translated chapters for the web reader in ../web (a static site, e.g. GitHub Pages).

  web/books/index.json            every exported book
  web/books/<slug>/book.json      title, author, chapter list
  web/books/<slug>/c/<nnnn>.json  {"n", "title", "vi": [...], "en": [...]}
"""
import re
from datetime import datetime, timezone

from common import ROOT, available, chapter_path, read_json, write_json

WEB = ROOT.parent / "web"
# Chapters translated from an older scrape have the closing quote/bracket of a line as a
# paragraph of its own ('"Hello.' then '"'); glue it back so the reader shows no lone quotes.
STRAY = re.compile(r"""^["'\])”’」』]+$""")


def _paragraphs(ch):
    out = []
    for p in ch["paragraphs"]:
        en = p["en"].strip()
        vi = p["vi"].strip() or en
        if out and STRAY.match(vi) and (not en or STRAY.match(en)):
            prev = out[-1]
            if not prev[0].endswith(vi):
                prev[0] += vi
            if en and not prev[1].endswith(en):
                prev[1] += en
        elif vi:
            out.append([vi, en])
    return out


def export_web(cfg, paths, model, chapters):
    folder = paths.vi(model)
    chapters = [n for n in (chapters or available(folder)) if chapter_path(folder, n).exists()]
    if not chapters:
        print(f"Chưa có chương nào đã dịch bằng {model}.")
        return
    slug = cfg["source"]["slug"]
    book_dir = WEB / "books" / slug
    for n in chapters:
        ch = read_json(chapter_path(folder, n))
        paras = _paragraphs(ch)
        write_json(chapter_path(book_dir / "c", n),
                   {"n": n, "title": ch["title_vi"], "vi": [v for v, _ in paras], "en": [e for _, e in paras]})

    # The chapter list covers everything exported so far, not only this run.
    listed = [{"n": n, "title": read_json(chapter_path(book_dir / "c", n))["title"]}
              for n in available(book_dir / "c")]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    title, author = cfg["book"]["title"], cfg["book"]["author"]
    write_json(book_dir / "book.json",
               {"slug": slug, "title": title, "author": author, "model": model, "updated": now, "chapters": listed})

    index = WEB / "books" / "index.json"
    books = [b for b in (read_json(index)["books"] if index.exists() else []) if b["slug"] != slug]
    books.append({"slug": slug, "title": title, "author": author, "count": len(listed),
                  "first": listed[0]["n"], "last": listed[-1]["n"], "updated": now})
    write_json(index, {"books": books})
    print(f"{len(chapters)} chương → {book_dir} (sách hiện có {len(listed)} chương)")
