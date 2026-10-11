"""Shared helpers: config, paths, JSON I/O, chapter ranges."""
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
# Other books (--book <slug>): hand-edited files (config.yaml overrides, glossary, aliases, style, story)
# live in books/<slug>/, generated data in data/books/<slug>/, the raw novelight scrape in data/novelight/<slug>/.
BOOKS = ROOT / "books"


def _merge(base, over):
    for k, v in over.items():
        base[k] = _merge(base[k], v) if isinstance(v, dict) and isinstance(base.get(k), dict) else v
    return base


def load_config(book=None):
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    own = BOOKS / book / "config.yaml" if book else None
    if own and own.exists():
        with open(own, encoding="utf-8") as f:
            _merge(cfg, yaml.safe_load(f) or {})
    return cfg


def book_slug(spec):
    """A --book value (novelight link, slug, or a unique prefix of a book already on disk) -> its slug."""
    if not spec:
        return None
    slug = spec.rstrip("/").rsplit("/book/", 1)[-1].split("?")[0]
    known = sorted({p.name for d in (BOOKS, ROOT / "data" / "novelight") if d.is_dir()
                    for p in d.iterdir() if p.is_dir()})
    if slug in known:
        return slug
    hits = [k for k in known if k.startswith(slug)]
    if len(hits) > 1:
        raise SystemExit(f"--book {spec}: khớp nhiều truyện: {', '.join(hits)}")
    return hits[0] if hits else slug  # a new book, before its first scrape


def safe_name(s):
    return re.sub(r"[^\w.-]+", "_", s)


class Paths:
    def __init__(self, book=None):
        data = ROOT / "data"
        self.book = book                    # None = the main book, laid out as before
        self.cache = data / "cache"         # LLM answers keyed by prompt hash: safe to share between books
        if book:
            self.home = BOOKS / book
            self.data = data / "books" / book
            self.en_novelight = data / "novelight" / book
            self.output = ROOT / "output" / book
        else:
            self.home = ROOT
            self.data = data
            self.en_novelight = data / "en_novelight"
            self.output = ROOT / "output"
        self.en = self.data / "en"
        self.vi_root = self.data / "vi"
        self.analysis = self.data / "analysis"
        self.terms = self.data / "terms.json"
        self.glossary = self.home / "glossary.yaml"
        self.aliases = self.home / "aliases.yaml"
        self.style = self.home / "style.md"
        self.story = self.home / "story"

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
