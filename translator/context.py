"""Per-chapter story context ("bối cảnh chương") for the translator, the pronoun polisher and the judge.

From story/ngu_canh.yaml it takes only what fits chapter n: the arc, the characters present (their stance
towards the narrator, role and the pronoun the narrator uses for them at that point of the story) and the
relationship stage of each pair present. From data/analysis/NNNN.json it adds the relationships the summary
pass saw in this very chapter (who is hostile to whom, who is seducing whom, how they address each other).
"""
import re

import yaml

from common import ROOT, chapter_path, read_json
from glossary import _parse_range


def _ranges(items):
    out = []
    for it in items or []:
        bounds = _parse_range(str(it.get("chuong", "")))
        if bounds:
            out.append((bounds[0] or 0, bounds[1] or 10 ** 9, it))
    return out


def _at(periods, n):
    hits = [it for lo, hi, it in periods if lo <= n <= hi]
    return hits[-1] if hits else None


class StoryContext:
    def __init__(self, paths, glossary, hero=""):
        self.paths, self.glossary, self.hero = paths, glossary, hero
        path = ROOT / "story" / "ngu_canh.yaml"
        data = {}
        if path.exists():
            with open(path, encoding="utf-8") as f:
                data = yaml.load(f, Loader=yaml.BaseLoader) or {}
        self.arcs = _ranges(data.get("arc"))
        self.notes = _ranges(data.get("ghi_chu"))
        self.people = {name: _ranges(v) for name, v in (data.get("nhan_vat") or {}).items()}
        self.pairs = {}
        for key, v in (data.get("quan_he") or {}).items():
            names = [s.strip() for s in re.split(r"\s+[–-]\s+", key)]
            if len(names) == 2:
                self.pairs[tuple(names)] = _ranges(v)
        self.patterns = {e.en: e.pattern for e in glossary.entries if e.section == "nhan_vat"}

    def present(self, name, text):
        if name == self.hero:
            return True
        pat = self.patterns.get(name) or re.compile(rf"(?<!\w){re.escape(name)}(?!\w)")
        return bool(pat.search(text))

    def pack(self, n, text):
        """The context block for chapter n (text: the chapter, used to see who is present)."""
        lines = []
        arc = _at(self.arcs, n)
        if arc:
            lines.append(f"Arc: {arc.get('ten', '')} – {arc.get('noi_dung', '')}")
        cast = [(name, _at(periods, n)) for name, periods in self.people.items() if self.present(name, text)]
        cast = [(name, p) for name, p in cast if p]
        if cast:
            lines.append("Nhân vật (ở giai đoạn này):")
            for name, p in cast:
                bits = [x for x in (p.get("lap_truong"), p.get("vai_tro")) if x]
                pron = f'; người kể gọi là "{p["ngoi3"]}"' if p.get("ngoi3") else ""
                lines.append(f"- {name}: " + "; ".join(bits) + pron)
        rel = []
        for (a, b), periods in self.pairs.items():
            st = _at(periods, n)
            if st and self.present(a, text) and self.present(b, text):
                rel.append(f"- {a} – {b}: {st.get('trang_thai', '')}")
        if rel:
            lines.append("Quan hệ lúc này:")
            lines += rel
        notes = [it.get("noi_dung", "") for lo, hi, it in self.notes if lo <= n <= hi]
        if notes:
            lines.append("Lưu ý xưng hô (bắt buộc theo):")
            lines += [f"- {x}" for x in notes if x]
        seen = self.seen(n)
        if seen:
            lines.append("Ghi nhận trong chương này:")
            lines += seen
        if not lines:
            return ""
        return f"BỐI CẢNH CHƯƠNG {n} (để chọn giọng, đại từ, xưng hô; KHÔNG dịch phần này):\n" + "\n".join(lines)

    def seen(self, n, limit=12):
        """Relationships noted by the summary pass for this chapter."""
        path = chapter_path(self.paths.cache.parent / "analysis", n)
        if not path.exists():
            return []
        out = []
        for q in read_json(path).get("quan_he", [])[:limit]:
            goi = q.get("cach_goi", "")
            goi = "" if "không nói chuyện" in goi else f"; cách gọi: {goi}"
            out.append(f"- {q.get('a')} → {q.get('b')}: {q.get('mo_ta') or q.get('loai')}{goi}")
        return out
