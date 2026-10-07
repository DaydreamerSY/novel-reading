"""Xưng hô audit: how well each translation follows the glossary pairs and the narrator pronouns, without a model.

Dialogue: for every line whose speaker and listener are known (the cached speaker pass) and whose pair has a
glossary rule, the Vietnamese line is checked for the required self-reference and form of address. Pronouns may
be dropped (natural in Vietnamese); a line counts as wrong only when a different first-person word or a
different form of address shows up.
Narration: in a paragraph without dialogue that names exactly one character (besides the narrator) who has a
"người kể gọi là" (ngoi3) in story/ngu_canh.yaml at that chapter, the third-person pronouns of that character's
gender are compared with it.

Output: a table per translation and output/kiem-tra-xung-ho/<first>-<last>.md listing every mismatch.
"""
import re

from common import chapter_path, read_json
from context import _at
from translator import Stats, Translator, make_chunks

from pronouns import QUOTED, issues, status

MALE = ["anh ta", "anh ấy", "hắn", "gã", "ông ta", "ông ấy", "lão", "cậu ta", "cậu ấy", "y"]
FEMALE = ["cô ta", "cô ấy", "nàng", "ả", "bà ta", "bà ấy", "cô bé", "mụ"]


def _forms(text, forms):
    found = []
    for f in forms:
        for m in re.finditer(rf"(?<!\w){re.escape(f)}(?!\w)", text, re.I):
            found.append(f)
    return found


class Auditor:
    def __init__(self, cfg, paths):
        self.paths = paths
        self.tr = Translator(cfg, paths, cfg["llm"]["model"])  # glossary, story context, cached speaker pass
        self.g = self.tr.glossary

    def speakers(self, n, paras):
        prev = chapter_path(self.paths.en, n - 1)
        context = [(p, None) for p in self.tr.tail(read_json(prev)["paragraphs"])] if prev.exists() else []
        who = []
        for idx in make_chunks(paras, self.tr.max_chars, self.tr.max_paras):
            src = [paras[i] for i in idx]
            who += self.tr.speakers(src, context, Stats()) or [None] * len(src)
            context = [(p, None) for p in self.tr.tail(src)]
        return who

    def dialogue(self, n, who, vi):
        """(ok, wrong, dropped, problems) for the lines with a known pair rule."""
        ok = wrong = dropped = 0
        bad = []
        for i, (w, v) in enumerate(zip(who, vi)):
            r = w and w[1] and self.g.rule_for(w[0], w[1], n)
            if not r:
                continue
            st = status(r, v)
            if st == "sai":
                wrong += 1
                bad.append((i + 1, f"{w[0]} → {w[1]}", "; ".join(issues(r, v)), v))
            elif st == "dung":
                ok += 1
            else:
                dropped += 1
        return ok, wrong, dropped, bad

    def narration(self, n, en, vi):
        ok = wrong = 0
        bad = []
        people = self.tr.story.people
        for i, (e, v) in enumerate(zip(en, vi)):
            if QUOTED.search(v):
                continue
            named = [name for name in people if name != self.tr.hero and self.tr.story.present(name, e)]
            if len(named) != 1:
                continue
            p = _at(people[named[0]], n)
            want = (p or {}).get("ngoi3", "").lower()
            if not want:
                continue
            fam = FEMALE if any(want.startswith(x) for x in ("cô", "bà", "nàng", "ả", "mụ", "chị")) else MALE
            found = _forms(v, fam)
            if not found:
                continue
            if all(f == want for f in found) or (want not in fam and not found):
                ok += 1
            else:
                others = sorted({f for f in found if f != want})
                if want in fam and others:
                    wrong += 1
                    bad.append((i + 1, named[0], f'người kể nên gọi "{want}", bản dịch dùng "{", ".join(others)}"', v))
                else:
                    ok += 1
        return ok, wrong, bad


def run(cfg, paths, chapters, models):
    au = Auditor(cfg, paths)
    rows, details = [], []
    for m in models:
        tot = {"d_ok": 0, "d_wrong": 0, "d_drop": 0, "n_ok": 0, "n_wrong": 0}
        bad_d, bad_n = [], []
        done = [n for n in chapters if chapter_path(paths.vi(m), n).exists()]
        for n in done:
            en = read_json(chapter_path(paths.en, n))["paragraphs"]
            vi = [p["vi"] for p in read_json(chapter_path(paths.vi(m), n))["paragraphs"]]
            if len(vi) != len(en):
                continue
            who = au.speakers(n, en)
            ok, wrong, drop, bad = au.dialogue(n, who, vi)
            tot["d_ok"] += ok; tot["d_wrong"] += wrong; tot["d_drop"] += drop
            bad_d += [(n,) + b for b in bad]
            ok, wrong, bad = au.narration(n, en, vi)
            tot["n_ok"] += ok; tot["n_wrong"] += wrong
            bad_n += [(n,) + b for b in bad]
        rows.append((m, done, tot))
        details.append((m, bad_d, bad_n))

    def pct(a, b):
        return f"{100 * a / (a + b):.0f}%" if a + b else "-"
    print(f"{'bản dịch':22} {'chương':>6}  {'thoại đúng':>10} {'thoại sai':>9} {'lược bỏ':>7}  {'lời kể đúng':>11} {'lời kể lệch':>11}")
    for m, done, t in rows:
        print(f"{m:22} {len(done):6}  {t['d_ok']:5} ({pct(t['d_ok'], t['d_wrong'])}) {t['d_wrong']:9} {t['d_drop']:7}  "
              f"{t['n_ok']:6} ({pct(t['n_ok'], t['n_wrong'])}) {t['n_wrong']:11}")

    lines = [f"# Soát xưng hô chương {chapters[0]}–{chapters[-1]}", "",
             "| Bản dịch | Thoại đúng | Thoại sai | Lược bỏ đại từ | Lời kể đúng | Lời kể lệch |", "|---|---|---|---|---|---|"]
    lines += [f"| `{m}` | {t['d_ok']} ({pct(t['d_ok'], t['d_wrong'])}) | {t['d_wrong']} | {t['d_drop']} | "
              f"{t['n_ok']} ({pct(t['n_ok'], t['n_wrong'])}) | {t['n_wrong']} |" for m, done, t in rows]
    for m, bad_d, bad_n in details:
        lines += ["", f"## `{m}`", ""]
        if bad_d:
            lines += ["### Lời thoại sai quy tắc", ""]
            lines += [f"- Ch{n} ¶{i} · {pair}: {why}  \n  > {v}" for n, i, pair, why, v in bad_d]
        if bad_n:
            lines += ["", "### Lời kể lệch đại từ người kể", ""]
            lines += [f"- Ch{n} ¶{i} · {name}: {why}  \n  > {v}" for n, i, name, why, v in bad_n]
    folder = paths.output / "kiem-tra-xung-ho"
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"{chapters[0]:04d}-{chapters[-1]:04d}.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Chi tiết → {out}")
