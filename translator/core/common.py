"""Shared helpers: config, paths, JSON I/O, chapter ranges."""
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent   # translator/
# Every novel has the same layout, whichever book it is:
#   books/<slug>/               hand-edited, committed: config.yaml (merged over config.yaml), glossary.yaml,
#                               aliases.yaml, style.md, story/
#   data/books/<slug>/          generated: en/ (English, after aliases), vi/<model>/, analysis/, terms.json
#   data/sources/<site>/<slug>/ a source site's scrape of the book, as downloaded (see sources/)
#   output/<slug>/              EPUB/TXT/MD exports and reports
BOOKS = ROOT / "books"
DATA = ROOT / "data"


def _merge(base, over):
    for k, v in over.items():
        base[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def _yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config(book):
    """config.yaml (settings shared by every book) with books/<book>/config.yaml merged over it."""
    cfg = _yaml(ROOT / "config.yaml")
    own = BOOKS / book / "config.yaml"
    return _merge(cfg, _yaml(own)) if own.exists() else cfg


def book_slug(spec):
    """A --book value -> the book's folder name. Takes the folder name, a unique prefix of it, or the
    book's slug / link on a source site (novelight.book in its config). None -> default_book."""
    if not spec:
        return _yaml(ROOT / "config.yaml")["default_book"]
    slug = spec.rstrip("/").rsplit("/book/", 1)[-1].split("?")[0]
    folders = [BOOKS, *(DATA / "sources").glob("*")]
    known = sorted({p.name for d in folders if d.is_dir() for p in d.iterdir() if p.is_dir()})
    if slug in known:
        return slug
    for k in known:
        own = BOOKS / k / "config.yaml"
        if own.exists() and any(isinstance(v, dict) and v.get("book") == slug for v in _yaml(own).values()):
            return k
    hits = [k for k in known if k.startswith(slug)]
    if len(hits) > 1:
        raise SystemExit(f"--book {spec}: khớp nhiều truyện: {', '.join(hits)}")
    return hits[0] if hits else slug  # a new book, before its first scrape


def safe_name(s):
    return re.sub(r"[^\w.-]+", "_", s)


class Paths:
    def __init__(self, book):
        self.book = book
        self.home = BOOKS / book
        self.data = DATA / "books" / book
        self.output = ROOT / "output" / book
        self.cache = DATA / "cache"         # LLM answers keyed by prompt hash: safe to share between books
        self.en = self.data / "en"
        self.vi_root = self.data / "vi"
        self.analysis = self.data / "analysis"
        self.terms = self.data / "terms.json"
        self.glossary = self.home / "glossary.yaml"
        self.aliases = self.home / "aliases.yaml"
        self.style = self.home / "style.md"
        self.story = self.home / "story"

    def raw(self, site):
        """A source site's scrape of this book: English as downloaded, before aliases are applied."""
        return DATA / "sources" / site / self.book

    def vi(self, model):
        return self.vi_root / safe_name(model)


def chapter_path(folder, n):
    return folder / f"{n:04d}.json"


def available(folder):
    return sorted(int(p.stem) for p in folder.glob("[0-9][0-9][0-9][0-9].json"))


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, obj):
    """Atomic write: a crash or Ctrl+C never leaves a half-written file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def parse_range(spec, default):
    """'1-50,60,70-80' -> [1..50, 60, 70..80]; empty or 'all' -> default."""
    if not spec or spec == "all":
        return list(default)
    out = set()
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.update(range(int(a), int(b) + 1))
        elif part:
            out.add(int(part))
    return sorted(out)


def utf8_console():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def fmt_duration(seconds):
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}m" if h else f"{m}m{s:02d}s"
