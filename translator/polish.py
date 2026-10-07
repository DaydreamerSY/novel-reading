"""Pronoun polish: a bigger model reads a finished translation and fixes only the xưng hô.

It sees each chunk in English and Vietnamese, the chapter context (story/ngu_canh.yaml + the chapter summary:
who is friend or foe, how each relationship stands, how the narrator refers to each character), the xưng hô
pairs and the speaker of each line (the translator's cached speaker pass). It answers with short replacements
("anh ta" -> "anh ấy" in paragraph 12), not whole paragraphs: few generated tokens, and the rest of the text
(punctuation, quotes, meaning) cannot be touched. A replacement is applied only when both sides consist of
pronoun / address words and the old words really occur in that paragraph.

Output: data/vi/<name>/NNNN.json + output/md/<name>/NNNN.md, and output/xung-ho/NNNN.md listing every
replacement (before / after) for review.
"""
import json
import re
import time

from common import chapter_path, fmt_duration, read_json, write_json
from exporter import write_md
from llm import Ollama
from selector import read_style
from translator import Stats, Translator, make_chunks

RULES = """\
Bạn là biên tập viên tiếng Việt của bản dịch một web novel giả tưởng (dịch từ tiếng Anh).
Nhiệm vụ DUY NHẤT: tìm những chỗ dùng SAI đại từ nhân xưng / xưng hô và đề xuất từ thay thế.
- Lời thoại: tự xưng và cách gọi người nghe phải đúng cặp trong XƯNG HÔ, theo NGƯỜI NÓI TỪNG DÒNG, và hợp với \
quan hệ lúc này trong BỐI CẢNH CHƯƠNG (kẻ thù, người lạ không xưng "tớ / cậu", không gọi "con"...).
- Lời kể: đại từ ngôi thứ ba gọi một nhân vật phải theo "người kể gọi là" trong BỐI CẢNH CHƯƠNG (anh ấy, anh ta, \
hắn, cô ấy, cô ta, nàng, ông, bà, lão, nó...) và nhất quán trong cảnh.
- {narrator}
Chỉ đề xuất khi chắc chắn là sai; đúng rồi thì để yên. Mỗi đề xuất gồm: số đoạn, cụm CŨ đúng nguyên văn như \
trong bản dịch (chỉ gồm đại từ / từ xưng hô, vd "cậu", "anh ta", "tớ"), cụm MỚI thay vào, lý do tối đa 8 chữ.
Không sửa gì khác (tên riêng, thuật ngữ, câu chữ, dấu câu). Không có gì sai thì trả về danh sách rỗng.
{style}"""
SCHEMA = {"type": "object", "required": ["sua"], "properties": {"sua": {"type": "array", "items": {
    "type": "object", "required": ["i", "cu", "moi", "ly_do"],
    "properties": {"i": {"type": "integer"}, "cu": {"type": "string"}, "moi": {"type": "string"},
                   "ly_do": {"type": "string"}}}}}}

# Words a pronoun / address replacement may consist of (both the old and the new side).
PRONOUNS = set("""tôi ta tớ mình tao tui anh em chị cô cậu ông bà ngài ngươi mày hắn y gã ả nàng chàng nó lão mụ
thầy con cháu chú bác cha mẹ bố má ấy kia này họ chúng bọn các người bệ điện hạ chủ nhân tiền bối bé cụ""".split())


def _words(s):
    return re.findall(r"\w+", s.lower())


def _ok(phrase):
    w = _words(phrase)
    return bool(w) and len(w) <= 4 and all(x in PRONOUNS for x in w)


def _replace(text, old, new):
    """Replace every whole-word occurrence of `old` (case-insensitive), keeping a capital first letter."""
    pat = re.compile(rf"(?<!\w){re.escape(old)}(?!\w)", re.I)

    def one(m):
        return new[:1].upper() + new[1:] if m.group(0)[:1].isupper() else new
    return pat.subn(one, text)


