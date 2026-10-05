"""Shared helpers: config, paths, JSON I/O, chapter ranges."""
import json
import os
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent


def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def safe_name(s):
    return re.sub(r"[^\w.-]+", "_", s)


class Paths:
    def __init__(self):
        data = ROOT / "data"
        self.en = data / "en"
        self.cache = data / "cache"
        self.vi_root = data / "vi"
        self.output = ROOT / "output"

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
