"""Translate English chapters into Vietnamese with a local Ollama model.

Each chapter is split into chunks of numbered paragraphs; the model must return the same
numbers, so the output stays aligned 1:1 with the English paragraphs. Every chunk result is
cached under a hash of its exact prompt, so after editing glossary.yaml a forced re-run only
re-translates the chunks whose prompt actually changed.
"""
import hashlib
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from common import ROOT, chapter_path, fmt_duration, read_json, safe_name, write_json
from context import StoryContext
from pronouns import fix_self
from pronouns import issues as xh_issues
from exporter import write_md
from glossary import Glossary
from llm import Ollama

PROMPT_VERSION = 2  # bump when RULES or the prompt layout changes, to invalidate the cache

RULES = """\
You are a professional literary translator. You translate a web novel from its English translation \
into natural, fluent Vietnamese.

OUTPUT FORMAT (strict):
- Input paragraphs are numbered [1], [2], [3]... For each one, write its Vietnamese translation on one line \
that starts with the same number in square brackets, in the same order.
- Never merge, split, skip, reorder or add paragraphs. Very short lines ("...", "!?", sound effects) still \
get their own numbered line.
- Output only the numbered translations: no notes, no explanations, no English sentences, no Chinese characters.

TRANSLATION RULES:
- Use the glossary translations exactly. Names that are not in the glossary keep their original spelling.
- For every line of dialogue, work out who is speaking and to whom (dialogue tags, the glossary, the \
previous context). Words mouthed silently, whispered, read from the lips, sent by telepathy or thought at \
someone are dialogue too.
- When the glossary gives a xưng hô pair for those two people, use exactly that pair for every line between \
them, also in tense, dangerous or angry moments; only the way a name is said may vary (a nickname in a private \
moment). Without a pair, pick natural Vietnamese pronouns from age, gender, status and relationship, and keep \
them consistent through the scene. Do not fall back on "ta / ngươi" unless the glossary gives it for that pair \
or the speaker is a hostile, arrogant enemy.
- BỐI CẢNH CHƯƠNG tells where each relationship stands at this point of the story. Pick pronouns that fit it: warm ones (tớ / cậu, anh / em, con...) only between people who are close; in narration, refer to a character the way given after "người kể gọi là" (anh ấy, anh ta, hắn, cô ấy, cô ta...), or by name.
- Use the gender given in the glossary when translating he/she/his/her.
- Keep the tone of each scene (humour, tension, sarcasm); dialogue must sound like real speech.
- Keep system messages and skill names inside square brackets, as in the source.
"""

SPEAKER_RULES = """\
You read a scene from a novel (English) and say who speaks each line of dialogue and to whom.
Dialogue includes words in quotes, after a dash, mouthed or read from the lips, whispered, sent by telepathy, \
or thought at someone.
{narrator}Give one entry for every paragraph number listed under LABEL, no more and no fewer. \
Use the names from the CHARACTERS list when possible. Write "?" when the listener is a group or unclear, \
and "-" as the speaker when a listed paragraph holds no spoken words after all. \
In an exchange of untagged lines between two people, the speakers usually alternate."""
DIALOGUE = re.compile(r"[\"“”«»]|^\s*[—–-]\s|(?:^|\s)[‘']\w")
SPEAKER_SCHEMA = {"type": "object", "required": ["lines"], "properties": {"lines": {"type": "array", "items": {
    "type": "object", "required": ["i", "speaker", "listener"],
    "properties": {"i": {"type": "integer"}, "speaker": {"type": "string"}, "listener": {"type": "string"}}}}}}

MARKER = re.compile(r"^[ \t]*[*_]*\[(\d+)\][*_]*[ \t]*", re.M)
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")
EN_WORDS = frozenset("""the and of was were with that this you your he she his her him they them their is are
been have has had its for not from what which would could should there when will into just about""".split())
PLAIN_TITLE = re.compile(r"chapter\s*(\d+)\s*[.:\-–—]?\s*", re.I)
PART = re.compile(r"^(.*?)\s*Part\s*(\d+)\s*$", re.I)  # "Retribution (2) Part 1"
TITLE_NUM = re.compile(r"^(.*?)\s*(\(\d+\))?\s*$")      # "Retribution (2)" -> core + "(2)"
TITLE_SYSTEM = ("You translate chapter titles of a fantasy web novel from English into Vietnamese.\n"
                "Reply with the Vietnamese title only: a few words, a title and not a sentence, no quotes, "
                "no explanation, no chapter number. Use the glossary translations for names and terms.")


