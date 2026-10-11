"""Raw scrape -> data/books/<book>/en: rename the variant spellings listed in the book's aliases.yaml,
so analysis, glossary and translation see one name per character. The raw scrape stays untouched.

  python novel.py source [--source <site>] [--book <book>]

aliases.yaml:
  doi_ten_moi_chuong   renamed in every chapter
  doi_ten + tu_chuong  renamed from chapter tu_chuong on (e.g. where a new English translator took over)
  theo_khoang          {"970-971": {May: Mei}}: only safe to rename inside that chapter range
"""
import re

import yaml

from core.common import available, chapter_path, read_json, write_json
from sources import site as source_site


def _alias_pattern(mapping):
    """One regex for all variants, longest first, so "Ria Liss" wins over "Liss" and "Lirih" over "Liri".
    Hyphens count as edges: "P-Pielot", "Heukcheon-covered", "Atjie-nim"."""
    if not mapping:
        return None
    names = sorted(mapping, key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)")


def build_source(cfg, paths, site):
    src, dst = paths.raw(site), paths.en
    have = available(src)
    if not have:
        print(f"Chưa có chương nào trong {src}. Chạy: python novel.py scrape --source {site} --book {paths.book}")
        return
    foreign = [n for n in available(dst) if read_json(chapter_path(dst, n)).get("source", site) != site]
    if foreign:
        print(f"{dst} đang chứa {len(foreign)} chương dựng từ web khác. "
              f"Hãy chuyển chúng sang chỗ khác trước, lệnh này sẽ không ghi đè.")
        return
    title_of = source_site(site).title

    a_path = paths.aliases
    a = (yaml.safe_load(open(a_path, encoding="utf-8")) or {}) if a_path.exists() else {}
    every, late, start = a.get("doi_ten_moi_chuong") or {}, a.get("doi_ten") or {}, int(a.get("tu_chuong") or 1)
    ranged = []
    for key, table in (a.get("theo_khoang") or {}).items():
        lo, _, hi = str(key).partition("-")
        ranged.append((int(lo), int(hi or lo), table or {}))
    patterns = {}

    totals, every_table = {}, {}
    for n in have:
        ch = read_json(chapter_path(src, n))
        table = {**every, **(late if n >= start else {})}
        for lo, hi, extra in ranged:
            if lo <= n <= hi:
                table.update(extra)
        key = frozenset(table.items())
        if key not in patterns:
            patterns[key] = _alias_pattern(table)
        pat = patterns[key]
        every_table.update(table)
        used = {}

        def rename(text):
            if pat is None:
                return text

            def one(m):
                used[m.group(1)] = used.get(m.group(1), 0) + 1
                return table[m.group(1)]
            return pat.sub(one, text)

        out = {"number": n, "title": rename(title_of(ch, cfg)), "label": ch.get("label", str(n)),
               "paragraphs": [rename(p) for p in ch["paragraphs"]],
               "source": site, "source_id": ch.get("source_id"), "url": ch.get("url")}
        if used:
            out["aliases"] = used
        if ch.get("tl_notes"):
            out["tl_notes"] = ch["tl_notes"]
        write_json(chapter_path(dst, n), out)
        for k, v in used.items():
            totals[k] = totals.get(k, 0) + v

    stale = [n for n in available(dst) if n not in set(have)]
    for n in stale:
        chapter_path(dst, n).unlink()
    print(f"Đã dựng {len(have)} chương vào {dst} từ {src}" + (f", xoá {len(stale)} file thừa" if stale else ""))
    if totals:
        print("Đổi tên theo aliases.yaml: " + ", ".join(
            f"{k} → {every_table[k]} ({v})" for k, v in sorted(totals.items(), key=lambda kv: -kv[1])))
