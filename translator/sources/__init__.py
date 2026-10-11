"""One module per source website. Each downloads a book's English chapters into
data/sources/<site>/<book>/ and removes that site's own junk on the way (watermarks, the fan
translators' notes). Every site module offers:

  scrape(cfg, paths, chapters=None, workers=None, force=False)
  title(ch, cfg)      the chapter title to keep from one of its scraped files

`python novel.py source` then builds data/books/<book>/en from one of them (modifiers/aliases.py).
"""
from importlib import import_module

SITES = ("novelight", "novellunar")


def site(name):
    if name not in SITES:
        raise SystemExit(f"Không có web nguồn '{name}' (có: {', '.join(SITES)})")
    return import_module(f"sources.{name}")
