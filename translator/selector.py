"""Merge two translations of each chapter into one.

Per paragraph: identical (or nearly) versions and versions that fail the automatic checks are decided
without a model; only real disagreements go to a judge model (a different model than the translators, so it
does not favour its own writing), in batches, with the chapter summary, the characters present and the
speaker / xưng hô of each line. The two candidates are shown as "1" and "2" in a random but reproducible order.

Output: data/vi/<name>/NNNN.json + output/md/<name>/NNNN.md, and output/chon-loc/NNNN.md listing every
disputed paragraph with both versions, the pick and the judge's reason.
"""
import difflib
import json
import random
import re
import time

from common import ROOT, chapter_path, fmt_duration, read_json, write_json
from exporter import write_md
from llm import Ollama
from translator import Stats, Translator, make_chunks, problems

JUDGE_RULES = """\
You are the editor of a Vietnamese translation of a fantasy web novel. Each item gives the English source \
paragraph and two Vietnamese translations, numbered 1 and 2. Pick the one that belongs in the finished book.
Judge in this order:
1. Meaning: faithful to the English, nothing missing, nothing added.
2. Xưng hô: when the speaker, the listener and their pronouns are given, the translation must use exactly those.
3. Character voice: fits the speaker's personality and relationship (see NHÂN VẬT) and the scene.
4. Natural Vietnamese that reads like a novel, not word-for-word.
5. Consistent with the glossary terms and with the paragraph before it.
{style}{why}"""
WHY = 'For "why", write at most 15 Vietnamese words.'


def _schema(reasons):
    item = {"item": {"type": "integer"}, "pick": {"type": "integer", "enum": [1, 2]}}
    if reasons:
        item["why"] = {"type": "string"}
    return {"type": "object", "required": ["choices"], "properties": {"choices": {"type": "array", "items": {
        "type": "object", "required": list(item), "properties": item}}}}


def read_style():
    """style.md without its # comment lines (the same text the translator sends)."""
    path = ROOT / "style.md"
    if not path.exists():
        return ""
    return "\n".join(line for line in path.read_text(encoding="utf-8").splitlines()
                     if not line.lstrip().startswith("#")).strip()


def _norm(s):
    return re.sub(r"\W+", " ", s.lower()).strip()


