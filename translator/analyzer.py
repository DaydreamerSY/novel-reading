"""Step 1 of the story bible: read every English chapter once with the local model and note what a
translator needs later: summary, setting, characters present, key events, and relationship signals
between the characters who interact (type, attitude, how one addresses the other).

Output: data/analysis/NNNN.json per chapter, and readable digests story/tom_tat/XXXX-YYYY.md
(100 chapters per file) for review and for building the story bible.
"""
import json
import os
import re
import time

from common import ROOT, chapter_path, fmt_duration, read_json, write_json
from glossary import Glossary
from llm import Ollama

PROMPT_VERSION = 3
LOAI = {
    "gia_dinh": "gia đình", "ban_be": "bạn bè", "nguoi_yeu": "người yêu", "dong_minh": "đồng minh",
    "doi_thu": "đối thủ", "ke_thu": "kẻ thù", "cap_tren": "cấp trên / cấp dưới", "thay_tro": "thầy trò",
    "chu_to": "chủ tớ", "nguoi_la": "người lạ", "khac": "khác",
}

SYSTEM = """You read one chapter of a web novel (in English) and write notes for the translator who will \
translate the novel into Vietnamese. Use only what this chapter shows; do not guess beyond it.
Write every free-text field in Vietnamese. Keep character and place names exactly as written in English.
{narrator}
Fields:
- tom_tat: 3 to 5 sentences: what happens in the chapter.
- boi_canh: one short sentence: where and when (place, occasion).
- nhan_vat: the characters who appear or speak, names as written.
- su_kien: up to 5 key events, each short.
- quan_he: EVERY pair of characters who interact in this chapter (talk to or act on each other), no limit. \
Addressing is directional, so when both speak to each other write two items (a to b, then b to a):
  a, b: the two names;
  cach_goi: how a addresses b when speaking to b: what a calls b (first name, nickname, "Senior", \
"Your Highness", "Professor", "you" only...) and the tone (lễ phép, thân mật, lạnh lùng, thô lỗ, trịch thượng...), \
at most 12 words, e.g. "gọi tên Aster, thân mật" or "gọi 'Your Highness', lễ phép". \
Never leave it empty: write "không nói chuyện trực tiếp" if a never speaks to b;
  loai: one of {loai} (nguoi_la only when they do not know each other or meet for the first time);
  mo_ta: their relationship and attitude in this chapter, at most 15 words.
- danh_tinh: identity notes: aliases, disguises, someone revealed to be someone else, name changes. Empty if none.
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "tom_tat": {"type": "string"},
        "boi_canh": {"type": "string"},
        "nhan_vat": {"type": "array", "items": {"type": "string"}},
        "su_kien": {"type": "array", "items": {"type": "string"}},
        "quan_he": {"type": "array", "items": {
            "type": "object",
            # property order is generation order: cach_goi right after the names gets filled reliably
            "properties": {
                "a": {"type": "string"}, "b": {"type": "string"},
                "cach_goi": {"type": "string", "minLength": 3},
                "loai": {"type": "string", "enum": list(LOAI)},
                "mo_ta": {"type": "string"},
            },
            "required": ["a", "b", "cach_goi", "loai", "mo_ta"],
        }},
        "danh_tinh": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["tom_tat", "boi_canh", "nhan_vat", "su_kien", "quan_he", "danh_tinh"],
}


def _clean(s):
    return " ".join(str(s).split())


class Analyzer:
    def __init__(self, cfg, paths, model):
        self.paths, self.model = paths, model
        self.llm = Ollama(cfg["llm"]["url"], model, int(cfg["llm"].get("timeout_seconds", 900)))
        self.glossary = Glossary(ROOT / "glossary.yaml")
        hero = (cfg.get("book") or {}).get("protagonist", "")
        narrator = (f'The story is narrated in the first person: "I" is {hero}. Use the name {hero} '
                    f'for the narrator in every field.') if hero else ""
        self.system = SYSTEM.format(narrator=narrator, loai=", ".join(LOAI))
        self.out_dir = paths.cache.parent / "analysis"

    def cast(self, text):
        """Known characters of this chapter from the glossary, so names and genders stay consistent."""
        lines = []
        for e in self.glossary.entries:
            if e.section == "nhan_vat" and e.pattern.search(text):
                info = ", ".join(x for x in (e.gender, e.note) if x)
                lines.append(f"- {e.en}" + (f" ({info})" if info else ""))
        return lines

    def analyze(self, n):
        ch = read_json(chapter_path(self.paths.en, n))
        text = "\n".join(ch["paragraphs"])
        cast = self.cast(text)
        user = (f"CHƯƠNG {n}\n"
                + ("NHÂN VẬT ĐÃ BIẾT (theo glossary):\n" + "\n".join(cast) + "\n" if cast else "")
                + "\nNỘI DUNG:\n" + text)
        last_err = None
        for attempt in range(3):
            options = {"temperature": 0.2 + 0.2 * attempt, "repeat_penalty": 1.1, "num_ctx": 12288,
                       "num_predict": 2500}
            raw, tokens, secs = self.llm.chat(self.system, user, options, fmt=SCHEMA)
            try:
                d = json.loads(raw)
                break
            except ValueError as e:
                last_err = e
        else:
            raise RuntimeError(f"model không trả JSON hợp lệ: {last_err}")
        result = {
            "number": n, "model": self.model, "version": PROMPT_VERSION,
            "tom_tat": _clean(d.get("tom_tat", "")),
            "boi_canh": _clean(d.get("boi_canh", "")),
            "nhan_vat": [_clean(x) for x in d.get("nhan_vat", []) if _clean(x)],
            "su_kien": [_clean(x) for x in d.get("su_kien", []) if _clean(x)][:5],
            "quan_he": [{k: _clean(q.get(k, "")) for k in ("a", "b", "loai", "mo_ta", "cach_goi")}
                        for q in d.get("quan_he", []) if q.get("a") and q.get("b") and q.get("a") != q.get("b")],
            "danh_tinh": [_clean(x) for x in d.get("danh_tinh", []) if _clean(x)],
            "stats": {"tokens": tokens, "seconds": round(secs, 1)},
        }
        write_json(chapter_path(self.out_dir, n), result)
        return result


def report(cfg, paths):
    write_digests(paths)
    write_report(paths, cfg)


def run(cfg, paths, chapters, model, force):
    an = Analyzer(cfg, paths, model)
    todo = [n for n in chapters if chapter_path(paths.en, n).exists()
            and (force or not chapter_path(an.out_dir, n).exists())]
    if not todo:
        print("Không còn chương nào cần phân tích.")
    else:
        print(f"Phân tích {len(todo)} chương bằng {model}...", flush=True)
        t0 = time.time()
        try:
            for k, n in enumerate(todo, 1):
                try:
                    r = an.analyze(n)
                    note = f"{len(r['nhan_vat'])} nhân vật, {len(r['quan_he'])} cặp quan hệ"
                except Exception as e:  # keep going; the chapter is retried on the next run
                    note = f"LỖI {e!r}"
                eta = (time.time() - t0) / k * (len(todo) - k)
                print(f"[{k}/{len(todo)}] Chương {n}: {note} | còn ~{fmt_duration(eta)}", flush=True)
        except KeyboardInterrupt:
            print("\nĐã dừng. Chạy lại lệnh để phân tích tiếp.", flush=True)
            os._exit(130)
    report(cfg, paths)


def _canonical(paths):
    """Map names the model wrote ("Frondier de Roach", "Aten Terst", "I") to the glossary's main name."""
    terms_file = paths.cache.parent / "terms.json"
    counts = {t["name"]: t["count"] for t in read_json(terms_file)["terms"]} if terms_file.exists() else {}
    people = [e.en for e in Glossary(ROOT / "glossary.yaml").entries if e.section == "nhan_vat"]
    cache = {}

    def canon(name):
        if name not in cache:
            words = name.split()
            subs = [p for p in people if p in name and all(w in words for w in p.split())]
            cache[name] = max(subs, key=lambda p: (counts.get(p, 0), -len(p))) if subs else name
        return cache[name]
    return canon


