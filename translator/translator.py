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
previous context). Start from the default pronouns (xưng hô) given for that pair; without one, pick natural \
Vietnamese pronouns from age, gender, status and relationship. Switch only when the scene clearly calls for it \
(an intimate private moment, a nickname, anger, a formal setting, a change in the relationship), and keep each \
pair's pronouns consistent through the scene.
- Use the gender given in the glossary when translating he/she/his/her.
- Keep the tone of each scene (humour, tension, sarcasm); dialogue must sound like real speech.
- Keep system messages and skill names inside square brackets, as in the source.
"""

MARKER = re.compile(r"^[ \t]*[*_]*\[(\d+)\][*_]*[ \t]*", re.M)
CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿가-힯豈-﫿]")
EN_WORDS = frozenset("""the and of was were with that this you your he she his her him they them their is are
been have has had its for not from what which would could should there when will into just about""".split())
PLAIN_TITLE = re.compile(r"chapter\s*(\d+)\s*[.:\-–—]?\s*", re.I)


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

    def log(self, msg):
        with self._log_lock:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")

    def tail(self, items):
        return items[-self.context_n:] if self.context_n else []

    def build_user(self, src, chapter_text, context, chapter):
        """context: (english, vietnamese-or-None) pairs that come right before src."""
        parts = []
        block = self.glossary.prompt_block("\n".join(src), chapter_text, chapter)
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
        parts.append("DỊCH CÁC ĐOẠN SAU:\n" + "\n".join(f"[{i}] {p}" for i, p in enumerate(src, 1)))
        return "\n\n".join(parts)

    def chunk(self, src, chapter_text, context, stats, tag):
        user = self.build_user(src, chapter_text, context, tag)
        key = hashlib.sha1(json.dumps([PROMPT_VERSION, self.model, self.system, user, self.options],
                                      ensure_ascii=False).encode("utf-8")).hexdigest()
        path = self.cache_dir / key[:2] / f"{key}.json"
        if self.use_cache and path.exists():
            stats.cached += 1
            d = read_json(path)
            return d["vi"], d["flags"]
        vi, flags = self._translate(src, chapter_text, context, stats, tag, user)
        write_json(path, {"vi": vi, "flags": flags})
        return vi, flags

    def _translate(self, src, chapter_text, context, stats, tag, user=None):
        user = user or self.build_user(src, chapter_text, context, tag)
        n = len(src)
        best, best_errs = {}, None
        # A big chunk that merges lines tends to merge the same lines again on a retry, so it is
        # split straight away; small chunks get a second try, single paragraphs get max_retries.
        attempts = self.retries + 1 if n == 1 else (2 if n <= 8 else 1)
        for attempt in range(attempts):
            opts = dict(self.options, num_predict=max(512, sum(map(len, src))),
                        temperature=self.options["temperature"] + 0.2 * attempt)
            text, tokens, secs = self.llm.chat(self.system, user, opts)
            stats.calls += 1
            stats.tokens += tokens
            stats.gen_seconds += secs
            out = parse_numbered(text, n)
            errs = problems(src, out) + self.glossary.name_swaps(src, out)
            if errs:
                self.log(f"Chương {tag}, khối {n} đoạn, lần {attempt + 1}: {'; '.join(errs)}")
            if best_errs is None or len(errs) < len(best_errs):
                best, best_errs = out, errs
            if not errs:
                break

        if best_errs and n > 1:
            # Long chunks fail mostly by dropping/merging lines: halve and try again.
            mid = n // 2
            self.log(f"Chương {tag}: chia khối {n} đoạn thành {mid} + {n - mid}")
            va, fa = self._translate(src[:mid], chapter_text, context, stats, tag)
            vb, fb = self._translate(src[mid:], chapter_text, self.tail(context + list(zip(src[:mid], va))),
                                     stats, tag)
            return va + vb, fa + fb

        vi, flags = [], []
        for i, en in enumerate(src, 1):
            text, f = best.get(i, ""), list(best_errs)
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
        items = paras if plain else [title] + paras
        chapter_text = "\n".join([title] + paras)

        # The chapter opens with the end of the previous one (English only, so that re-translating
        # chapter n-1 never invalidates the cache of chapter n).
        prev = chapter_path(en_dir, n - 1)
        context = [(p, None) for p in self.tail(read_json(prev)["paragraphs"])] if prev.exists() else []

        stats = Stats()
        vi, flags = [], []
        for idx in make_chunks(items, self.max_chars, self.max_paras):
            src = [items[i] for i in idx]
            v, f = self.chunk(src, chapter_text, context, stats, n)
            vi += v
            flags += f
            context = self.tail(list(zip(src, v)))
        if plain:
            title_vi = f"Chương {plain.group(1)}"
        else:
            title_vi, vi, flags = vi[0], vi[1:], flags[1:]

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