class Selector:
    def __init__(self, cfg, paths, models, judge, name, reasons=None):
        mc = cfg.get("merge") or {}
        self.paths, self.models, self.name = paths, models, name
        self.batch = int(mc.get("batch", 10))
        self.same = float(mc.get("same_ratio", 0.92))
        # The first model's Translator gives the glossary, the checks and the cached speaker pass.
        self.tr = Translator(cfg, paths, models[0])
        self.judge_model = judge
        self.judge = Ollama(cfg["llm"]["url"], judge, int(cfg["llm"].get("timeout_seconds", 1800)))
        self.options = {"temperature": 0.1, "num_ctx": int(mc.get("num_ctx", 12288))}
        # Reasons help reviewing, but cost generated tokens: a slow judge (27B) runs without them.
        self.reasons = bool(mc.get("reasons", True)) if reasons is None else reasons
        style = read_style()
        self.rules = JUDGE_RULES.format(style=f"The book's style guide (Vietnamese):\n{style}\n" if style else "",
                                        why=WHY if self.reasons else "Answer with the picks only.")
        self.schema = _schema(self.reasons)

    def checks(self, en, vi, who, n):
        if not vi.strip():
            return ["trống"]
        errs = problems([en], {1: vi}) + self.tr.glossary.name_swaps([en], {1: vi})
        errs += [f"thiếu thuật ngữ {e.en} → {e.vi}" for e in self.tr.glossary.misses(en, vi)]
        errs += self.tr.pronoun_errors([who] if who else None, {1: vi}, n)
        return [re.sub(r"^\[1\] |^đoạn 1 ", "", e) for e in errs]

    def speakers(self, n, paras):
        """The speaker pass of the first model's run, rebuilt chunk by chunk (it is cached, no model call)."""
        prev = chapter_path(self.paths.en, n - 1)
        context = [(p, None) for p in self.tr.tail(read_json(prev)["paragraphs"])] if prev.exists() else []
        who = []
        for idx in make_chunks(paras, self.tr.max_chars, self.tr.max_paras):
            src = [paras[i] for i in idx]
            who += self.tr.speakers(src, context, Stats()) or [None] * len(src)
            context = [(p, None) for p in self.tr.tail(src)]
        return who

    def characters(self, text):
        lines = []
        for e in self.tr.glossary.entries:
            if e.section == "nhan_vat" and e.pattern.search(text):
                info = ", ".join(x for x in (e.gender, e.note) if x)
                lines.append(f"- {e.en}" + (f" ({info})" if info else ""))
        return lines

    def ask(self, n, summary, items):
        """items: dicts with en, prev, cand (two texts in shown order), who, rule. Returns {k: (pick, why)}."""
        text = "\n".join(it["en"] for it in items)
        head = [f"CHƯƠNG {n}" + (f" – tóm tắt: {summary}" if summary else "")]
        cast = self.characters(text)
        if cast:
            head.append("NHÂN VẬT:\n" + "\n".join(cast))
        body = []
        for k, it in enumerate(items, 1):
            lines = [f"### Item {k}"]
            if it["who"]:
                s, l = it["who"]
                lines.append(f"Người nói: {s} nói với {l or 'nhiều người / không rõ'}"
                             + (f' (tự xưng "{it["rule"].self_ref}", gọi "{it["rule"].address}")' if it["rule"] else ""))
            if it["prev"]:
                lines.append(f"Đoạn trước (đã chọn): {it['prev']}")
            lines += [f"EN: {it['en']}", f"1: {it['cand'][0]}", f"2: {it['cand'][1]}"]
            body.append("\n".join(lines))
        user = "\n\n".join(head) + "\n\nITEMS:\n\n" + "\n\n".join(body)
        opts = dict(self.options, num_predict=(60 if self.reasons else 20) * len(items) + 100)
        raw, tokens, secs = self.judge.chat(self.rules, user, opts, fmt=self.schema)
        try:
            got = json.loads(raw).get("choices", [])
        except ValueError:
            got = []
        out = {}
        for c in got:
            k, pick = c.get("item"), c.get("pick")
            if isinstance(k, int) and 1 <= k <= len(items) and pick in (1, 2):
                out[k] = (pick, " ".join(str(c.get("why", "")).split()))
        return out, tokens, secs

    def merge_chapter(self, n):
        start = time.time()
        en = read_json(chapter_path(self.paths.en, n))
        paras = en["paragraphs"]
        cands = [read_json(chapter_path(self.paths.vi(m), n)) for m in self.models]
        for m, c in zip(self.models, cands):
            if len(c["paragraphs"]) != len(paras):
                raise RuntimeError(f"bản {m} của chương {n} có {len(c['paragraphs'])} đoạn, bản gốc {len(paras)}")
        a_all = [p["vi"] for p in cands[0]["paragraphs"]]
        b_all = [p["vi"] for p in cands[1]["paragraphs"]]
        who = self.speakers(n, paras)
        analysis = self.paths.cache.parent / "analysis" / f"{n:04d}.json"
        summary = read_json(analysis).get("tom_tat", "") if analysis.exists() else ""

        picks, disputed = [None] * len(paras), []
        for i, (e, a, b) in enumerate(zip(paras, a_all, b_all)):
            ea, eb = self.checks(e, a, who[i], n), self.checks(e, b, who[i], n)
            if difflib.SequenceMatcher(None, _norm(a), _norm(b)).ratio() >= self.same:
                picks[i] = (0, "giống nhau", "", ea)
            elif len(ea) != len(eb):
                k = 0 if len(ea) < len(eb) else 1
                picks[i] = (k, "kiểm tra", "; ".join((eb if k == 0 else ea)[:2]), [ea, eb][k])
            else:
                disputed.append(i)
                picks[i] = (0, "chờ", "", ea)  # placeholder until the judge answers

        calls = tokens = 0
        gen = 0.0
        rng = random.Random(n)
        for s in range(0, len(disputed), self.batch):
            batch = disputed[s:s + self.batch]
            items, flips = [], []
            for i in batch:
                flip = rng.random() < 0.5
                flips.append(flip)
                prev = None
                if i > 0:
                    k, _, _, _ = picks[i - 1]
                    prev = (a_all, b_all)[k][i - 1]
                w = who[i]
                rule = w and w[1] and self.tr.glossary.rule_for(w[0], w[1], n)
                cand = (b_all[i], a_all[i]) if flip else (a_all[i], b_all[i])
                items.append({"en": paras[i], "prev": prev, "cand": cand, "who": w, "rule": rule or None})
            # A small judge leans towards one position, so ask twice with the two versions swapped
            # and keep a pick only when both rounds name the same model.
            swapped = [dict(it, cand=it["cand"][::-1]) for it in items]
            rounds = []
            for its, fl in ((items, flips), (swapped, [not f for f in flips])):
                got, tok, secs = self.ask(n, summary, its)
                calls += 1
                tokens += tok
                gen += secs
                rounds.append({j: ((shown - 1) ^ int(fl[j - 1]), why) for j, (shown, why) in got.items()})
            for j, i in enumerate(batch, 1):
                r1, r2 = rounds[0].get(j), rounds[1].get(j)
                if r1 and r2 and r1[0] == r2[0]:
                    k, how, why = r1[0], "phân xử", r1[1]
                elif r1 and r2:
                    k, how, why = 0, "hoà", "hai lượt phân xử chọn khác nhau"
                else:
                    k, how, why = 0, "mặc định", "người phân xử không trả lời"
                errs = self.checks(paras[i], (a_all, b_all)[k][i], who[i], n)
                picks[i] = (k, how, why, errs)

        out_paras, wins = [], [0, 0]
        for i, (e, (k, how, why, errs)) in enumerate(zip(paras, picks)):
            wins[k] += 1
            p = {"en": e, "vi": (a_all, b_all)[k][i], "pick": self.models[k], "how": how}
            if why:
                p["why"] = why
            if errs:
                p["flags"] = errs
            out_paras.append(p)
        out = {"number": n, "title_en": cands[0]["title_en"], "title_vi": cands[0]["title_vi"],
               "model": self.name, "sources": self.models, "judge": self.judge_model,
               "paragraphs": out_paras,
               "stats": {"seconds": round(time.time() - start, 1), "llm_calls": calls, "tokens": tokens,
                         "gen_seconds": round(gen, 1), "disputed": len(disputed), "wins": dict(zip(self.models, wins)),
                         "how": {h: sum(1 for p in out_paras if p["how"] == h)
                                 for h in ("giống nhau", "kiểm tra", "phân xử", "hoà", "mặc định")}}}
        write_json(chapter_path(self.paths.vi(self.name), n), out)
        write_md(self.paths, self.name, [out])
        self.report(n, out, a_all, b_all, disputed)
        return out

    def report(self, n, out, a_all, b_all, disputed):
        st = out["stats"]
        lines = [f"# Chọn lọc chương {n}: {out['title_vi']}", "",
                 f"Bản 1: `{self.models[0]}` · Bản 2: `{self.models[1]}` · Người phân xử: `{self.judge_model}`", "",
                 f"- Tổng {len(out['paragraphs'])} đoạn: " + ", ".join(f"{k} {v}" for k, v in st["how"].items() if v),
                 "- Số đoạn được chọn: " + ", ".join(f"`{m}` {w}" for m, w in st["wins"].items()), ""]
        for i, p in enumerate(out["paragraphs"]):
            if p["how"] not in ("kiểm tra", "phân xử", "hoà", "mặc định"):
                continue
            k = self.models.index(p["pick"])
            lines += [f"## Đoạn {i + 1} – {p['how']}: chọn bản {k + 1} (`{p['pick']}`)", "",
                      f"> {p['en']}", "",
                      f"1. {'✅ ' if k == 0 else ''}{a_all[i]}",
                      f"2. {'✅ ' if k == 1 else ''}{b_all[i]}", ""]
            if p.get("why"):
                lines += [f"*Lý do:* {p['why']}", ""]
        folder = self.paths.output / "chon-loc"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / f"{n:04d}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(cfg, paths, chapters, models=None, judge=None, name=None, reasons=None):
    mc = cfg.get("merge") or {}
    models = models or mc.get("models") or ["gemma3:12b", "translategemma:12b"]
    judge = judge or mc.get("judge", "qwen3:8b")
    name = name or mc.get("name", "tuyen-chon")
    have = [n for n in chapters if all(chapter_path(paths.vi(m), n).exists() for m in models)]
    missing = sorted(set(chapters) - set(have))
    if missing:
        print(f"Bỏ qua {len(missing)} chương chưa có đủ bản dịch của {', '.join(models)}: {missing[:20]}")
    if not have:
        return
    sel = Selector(cfg, paths, models, judge, name, reasons)
    print(f"Chọn lọc {len(have)} chương: {models[0]} + {models[1]}, phân xử bằng {judge}", flush=True)
    t0 = time.time()
    for k, n in enumerate(have, 1):
        out = sel.merge_chapter(n)
        st = out["stats"]
        eta = (time.time() - t0) / k * (len(have) - k)
        print(f"[{k}/{len(have)}] Chương {n}: {st['seconds']:.0f}s, phân xử {st['how']['phân xử']} đoạn, "
              f"hoà {st['how']['hoà']} "
              f"({st['llm_calls']} lượt gọi), chọn " + ", ".join(f"{m} {w}" for m, w in st["wins"].items())
              + f" | còn ~{fmt_duration(eta)}", flush=True)
    print(f"Xong → {paths.vi(name)} · báo cáo từng đoạn: {paths.output / 'chon-loc'}")