def write_report(paths, cfg=None, min_shared=3):
    """Relationship timelines per pair and identity notes, aggregated over all analysed chapters."""
    folder = paths.cache.parent / "analysis"
    done = sorted(int(p.stem) for p in folder.glob("[0-9][0-9][0-9][0-9].json"))
    if not done:
        return
    hero = ((cfg or {}).get("book") or {}).get("protagonist", "")
    canon = _canonical(paths)

    def norm(x):
        x = canon(x)
        return hero if hero and x.lower() in ("i", "tôi", "me", "narrator") else x

    pairs = {}      # (x, y) sorted -> list of (chapter, loai)
    address = {}    # (a, b) directed -> list of (chapter, cach_goi)
    ident = []
    for n in done:
        r = read_json(chapter_path(folder, n))
        seen = set()
        for q in r["quan_he"]:
            a, b = norm(q["a"]), norm(q["b"])
            if a == b:
                continue
            key = tuple(sorted((a, b)))
            if key not in seen:
                pairs.setdefault(key, []).append((n, q["loai"]))
                seen.add(key)
            goi = q["cach_goi"]
            if goi and "không nói chuyện" not in goi:
                address.setdefault((a, b), []).append((n, goi))
        ident += [(n, s) for s in r["danh_tinh"]]

    def segments(items):
        out = []
        for n, loai in items:
            if out and out[-1][2] == loai:
                out[-1][1], out[-1][3] = n, out[-1][3] + 1
            else:
                out.append([n, n, loai, 1])
        return out

    lines = ["# Quan hệ giữa các nhân vật (tổng hợp tự động)", "",
             f"Từ {len(done)} chương đã phân tích. Mỗi cặp: các giai đoạn quan hệ theo nhận định của model "
             "(chương đầu–cuối, số chương), rồi cách mỗi người gọi người kia. Nhận định từng chương có thể sai; "
             "hãy nhìn xu hướng.", ""]
    for (x, y), items in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        if len(items) < min_shared:
            continue
        lines += [f"## {x} ↔ {y} ({len(items)} chương, ch{items[0][0]}–{items[-1][0]})", ""]
        lines.append("- Quan hệ: " + " → ".join(
            f"{LOAI.get(l, l)} (ch{a}" + (f"–{b}" if b != a else "") + (f", {c} ch)" if c > 1 else ")")
            for a, b, l, c in segments(items)))
        for a, b in ((x, y), (y, x)):
            said = address.get((a, b), [])
            if not said:
                continue
            uniq, seen_goi = [], set()
            for n, goi in said:
                k = goi.lower()
                if k not in seen_goi:
                    seen_goi.add(k)
                    uniq.append(f"ch{n}: {goi}")
            shown = uniq[:4] + (["…"] + uniq[-3:] if len(uniq) > 7 else uniq[4:7])
            lines.append(f"- {a} gọi {b} ({len(said)} lần ghi nhận): " + "; ".join(shown))
        lines.append("")
    out = ROOT / "story"
    out.mkdir(exist_ok=True)
    (out / "quan_he_tong_hop.md").write_text("\n".join(lines), encoding="utf-8")

    id_lines = ["# Ghi chú danh tính (tên giả, cải trang, tiết lộ thân phận)", "",
                "Model ghi lại khi một chương có chi tiết về danh tính. Có thể sai, dùng để đối chiếu.", ""]
    id_lines += [f"- ch{n}: {s}" for n, s in ident]
    (out / "danh_tinh.md").write_text("\n".join(id_lines) + "\n", encoding="utf-8")
    print(f"Tổng hợp quan hệ ({sum(1 for v in pairs.values() if len(v) >= min_shared)} cặp) và danh tính → {out}")