class Polisher:
    def __init__(self, cfg, paths, model, source, name):
        pc = cfg.get("polish") or {}
        self.paths, self.model, self.source, self.name = paths, model, source, name
        # The default model's Translator gives the glossary, the story context and the cached speaker pass.
        self.tr = Translator(cfg, paths, cfg["llm"]["model"])
        self.llm = Ollama(cfg["llm"]["url"], model, int(cfg["llm"].get("timeout_seconds", 1800)))
        self.options = {"temperature": 0.1, "num_ctx": int(pc.get("num_ctx", 8192))}
        hero = self.tr.hero
        style = read_style()
        self.system = RULES.format(
            narrator=f'Truyện kể ngôi thứ nhất: "tôi" trong lời kể là {hero}; giữ "tôi".' if hero else
            "Giữ ngôi kể như bản dịch.",
            style=f"\nHƯỚNG DẪN VĂN PHONG:\n{style}" if style else "")

    def prompt(self, n, pack, src, vi, who):
        parts = [pack] if pack else []
        names = {e.en for e in self.tr.glossary.entries
                 if e.section == "nhan_vat" and e.pattern.search("\n".join(src))}
        if self.tr.hero:
            names.add(self.tr.hero)
        rules = [r.prompt_line() for a in sorted(names) for b in sorted(names)
                 for r in [a != b and self.tr.glossary.rule_for(a, b, n)] if r]
        if rules:
            parts.append("XƯNG HÔ:\n" + "\n".join(rules))
        lines = []
        for i, w in enumerate(who or [], 1):
            if w:
                r = w[1] and self.tr.glossary.rule_for(w[0], w[1], n)
                lines.append(f"[{i}] {w[0]} nói với {w[1] or 'nhiều người / không rõ'}"
                             + (f': tự xưng "{r.self_ref}", gọi "{r.address}"' if r else ""))
        if lines:
            parts.append("NGƯỜI NÓI TỪNG DÒNG:\n" + "\n".join(lines))
        parts.append("CÁC ĐOẠN:\n" + "\n".join(f"[{i}] EN: {e}\n[{i}] VI: {v}"
                                              for i, (e, v) in enumerate(zip(src, vi), 1)))
        return "\n\n".join(parts)

    def polish_chapter(self, n):
        start = time.time()
        en = read_json(chapter_path(self.paths.en, n))
        base = read_json(chapter_path(self.paths.vi(self.source), n))
        paras = en["paragraphs"]
        vi_all = [p["vi"] for p in base["paragraphs"]]
        if len(vi_all) != len(paras):
            raise RuntimeError(f"bản {self.source} của chương {n} có {len(vi_all)} đoạn, bản gốc {len(paras)}")
        pack = self.tr.story.pack(n, "\n".join([en["title"]] + paras))

        prev = chapter_path(self.paths.en, n - 1)
        context = [(p, None) for p in self.tr.tail(read_json(prev)["paragraphs"])] if prev.exists() else []
        new_vi, applied, rejected = list(vi_all), [], []
        calls, tokens, gen = 0, 0, 0.0
        for idx in make_chunks(paras, self.tr.max_chars, self.tr.max_paras):
            src = [paras[i] for i in idx]
            who = self.tr.speakers(src, context, Stats())  # cached from the translation run
            context = [(p, None) for p in self.tr.tail(src)]
            user = self.prompt(n, pack, src, [vi_all[i] for i in idx], who)
            raw, tok, secs = self.llm.chat(self.system, user, dict(self.options, num_predict=800), fmt=SCHEMA)
            calls, tokens, gen = calls + 1, tokens + tok, gen + secs
            try:
                got = json.loads(raw).get("sua", [])
            except ValueError:
                got = []
            for e in got:
                k, old, new = e.get("i"), str(e.get("cu", "")).strip(), str(e.get("moi", "")).strip()
                why = " ".join(str(e.get("ly_do", "")).split())
                if not isinstance(k, int) or not 1 <= k <= len(src) or not old or old.lower() == new.lower():
                    continue
                i = idx[k - 1]
                if not (_ok(old) and _ok(new)):
                    rejected.append((i, old, new, why, "không phải từ xưng hô"))
                    continue
                text, count = _replace(new_vi[i], old, new)
                if not count:
                    rejected.append((i, old, new, why, "không thấy cụm cũ trong đoạn"))
                    continue
                applied.append((i, old, new, why, new_vi[i], text))
                new_vi[i] = text

        out_paras = []
        changed = {i for i, *_ in applied}
        for i, p in enumerate(base["paragraphs"]):
            q = dict(p)
            if i in changed:
                q.update(vi=new_vi[i], polished=True,
                         why="; ".join(f"{o} → {nw} ({w})" if w else f"{o} → {nw}" for j, o, nw, w, *_ in applied if j == i))
            out_paras.append(q)
        out = dict(base, model=self.name, polished_by=self.model, source=self.source, paragraphs=out_paras,
                   polish_stats={"seconds": round(time.time() - start, 1), "llm_calls": calls, "tokens": tokens,
                                 "gen_seconds": round(gen, 1), "edits": len(applied), "paragraphs": len(changed),
                                 "rejected": len(rejected)})
        write_json(chapter_path(self.paths.vi(self.name), n), out)
        write_md(self.paths, self.name, [out])
        self.report(n, out, applied, rejected)
        return out

    def report(self, n, out, applied, rejected):
        st = out["polish_stats"]
        lines = [f"# Chỉnh xưng hô chương {n}: {out['title_vi']}", "",
                 f"Bản gốc: `{self.source}` · Model chỉnh: `{self.model}` · {st['edits']} chỗ sửa ở "
                 f"{st['paragraphs']} đoạn, {st['rejected']} đề xuất bị bỏ · {fmt_duration(st['seconds'])}", ""]
        for i, old, new, why, before, after in applied:
            lines += [f"## Đoạn {i + 1}: \"{old}\" → \"{new}\"" + (f" – {why}" if why else ""), "",
                      f"- Trước: {before}", f"- Sau: {after}", ""]
        if rejected:
            lines += ["## Đề xuất bị bỏ", ""]
            lines += [f"- Đoạn {i + 1}: \"{old}\" → \"{new}\" ({reason}{', ' + why if why else ''})"
                      for i, old, new, why, reason in rejected]
        folder = self.paths.output / "xung-ho"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{n:04d}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(cfg, paths, chapters, model=None, source=None, name=None):
    pc = cfg.get("polish") or {}
    model = model or pc.get("model", "gemma3:27b")
    source = source or pc.get("source", cfg["llm"]["model"])
    name = name or pc.get("name", "xung-ho")
    have = [n for n in chapters if chapter_path(paths.vi(source), n).exists()]
    if not have:
        print(f"Chưa có chương nào của bản {source} trong khoảng này.")
        return
    pol = Polisher(cfg, paths, model, source, name)
    print(f"Chỉnh xưng hô {len(have)} chương của bản {source} bằng {model}", flush=True)
    t0 = time.time()
    for k, n in enumerate(have, 1):
        out = pol.polish_chapter(n)
        st = out["polish_stats"]
        eta = (time.time() - t0) / k * (len(have) - k)
        print(f"[{k}/{len(have)}] Chương {n}: {st['seconds']:.0f}s, sửa {st['edits']} chỗ ở {st['paragraphs']} đoạn, "
              f"bỏ {st['rejected']} đề xuất ({st['llm_calls']} lượt gọi, {st['tokens']} token) | còn ~{fmt_duration(eta)}",
              flush=True)
    print(f"Xong → {paths.vi(name)} · từng chỗ sửa: {paths.output / 'xung-ho'}")