class Stats:
    def __init__(self):
        self.calls = self.tokens = self.cached = 0
        self.gen_seconds = 0.0


def make_chunks(items, max_chars, max_paras):
    chunks, cur, size = [], [], 0
    for i, text in enumerate(items):
        if cur and (size + len(text) > max_chars or len(cur) >= max_paras):
            chunks.append(cur)
            cur, size = [], 0
        cur.append(i)
        size += len(text)
    if cur:
        chunks.append(cur)
    # Avoid a tiny trailing chunk (a whole model call for 1-2 lines, with little context):
    # fold it into the previous one, or split the last two evenly.
    if len(chunks) > 1 and len(chunks[-1]) < len(chunks[-2]) // 2:
        tail_chars = sum(len(items[i]) for i in chunks[-1])
        merged = chunks[-2] + chunks[-1]
        if len(chunks[-1]) <= max_paras // 5 and tail_chars <= max_chars // 5:
            chunks[-2:] = [merged]
        else:
            chunks[-2:] = [merged[:len(merged) // 2], merged[len(merged) // 2:]]
    return chunks


def parse_numbered(text, n):
    """Map [k] -> text. Only strictly increasing numbers in 1..n count as markers, so a bracketed
    number inside a translation (e.g. a game counter) cannot hijack the alignment."""
    marks, last = [], 0
    for m in MARKER.finditer(text):
        k = int(m.group(1))
        if last < k <= n:
            marks.append((m.start(), m.end(), k))
            last = k
    out = {}
    for i, (_, end, k) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        out[k] = " ".join(text[end:stop].split())
    return out


def looks_english(vi):
    words = re.findall(r"\w+", vi.lower())
    hits = sum(w in EN_WORDS for w in words)
    return hits >= 3 and hits / len(words) >= 0.2


def problems(src, out):
    """Hard errors that make a chunk worth retrying."""
    errs = []
    missing = [i for i, en in enumerate(src, 1) if not out.get(i) and re.search(r"\w", en)]
    if missing:
        errs.append(f"thiếu {len(missing)} đoạn")
    for i, vi in out.items():
        en = src[i - 1]
        if CJK.search(vi) and not CJK.search(en):
            errs.append(f"đoạn {i} lẫn chữ Trung/Hàn")
        elif looks_english(vi):
            errs.append(f"đoạn {i} chưa được dịch")
        elif len(en) >= 150 and len(vi) < 0.35 * len(en):
            errs.append(f"đoạn {i} có vẻ bị dịch thiếu")
    en_len = sum(len(src[i - 1]) for i in out)
    vi_len = sum(len(v) for v in out.values())
    if en_len > 400 and not 0.5 <= vi_len / en_len <= 2.5:
        errs.append(f"độ dài bất thường ({vi_len / en_len:.1f}x)")
    return errs


class Translator:
    def __init__(self, cfg, paths, model):
        llm, tr = cfg["llm"], cfg["translate"]
        self.model, self.paths = model, paths
        self.llm = Ollama(llm["url"], model, int(llm.get("timeout_seconds", 900)))
        self.options = {
            "temperature": float(llm["temperature"]),
            "top_p": float(llm.get("top_p", 0.9)),
            "num_ctx": int(llm["num_ctx"]),
            "repeat_penalty": float(llm.get("repeat_penalty", 1.0)),
        }
        self.max_chars = int(tr["chunk_chars"])
        self.max_paras = int(tr["chunk_paragraphs"])
        self.context_n = int(tr["context_paragraphs"])
        self.retries = int(tr["max_retries"])
        self.glossary = Glossary(ROOT / "glossary.yaml")
        self.hero = (cfg.get("book") or {}).get("protagonist", "")  # the first-person narrator, always "in" a scene
        self.story = StoryContext(paths, self.glossary, self.hero)
        self._packs = {}  # chapter -> its context block, sent first so every chunk of a chapter shares a prefix
        self.speaker_pass = bool(tr.get("speaker_pass", True))
        # The speaker pass may use another (faster) model than the translation; its answers are cached per model,
        # so a slow model can reuse the labels a fast one already made for the same chunks.
        self.speaker_model = tr.get("speaker_model") or model
        self.speaker_cache = paths.cache / safe_name(self.speaker_model) / "speakers"
        self._speaker_llm = None
        self.speaker_system = SPEAKER_RULES.format(
            narrator=f'Most chapters are narrated in the first person: "I" is {self.hero}.\n' if self.hero else "")
        style_file = ROOT / "style.md"
        style = ""
        if style_file.exists():
            style = "\n".join(line for line in style_file.read_text(encoding="utf-8").splitlines()
                              if not line.lstrip().startswith("#")).strip()
        self.system = RULES + (f"\nSTYLE GUIDE (tiếng Việt):\n{style}\n" if style else "")
        self.cache_dir = paths.cache / safe_name(model)
        self.use_cache = True
        self.log_path = paths.vi(model) / "_log.txt"
        self._log_lock = threading.Lock()
        # Chapter-title translations by core name ("Retribution"), editable by hand.
        self.titles_path = paths.vi(model) / "_titles.json"
        self._titles = read_json(self.titles_path) if self.titles_path.exists() else {}
        self._title_lock = threading.Lock()

    def title(self, name, stats):
        """"Retribution (2)" -> "<core in Vietnamese> (2)". Only the core goes to the model, with its own short
        prompt (alone among story lines it gets "translated" into a whole sentence), and the core's
        translation is kept in _titles.json so every chapter with that name reads the same."""
        m = TITLE_NUM.match(name)
        core, num = m.group(1).strip(), m.group(2) or ""
        with self._title_lock:
            vi = self._titles.get(core)
        if vi is None:
            terms = "\n".join(e.prompt_line() for e in self.glossary.entries_in(core))
            user = (f"BẢNG THUẬT NGỮ:\n{terms}\n\n" if terms else "") + f"TITLE: {core}"
            text, tokens, secs = self.llm.chat(TITLE_SYSTEM, user, dict(self.options, num_predict=64))
            stats.calls += 1
            stats.tokens += tokens
            stats.gen_seconds += secs
            lines = [s for s in text.strip().splitlines() if s.strip()]
            vi = re.sub(r"^(TITLE|Tiêu đề)\s*:\s*", "", lines[0].strip(), flags=re.I).strip(' "“”\'*').rstrip(".。") if lines else ""
            if not vi or len(vi) > 2 * len(core) + 20:  # empty, or a sentence instead of a title
                vi = core
            with self._title_lock:
                self._titles[core] = vi
                write_json(self.titles_path, self._titles)
        return f"{vi} {num}".strip()

    def log(self, msg):
        with self._log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    def tail(self, items):
        return items[-self.context_n:] if self.context_n else []

    def _who(self, name):
        name = (name or "").strip().strip(".")
        if not name or name in ("?", "-"):
            return None
        if name.lower() in ("i", "me", "narrator", "the narrator") and self.hero:
            return self.hero
        if name in self.glossary.known:
            return name
        first = name.split()[0]  # "Frondier de Roach" -> "Frondier"
        return first if first in self.glossary.known else name

    def speakers(self, src, context, stats):
        """[(speaker, listener) or None] for each line of src: a separate small call, cached, so that the
        translation prompt can name the xưng hô of each line (a 12B model does not track speakers well)."""
        if not self.speaker_pass:
            return None
        lines = [i for i, p in enumerate(src, 1) if DIALOGUE.search(p)]
        if not lines:
            return None
        scene = "\n".join([en for en, _ in context] + src)
        cast = [e.en for e in self.glossary.entries if e.section == "nhan_vat" and e.pattern.search(scene)]
        if self.hero and self.hero not in cast:
            cast.insert(0, self.hero)
        user = ("CHARACTERS: " + ", ".join(cast[:40]) + "\n\n"
                + ("BEFORE (context only):\n" + "\n".join(en for en, _ in context) + "\n\n" if context else "")
                + "PARAGRAPHS:\n" + "\n".join(f"[{i}] {p}" for i, p in enumerate(src, 1))
                + "\n\nLABEL: " + ", ".join(f"[{i}]" for i in lines))
        key = hashlib.sha1(json.dumps([self.speaker_model, self.speaker_system, user], ensure_ascii=False)
                           .encode("utf-8")).hexdigest()
        path = self.speaker_cache / f"{key}.json"
        if self.use_cache and path.exists():
            d = read_json(path)
        else:
            if self._speaker_llm is None:
                self._speaker_llm = (self.llm if self.speaker_model == self.model else
                                     Ollama(self.llm.url, self.speaker_model, self.llm.timeout))
            opts = dict(self.options, temperature=0.1, num_predict=60 * len(src) + 200)
            text, tokens, secs = self._speaker_llm.chat(self.speaker_system, user, opts, fmt=SPEAKER_SCHEMA)
            stats.calls += 1
            stats.tokens += tokens
            stats.gen_seconds += secs
            try:
                d = json.loads(text)
            except ValueError:
                d = {"lines": []}
            write_json(path, d)
        who = [None] * len(src)
        for x in d.get("lines", []):
            i = x.get("i")
            speaker = self._who(x.get("speaker"))
            if isinstance(i, int) and 1 <= i <= len(src) and speaker:
                who[i - 1] = (speaker, self._who(x.get("listener")))
        return who

    def pronoun_errors(self, who, out, chapter):
        """Lines that break the xưng hô rule of their (known) speaker / listener pair."""
        errs = []
        for i, w in enumerate(who or [], 1):
            r = w and w[1] and self.glossary.rule_for(w[0], w[1], chapter)
            if r and out.get(i):
                bad = xh_issues(r, out[i])
                if bad:
                    errs.append(f'[{i}] {w[0]} nói với {w[1]}: {"; ".join(bad)} (phải là "{r.self_ref} / {r.address}")')
        return errs

    def build_user(self, src, chapter_text, context, chapter, who=None):
        """context: (english, vietnamese-or-None) pairs that come right before src.
        who: (speaker, listener) or None for each line of src."""
        parts = [self._packs[chapter]] if self._packs.get(chapter) else []
        scene = "\n".join(src + [en for en, _ in context])
        block = self.glossary.prompt_block("\n".join(src), chapter_text, chapter, scene, (self.hero,) if self.hero else ())
        if block:
            parts.append(block)
        if context:
            lines = []
            for en, vi in context:
                lines.append(f"EN: {en}")
                if vi:
                    lines.append(f"VI: {vi}")
            parts.append("NGỮ CẢNH NGAY TRƯỚC (để biết ai đang nói, với ai, xưng hô ra sao; KHÔNG dịch lại):\n"
                         + "\n".join(lines))
        if who and any(who):
            lines = []
            for i, w in enumerate(who, 1):
                if not w:
                    continue
                speaker, listener = w
                r = listener and self.glossary.rule_for(speaker, listener, chapter)
                lines.append(f"[{i}] {speaker} nói với {listener or 'nhiều người / không rõ'}"
                             + (f': tự xưng "{r.self_ref}", gọi {listener} là "{r.address}"' if r else ""))
            parts.append("NGƯỜI NÓI TỪNG DÒNG (đã xác định trước, dùng để chọn xưng hô; KHÔNG dịch phần này):\n"
                         + "\n".join(lines))
        parts.append("DỊCH CÁC ĐOẠN SAU:\n" + "\n".join(f"[{i}] {p}" for i, p in enumerate(src, 1)))
        return "\n\n".join(parts)

    def chunk(self, src, chapter_text, context, stats, tag):
        who = self.speakers(src, context, stats)
        user = self.build_user(src, chapter_text, context, tag, who)
        key = hashlib.sha1(json.dumps([PROMPT_VERSION, self.model, self.system, user, self.options],
                                      ensure_ascii=False).encode("utf-8")).hexdigest()
        path = self.cache_dir / key[:2] / f"{key}.json"
        if self.use_cache and path.exists():
            stats.cached += 1
            d = read_json(path)
            return d["vi"], d["flags"]
        vi, flags = self._translate(src, chapter_text, context, stats, tag, user, who)
        write_json(path, {"vi": vi, "flags": flags})
        return vi, flags

    def _translate(self, src, chapter_text, context, stats, tag, user=None, who=None):
        user = user or self.build_user(src, chapter_text, context, tag, who)
        n = len(src)
        best, best_errs, best_perrs = {}, None, []
        # A big chunk that merges lines tends to merge the same lines again on a retry, so it is
        # split straight away; small chunks get a second try, single paragraphs get max_retries.
        attempts = self.retries + 1 if n == 1 else (2 if n <= 8 else 1)
        for attempt in range(attempts):
            opts = dict(self.options, num_predict=max(512, sum(map(len, src))),
                        temperature=self.options["temperature"] + 0.2 * attempt)
            prompt = user
            if attempt and best_perrs:
                # Say what the previous try got wrong; small models fix a named mistake far more often.
                prompt += "\n\nLẦN DỊCH TRƯỚC SAI XƯNG HÔ, SỬA LẠI: " + "; ".join(best_perrs)
            text, tokens, secs = self.llm.chat(self.system, prompt, opts)
            stats.calls += 1
            stats.tokens += tokens
            stats.gen_seconds += secs
            out = parse_numbered(text, n)
            errs = problems(src, out) + self.glossary.name_swaps(src, out)
            perrs = self.pronoun_errors(who, out, tag)
            if errs or perrs:
                self.log(f"Chương {tag}, khối {n} đoạn, lần {attempt + 1}: {'; '.join(errs + perrs)}")
            if best_errs is None or (len(errs), len(perrs)) < (len(best_errs), len(best_perrs)):
                best, best_errs, best_perrs = out, errs, perrs
            if not errs and not perrs:
                break

        if best_errs and n > 1:
            # Long chunks fail mostly by dropping/merging lines: halve and try again.
            mid = n // 2
            self.log(f"Chương {tag}: chia khối {n} đoạn thành {mid} + {n - mid}")
            va, fa = self._translate(src[:mid], chapter_text, context, stats, tag, who=who and who[:mid])
            vb, fb = self._translate(src[mid:], chapter_text, self.tail(context + list(zip(src[:mid], va))),
                                     stats, tag, who=who and who[mid:])
            return va + vb, fa + fb

        fixed = {}
        if best_perrs and n > 1:
            # Only some lines broke the xưng hô: re-translate just those, one by one, in place.
            bad = {int(e[1:e.index("]")]) for e in best_perrs}
            for i in sorted(bad):
                ctx = self.tail(context + [(src[k - 1], best.get(k)) for k in range(1, i)])
                v, f = self._translate([src[i - 1]], chapter_text, ctx, stats, tag, who=[who[i - 1]])
                best[i], fixed[i] = v[0], f[0]
            best_perrs = []

        if best_perrs and n == 1 and who and who[0]:
            # Every retry kept a wrong self-reference: swap that one word (the line stays flagged for review).
            r = who[0][1] and self.glossary.rule_for(who[0][0], who[0][1], tag)
            new = r and best.get(1) and fix_self(r, best[1])
            if new:
                self.log(f"Chương {tag}: tự thay tự xưng thành \"{r.self_ref}\" ({who[0][0]} nói với {who[0][1]})")
                best[1] = new
                best_perrs = [f'đã tự thay tự xưng thành "{r.self_ref}" ({who[0][0]} nói với {who[0][1]}), nên xem lại']

        vi, flags = [], []
        for i, en in enumerate(src, 1):
            if i in fixed:
                vi.append(best[i])
                flags.append(fixed[i])
                continue
            text, f = best.get(i, ""), list(best_errs) + list(best_perrs)
            if not text:
                text = en
                if re.search(r"[A-Za-z]", en):
                    f.append("chưa dịch, giữ bản tiếng Anh")
            f += [f"thiếu thuật ngữ {e.en} → {e.vi}" for e in self.glossary.misses(en, text)]
            vi.append(text)
            flags.append(f)
        return vi, flags

    def translate_chapter(self, n, en_dir, out_dir):
        start = time.time()
        ch = read_json(chapter_path(en_dir, n))
        title, paras = ch["title"], ch["paragraphs"]
        plain = PLAIN_TITLE.fullmatch(title)
        chapter_text = "\n".join([title] + paras)
        self._packs[n] = self.story.pack(n, chapter_text)

        # The chapter opens with the end of the previous one (English only, so that re-translating
        # chapter n-1 never invalidates the cache of chapter n).
        prev = chapter_path(en_dir, n - 1)
        context = [(p, None) for p in self.tail(read_json(prev)["paragraphs"])] if prev.exists() else []

        stats = Stats()
        if plain:
            title_vi = f"Chương {plain.group(1)}"
        else:
            # A named chapter (novelight source): "Chương 300: <name> (Phần 1)".
            part = PART.match(title)
            name = part.group(1) if part else title
            title_vi = f"Chương {n}: {self.title(name, stats)}" + (f" (Phần {part.group(2)})" if part else "")

        vi, flags = [], []
        for idx in make_chunks(paras, self.max_chars, self.max_paras):
            src = [paras[i] for i in idx]
            v, f = self.chunk(src, chapter_text, context, stats, n)
            vi += v
            flags += f
            context = self.tail(list(zip(src, v)))

        out = {
            "number": n, "title_en": title, "title_vi": title_vi, "model": self.model,
            "paragraphs": [{"en": e, "vi": v, **({"flags": f} if f else {})}
                           for e, v, f in zip(paras, vi, flags)],
            "stats": {"seconds": round(time.time() - start, 1), "llm_calls": stats.calls,
                      "tokens": stats.tokens, "gen_seconds": round(stats.gen_seconds, 1),
                      "cached_chunks": stats.cached},
        }
        write_json(chapter_path(out_dir, n), out)
        write_md(self.paths, self.model, [out])  # readable copy for review: output/md/<model>/NNNN.md
        return out


def run(cfg, paths, chapters, model, workers, force, no_cache):
    tr = Translator(cfg, paths, model)
    tr.use_cache = not no_cache
    out_dir = paths.vi(model)
    have_en = [n for n in chapters if chapter_path(paths.en, n).exists()]
    if len(have_en) < len(chapters):
        print(f"Bỏ qua {len(chapters) - len(have_en)} chương chưa có bản tiếng Anh (chạy scrape trước).")
    todo = [n for n in have_en if force or not chapter_path(out_dir, n).exists()]
    if not todo:
        print("Không còn chương nào cần dịch.")
        return
    print(f"Model {model} | {len(todo)} chương | {workers} luồng | glossary {len(tr.glossary.entries)} mục, "
          f"{len(tr.glossary.pairs)} cặp xưng hô", flush=True)

    t0, done = time.time(), 0

    def job(n):
        try:
            return n, tr.translate_chapter(n, paths.en, out_dir), None
        except Exception as e:  # keep the batch going; the chapter is retried on the next run
            return n, None, e

    def report(n, out, err):
        nonlocal done
        done += 1
        eta = (time.time() - t0) / done * (len(todo) - done)
        if err:
            print(f"[{done}/{len(todo)}] Chương {n}: LỖI {err!r}", flush=True)
            return
        st = out["stats"]
        speed = f"{st['tokens'] / st['gen_seconds']:.0f} tok/s" if st["gen_seconds"] else "từ cache"
        flagged = sum(1 for p in out["paragraphs"] if p.get("flags"))
        print(f"[{done}/{len(todo)}] Chương {n}: {st['seconds']:.0f}s, {st['llm_calls']} lượt gọi, {speed}"
              + (f", {flagged} đoạn cần xem lại" if flagged else "")
              + f" | còn ~{fmt_duration(eta)}", flush=True)

    try:
        if workers <= 1:
            for n in todo:
                report(*job(n))
        else:
            with ThreadPoolExecutor(workers) as ex:
                for fut in as_completed([ex.submit(job, n) for n in todo]):
                    report(*fut.result())
    except KeyboardInterrupt:
        print("\nĐã dừng. Phần đã dịch vẫn được lưu, chạy lại lệnh để dịch tiếp.", flush=True)
        os._exit(130)
    print(f"Xong {len(todo)} chương trong {fmt_duration(time.time() - t0)} → {out_dir}")