def write_digests(paths, per_file=100):
    """Readable markdown, 100 chapters per file: story/tom_tat/0001-0100.md ..."""
    folder = paths.cache.parent / "analysis"
    done = sorted(int(p.stem) for p in folder.glob("[0-9][0-9][0-9][0-9].json"))
    if not done:
        return
    out_dir = ROOT / "story" / "tom_tat"
    out_dir.mkdir(parents=True, exist_ok=True)
    for start in range(((done[0] - 1) // per_file) * per_file + 1, done[-1] + 1, per_file):
        nums = [n for n in done if start <= n < start + per_file]
        if not nums:
            continue
        lines = [f"# Tóm tắt chương {start}–{start + per_file - 1}", "",
                 f"Do model local tự đọc và ghi lại, {len(nums)} chương. Có thể sai: dùng để tham khảo và đối chiếu.", ""]
        for n in nums:
            r = read_json(chapter_path(folder, n))
            lines += [f"## Chương {n}", "", f"**Bối cảnh:** {r['boi_canh']}", "", r["tom_tat"], ""]
            if r["nhan_vat"]:
                lines += [f"**Nhân vật:** {', '.join(r['nhan_vat'])}", ""]
            if r["su_kien"]:
                lines += ["**Sự kiện:**"] + [f"- {s}" for s in r["su_kien"]] + [""]
            if r["quan_he"]:
                lines.append("**Quan hệ:**")
                for q in r["quan_he"]:
                    goi = f" · {q['a']} gọi {q['b']}: {q['cach_goi']}" if q["cach_goi"] else ""
                    lines.append(f"- {q['a']} ↔ {q['b']} · {LOAI.get(q['loai'], q['loai'])} · {q['mo_ta']}{goi}")
                lines.append("")
            if r["danh_tinh"]:
                lines += ["**Danh tính:**"] + [f"- {s}" for s in r["danh_tinh"]] + [""]
        path = out_dir / f"{start:04d}-{start + per_file - 1:04d}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Tóm tắt dạng .md → {out_dir}")
