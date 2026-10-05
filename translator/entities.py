"""List the novel's proper nouns and draft glossary entries for the user to review.

1. Script pass: capitalised phrases. Capitalisation in mid-sentence is the strong signal; a phrase
   seen only at the start of sentences is kept only when it never shows up in lowercase.
   Honorifics and titles are split off names: "Senior Ellen" counts for "Senior" and "Ellen",
   "Frondier-nim" for "-nim" and "Frondier". Per term: count, chapter span, he/she pronouns right
   after it, and a few excerpts.
2. LLM pass (local, optional): classify each term (character / place / weapon / skill ...),
   guess gender, suggest a Vietnamese rendering and a one-line description. Honorifics and
   titles from the built-in lists skip the model and get a default rendering.
3. Character pairs that share dialogue scenes, as suggestions for xưng hô rules.

Outputs glossary_draft.yaml (readable) and data/terms.json (for the editor).
"""
import json
import re
import time
from collections import Counter, defaultdict
from itertools import combinations

from common import ROOT, chapter_path, fmt_duration, read_json, safe_name, write_json
from glossary import LABELS, Glossary, term_pattern
from llm import Ollama
from translator import make_chunks

PROMPT_VERSION = 1
BATCH = 12

WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
CONNECT = {"de", "von", "van", "of", "la", "le", "du", "di", "del", "der", "the"}
STOP = set("""I I'm I'll I've I'd The A An He She It We They You My His Her Its Our Their This That These
Those There Here What When Where Why How Who Whom Whose Which But And Or So If Then Yes No Oh Ah Well Now
Just Still Even Also Not Do Does Did Don't Is Are Was Were Be Have Has Had Will Would Can Could Should May
Might Must Chapter Okay OK Hmm Huh Eh Um Uh Wait Please Thank Thanks Sorry Hey Hello Hi
Good Right After Before As At By For From In Into Of On To With Without Through During Since Until Upon
About Above Below Under Over Between Because Although Though While Once Every Each All Any Some Most Many
Much More One Two Three First Second Last Next Another Other Such Only Very Too Again Never Always Maybe
Perhaps Let Me Us Him Them Your Mine Ha Haha Ugh Ahh Whoa Wow However Whether Indeed Yeah Yes Alright Soon
Actually Suddenly Instead Besides Meanwhile Anyway Moreover Therefore Thus Nevertheless Nonetheless Unless
Otherwise Finally Eventually Certainly Obviously Naturally Fortunately Unfortunately Apparently Honestly
Seriously Really Sure Nope Nah Yep Exactly Probably Definitely Usually Rather Unlike Despite Except""".split())
CONTRACTION = re.compile(r"^[A-Za-z]+['’](re|ve|ll|m|d|t)$")  # You're, I’m, Don’t ... (not O'Brien)
OPENERS = set('"“‘\'([「『')
ENDERS = set(".!?…:")
PRONOUN = re.compile(r"\b(he|him|his|himself|she|her|hers|herself)\b", re.I)
MALE = {"he", "him", "his", "himself"}
BRACKET = re.compile(r"\[([^\[\]\n]{2,50})\]")

# Forms of address (section kinh_ngu) and positions/ranks (section danh_hieu), with a suggested
# rendering. They are split off the names they precede and never sent to the model for classification.
HONORIFICS = {
    "-nim": "ngài / anh / chị... tùy quan hệ (có thể lược bỏ)",
    "-ssi": "anh / chị / cô... lịch sự (có thể lược bỏ)",
    "-sunbae": "tiền bối", "-seonbae": "tiền bối", "-senpai": "tiền bối",
    "-sensei": "thầy / cô", "-ssaem": "thầy / cô", "-sama": "ngài",
    "-hyung": "anh", "-hyeong": "anh", "-oppa": "anh",
    "-noona": "chị", "-nuna": "chị", "-unnie": "chị", "-eonni": "chị",
    "-gun": "cậu", "-yang": "cô",
    "Sunbae": "tiền bối", "Seonbae": "tiền bối", "Hyung": "anh", "Hyeong": "anh", "Oppa": "anh",
    "Noona": "chị", "Nuna": "chị", "Unnie": "chị", "Eonni": "chị",
    "Senior": "tiền bối", "Junior": "hậu bối",
    "Miss": "cô / tiểu thư (quý tộc)", "Mister": "ông / anh", "Mr": "ông / anh", "Mrs": "bà", "Ms": "cô",
    "Madam": "phu nhân / bà", "Madame": "phu nhân / bà", "Dame": "phu nhân",
    "Lady": "tiểu thư / phu nhân (quý tộc)", "Lord": "ngài / lãnh chúa", "Sir": "ngài / hiệp sĩ",
    "Young Master": "thiếu gia", "Young Lady": "tiểu thư", "Master": "chủ nhân / sư phụ (tùy ngữ cảnh)",
    "Majesty": "Bệ hạ", "Highness": "Điện hạ", "Excellency": "các hạ",
}
TITLES = {
    "Teacher": "thầy / cô (tùy giới tính)", "Professor": "giáo sư", "Instructor": "giảng viên",
    "Headmaster": "hiệu trưởng", "Headmistress": "hiệu trưởng", "Principal": "hiệu trưởng",
    "Vice Principal": "phó hiệu trưởng", "Librarian": "thủ thư",
    "Emperor": "Hoàng đế", "Empress": "Hoàng hậu / Nữ hoàng", "King": "Quốc vương", "Queen": "Nữ vương / Hoàng hậu",
    "Prince": "Hoàng tử", "Princess": "Công chúa", "Grand Duke": "Đại công tước",
    "Grand Duchess": "Đại công tước phu nhân", "Duke": "Công tước", "Duchess": "Nữ công tước / Công tước phu nhân",
    "Marquis": "Hầu tước", "Marquess": "Hầu tước", "Count": "Bá tước", "Countess": "Nữ bá tước / Bá tước phu nhân",
    "Viscount": "Tử tước", "Baron": "Nam tước", "Baroness": "Nữ nam tước / Nam tước phu nhân",
    "Knight": "hiệp sĩ", "Commander": "chỉ huy", "Captain": "đội trưởng", "General": "tướng quân",
    "Saint": "Thánh", "Saintess": "Thánh nữ", "Archmage": "Đại pháp sư", "Elder": "trưởng lão",
}
SUFFIX = re.compile(r"^(.+?)-(" + "|".join(k[1:] for k in HONORIFICS if k.startswith("-")) + r")$", re.I)

TYPES = {
    "nhan_vat": "a person or a named creature/god (a character)",
    "kinh_ngu": "an honorific or form of address used with names (Miss, Lord, Senior, -nim)",
    "dia_danh": "a place: country, city, region, building, academy, dungeon",
    "to_chuc": "an organisation, faction, guild, noble house or family, class or team",
    "vu_khi": "a weapon or armour",
    "ky_nang": "a skill, spell, technique, ability, magic or martial art",
    "vat_pham": "another item, artifact, potion or material",
    "chung_toc": "a race, species or monster type",
    "danh_hieu": "a title, rank or position (Professor, Duke, Saint...)",
    "thuat_ngu": "another in-world term (system, event, concept)",
    "khong_phai": "NOT a proper noun: an ordinary word, exclamation or sentence-initial word",
}
ORDER = ["nhan_vat", "kinh_ngu", "danh_hieu", "dia_danh", "to_chuc", "vu_khi", "ky_nang", "vat_pham",
         "chung_toc", "thuat_ngu", "chua_phan_loai"]

SYSTEM = """You help build a glossary for translating a web novel from English into Vietnamese.
Each numbered candidate is a capitalised word or phrase found in the novel, with how often it occurs, the \
chapters it spans, how often he/she pronouns follow it, and a few short excerpts.
Return exactly one item per candidate, with the same id:
- loai: one of
{types}
- gioitinh: for nhan_vat decide from the excerpts and pronoun counts: "nam", "nu" or "khong_ro". Otherwise "khong_ro".
- vi: suggested Vietnamese rendering. Keep personal names exactly as written. For descriptive names translate \
the meaning naturally and keep the proper-name part (e.g. "Royal Academy" -> "Học viện Hoàng gia", \
"Iron Fang" -> "Nanh Sắt").
- mota: a short Vietnamese description, at most 15 words: who or what it is, its role, relationships shown in \
the excerpts. Use only the excerpts; do not invent facts.
""".format(types="\n".join(f"  {k}: {v}" for k, v in TYPES.items()))

SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "loai": {"type": "string", "enum": list(TYPES)},
            "gioitinh": {"type": "string", "enum": ["nam", "nu", "khong_ro"]},
            "vi": {"type": "string"},
            "mota": {"type": "string"},
        },
        "required": ["id", "loai", "gioitinh", "vi", "mota"],
    }}},
    "required": ["items"],
}


class Term:
    def __init__(self, name):
        self.name = name
        self.occ = []  # (chapter, paragraph index, start, end)
        self.male = self.female = 0
        self.fixed = None  # section for built-in honorifics/titles

    @property
    def count(self):
        return len(self.occ)

    @property
    def first(self):
        return self.occ[0][0]

    @property
    def last(self):
        return self.occ[-1][0]


def _runs(text):
    """Runs of Capitalised words joined only by spaces (allowing de/von/of...)."""
    runs, cur, prev_end = [], [], 0
    for m in WORD.finditer(text):
        w = m.group()
        joined = bool(cur) and text[prev_end:m.start()].strip() == ""
        if w[0].isupper():
            if cur and not joined:
                runs.append(cur)
                cur = []
            cur.append(m)
        elif w.lower() in CONNECT and joined:
            cur.append(m)
        else:
            if cur:
                runs.append(cur)
            cur = []
        prev_end = m.end()
    if cur:
        runs.append(cur)
    return runs


def _sentence_start(text, pos):
    i = pos - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    return i < 0 or text[i] in ENDERS or text[i] in OPENERS


def _title_len(spans, titles):
    """Number of leading words forming a known honorific/title (0, 1 or 2)."""
    if len(spans) >= 2 and f"{spans[0][2]} {spans[1][2]}" in titles:
        return 2
    return 1 if spans and spans[0][2] in titles else 0


def collect(paths, chapters, extra_titles=()):
    """Returns ({chapter: paragraphs}, [Term]) with occurrences and pronoun evidence filled in."""
    data = {}
    for n in chapters:
        p = chapter_path(paths.en, n)
        if p.exists():
            data[n] = read_json(p)["paragraphs"]
    lower = Counter(w.lower() for ps in data.values() for para in ps
                    for w in WORD.findall(para) if w[0].islower())
    fixed = {**{k: "kinh_ngu" for k in HONORIFICS}, **{k: "danh_hieu" for k in TITLES},
             **{k: "danh_hieu" for k in extra_titles}}
    prefixes = {k for k in fixed if not k.startswith("-")}

    terms = {}

    def add(name, n, pi, s, e):
        terms.setdefault(name, Term(name)).occ.append((n, pi, s, e))

    def name_of(spans):
        return " ".join(w for _, _, w in spans)

    mid, initial, brackets = [], [], []
    for n, ps in data.items():
        for pi, para in enumerate(ps):
            for run in _runs(para):
                spans = []
                for m in run:
                    w = re.sub(r"['’]s$", "", m.group()).rstrip("'’")
                    w = re.sub(r"^([A-Za-z]{1,2})-(?=\1)", "", w, flags=re.I)  # stutter: F-Frondier, I-I'm
                    sm = SUFFIX.match(w)
                    if sm:  # Frondier-nim -> "Frondier" + "-nim"
                        base = sm.group(1)
                        add("-" + sm.group(2).lower(), n, pi, m.start() + len(base), m.end())
                        w = base
                    spans.append((m.start(), m.start() + len(w), w))
                while spans and spans[-1][2].lower() in CONNECT:
                    spans.pop()
                while spans and (spans[0][2] in STOP or CONTRACTION.match(spans[0][2])
                                 or (spans[0][2].lower() in CONNECT and spans[0][2][0].islower())):
                    spans.pop(0)
                k = _title_len(spans, prefixes)
                if k:
                    rest, title = spans[k:], name_of(spans[:k])
                    after = para[spans[k - 1][1]:spans[k - 1][1] + 1]
                    if not rest:
                        # alone: count it mid-sentence, or as a vocative ("Senior, wait!")
                        if not _sentence_start(para, spans[0][0]) or after in (",", "!", "?"):
                            add(title, n, pi, spans[0][0], spans[k - 1][1])
                        continue
                    if (rest[0][2][0].isupper() and lower[rest[0][2].lower()] < 3
                            and rest[0][2] not in prefixes):
                        # "Senior Ellen" -> "Senior" + "Ellen"; "Lady of the Lake" stays whole
                        add(title, n, pi, spans[0][0], spans[k - 1][1])
                        spans = rest
                if spans:
                    (initial if _sentence_start(para, spans[0][0]) else mid).append((n, pi, spans))
            for m in BRACKET.finditer(para):
                if len(m.group(1).split()) <= 6:
                    brackets.append((n, pi, m.start(), m.end(), f"[{m.group(1).strip()}]"))

    mid_names = {name_of(spans) for _, _, spans in mid}
    for n, pi, spans in mid:
        add(name_of(spans), n, pi, spans[0][0], spans[-1][1])
    for n, pi, spans in initial:
        name = name_of(spans)
        if name in mid_names:
            add(name, n, pi, spans[0][0], spans[-1][1])
        elif len(spans) > 1 and name_of(spans[1:]) in mid_names:
            # "Suddenly Aster ..." -> "Aster": the first word is only capitalised by the sentence
            add(name_of(spans[1:]), n, pi, spans[1][0], spans[-1][1])
        elif all(lower[w.lower()] < 2 for _, _, w in spans):
            add(name, n, pi, spans[0][0], spans[-1][1])
    for n, pi, s, e, name in brackets:
        if name[1:-1] not in terms:  # "[X]" adds nothing when X itself is already a term
            add(name, n, pi, s, e)

    for t in terms.values():
        t.fixed = fixed.get(t.name)
        t.occ.sort()
        for n, pi, s, e in t.occ:
            after = data[n][pi][e:e + 160]
            m = PRONOUN.search(after)
            # another name before the pronoun: it most likely refers to that one
            if m and not any(w[0].isupper() and w not in STOP for w in WORD.findall(after[:m.start()])):
                if m.group(1).lower() in MALE:
                    t.male += 1
                else:
                    t.female += 1
    return data, list(terms.values())


def _excerpts(term, data, k=3):
    picks = sorted({0, len(term.occ) // 2, len(term.occ) - 1})[:k]
    out = []
    for i in picks:
        n, pi, s, e = term.occ[i]
        para = data[n][pi]
        a, b = max(0, s - 100), min(len(para), e + 140)
        out.append(("…" if a else "") + " ".join(para[a:b].split()) + ("…" if b < len(para) else ""))
    return out


def classify(cfg, paths, terms, data, model):
    cache_path = paths.cache / f"terms_{safe_name(model)}.json"
    cache = read_json(cache_path) if cache_path.exists() else {}
    if cache.get("version") != PROMPT_VERSION:
        cache = {"version": PROMPT_VERSION, "items": {}}
    results = cache["items"]
    todo = [t for t in terms if t.name not in results]
    if not todo:
        return results

    llm = Ollama(cfg["llm"]["url"], model, int(cfg["llm"].get("timeout_seconds", 900)))
    batches = [todo[i:i + BATCH] for i in range(0, len(todo), BATCH)]
    print(f"Phân loại {len(todo)} cụm bằng {model} ({len(batches)} lượt gọi)...", flush=True)
    t0 = time.time()
    failed = []
    for k, batch in enumerate(batches, 1):
        failed += _classify(llm, batch, data, results)
        write_json(cache_path, cache)
        eta = (time.time() - t0) / k * (len(batches) - k)
        print(f"[{k}/{len(batches)}] xong {len(batch)} cụm | còn ~{fmt_duration(eta)}", flush=True)
    if failed:
        print(f"  {len(failed)} cụm model không phân loại được, để ở mục chua_phan_loai.")
    return results


def _classify(llm, batch, data, results, attempt=0):
    """Classify a batch; whatever the model skipped is retried in halves. Returns the terms that never worked."""
    missing = _classify_batch(llm, batch, data, results, attempt)
    if not missing or attempt >= 3:
        return missing
    if len(missing) == 1:
        return _classify(llm, missing, data, results, attempt + 1)
    mid = len(missing) // 2
    return (_classify(llm, missing[:mid], data, results, attempt + 1)
            + _classify(llm, missing[mid:], data, results, attempt + 1))


ITEM = re.compile(r"\{[^{}]*\}")


def _classify_batch(llm, batch, data, results, attempt):
    blocks = []
    for i, t in enumerate(batch, 1):
        lines = [f"{i}. {t.name} | {t.count} lần | chương {t.first}-{t.last} | "
                 f"đại từ ngay sau tên: he {t.male}, she {t.female}"]
        lines += [f"   - {x}" for x in _excerpts(t, data)]
        blocks.append("\n".join(lines))
    # Small models in JSON mode can get stuck repeating a phrase inside a string until the token
    # limit: a repeat penalty plus a higher temperature on retries breaks the loop.
    options = {"temperature": 0.1 + 0.2 * attempt, "repeat_penalty": 1.15, "num_ctx": 8192,
               "num_predict": 160 * len(batch)}
    text, _, _ = llm.chat(SYSTEM, "\n\n".join(blocks), options, fmt=SCHEMA)
    try:
        items = json.loads(text).get("items", [])
    except ValueError:
        # Truncated output: keep every item object that was completed before the break.
        items = []
        for m in ITEM.finditer(text):
            try:
                items.append(json.loads(m.group()))
            except ValueError:
                pass
    got = {it.get("id"): it for it in items if isinstance(it, dict)}
    missing = []
    for i, t in enumerate(batch, 1):
        it = got.get(i)
        if it and it.get("loai") in TYPES:
            results[t.name] = {k: " ".join(str(it.get(k, "")).split()) for k in ("loai", "gioitinh", "vi", "mota")}
        else:
            missing.append(t)
    return missing


def scene_pairs(data, names, top=40):
    """Character pairs that appear together in chunks containing dialogue."""
    pats = {nm: term_pattern(nm) for nm in names}
    count, first = Counter(), {}
    for n in sorted(data):
        ps = data[n]
        for idx in make_chunks(ps, 2500, 40):
            text = "\n".join(ps[i] for i in idx)
            if '"' not in text and "“" not in text:
                continue
            present = sorted(nm for nm, p in pats.items() if p.search(text))
            for a, b in combinations(present, 2):
                wa, wb = set(a.split()), set(b.split())
                if wa <= wb or wb <= wa:  # "Aster" and "Aster Leon" are the same person
                    continue
                count[(a, b)] += 1
                first.setdefault((a, b), n)
    return [{"a": a, "b": b, "count": c, "first": first[(a, b)]} for (a, b), c in count.most_common(top)]


def pronoun_gender(t):
    """Gender from he/she counts after the name, when the evidence is clear."""
    if t.male >= 5 and t.male >= 3 * t.female:
        return "nam"
    if t.female >= 5 and t.female >= 3 * t.male:
        return "nữ"
    return ""


def decide_gender(t, model_answer):
    """(gender, warning). The model sees three excerpts; the pronoun counts cover every mention."""
    model_g = {"nam": "nam", "nu": "nữ"}.get(model_answer, "")
    stats_g = pronoun_gender(t)
    if not model_g:
        return stats_g, "giới tính điền theo thống kê đại từ" if stats_g else ""
    if stats_g and stats_g != model_g:
        return stats_g, f"⚠ KIỂM TRA: model đoán {model_g}, thống kê đại từ nghiêng về {stats_g}"
    return model_g, ""


def make_records(terms, results):
    """One dict per term: what the draft, terms.json and the editor show."""
    records = []
    for t in terms:
        r = results.get(t.name)
        rec = {"name": t.name, "count": t.count, "first": t.first, "last": t.last,
               "he": t.male, "she": t.female, "loai": r["loai"] if r else "chua_phan_loai",
               "vi": r["vi"] if r else "", "mota": r["mota"] if r else "", "gioitinh": "", "warn": ""}
        if t.fixed:
            rec.update(loai=t.fixed, vi=HONORIFICS.get(t.name) or TITLES.get(t.name) or rec["vi"],
                       mota="kính ngữ" if t.fixed == "kinh_ngu" else "chức danh")
        elif rec["loai"] == "nhan_vat":
            rec["gioitinh"], rec["warn"] = decide_gender(t, r["gioitinh"])
            rec["vi"] = rec["vi"] or t.name
        records.append(rec)
    return records


def write_draft(path, records, pairs, n_chapters, model):
    def q(s):
        return json.dumps(s, ensure_ascii=False)

    by = defaultdict(list)
    for rec in records:
        by[rec["loai"]].append(rec)
    lines = [
        f"# BẢN NHÁP GLOSSARY: trích tự động từ {n_chapters} chương"
        + (f", model {model} phân loại." if model else " (chưa phân loại bằng model)."),
        "# CẦN DUYỆT TAY: model có thể phân loại sai, đoán sai giới tính, gợi ý bản dịch chưa hay.",
        "# Dễ hơn: python novel.py edit  (công cụ chỉnh sửa trên trình duyệt, gom các mục trùng nhau).",
        "# - Cuối mỗi dòng: số lần xuất hiện, chương đầu-cuối; nhân vật có thêm số lần he/she đứng ngay sau tên.",
        "# - Mục nào để vi rỗng thì không được gửi cho model.",
    ]
    for key in ORDER:
        items = by.get(key)
        if not items:
            continue
        lines += ["", f"{key}:  # {LABELS.get(key, 'chưa phân loại')}: {len(items)} mục"]
        for rec in items:
            meta = f"{rec['count']} lần, ch{rec['first']}-{rec['last']}"
            if key == "nhan_vat":
                warn = f" | {rec['warn']}" if rec["warn"] else ""
                lines += [f"  {q(rec['name'])}:  # {meta}, he {rec['he']} / she {rec['she']}{warn}",
                          f"    vi: {q(rec['vi'])}",
                          f"    gioitinh: {q(rec['gioitinh'])}",
                          '    ngoi3: ""',
                          f"    ghichu: {q(rec['mota'])}"]
            else:
                desc = f" | {rec['mota']}" if rec["mota"] else ""
                lines.append(f"  {q(rec['name'])}: {q(rec['vi'])}  # {meta}{desc}")

    rejected = by.get("khong_phai", [])
    if rejected:
        lines += ["", f"# KHÔNG PHẢI TÊN RIÊNG theo model ({len(rejected)} mục). Có tên bị loại nhầm thì chép lên mục đúng:"]
        lines += [f"#   {q(rec['name'])}  ({rec['count']} lần) {rec['mota']}" for rec in rejected]

    lines += ["", "xung_ho:",
              "  # Các cặp nhân vật hay cùng xuất hiện trong cảnh có hội thoại, nhiều nhất trước.",
              '  # Bỏ dấu # và điền "tự xưng / gọi". Quan hệ thay đổi theo thời gian: dùng khoảng chương (xem glossary.yaml).']
    for p in pairs:
        a, b = p["a"], p["b"]
        lines.append(f"  # {q(f'{a} > {b}')}: \"\"    # {p['count']} cảnh chung, từ ch{p['first']}")
        lines.append(f"  # {q(f'{b} > {a}')}: \"\"")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_draft(cfg, paths, chapters, model, min_count, use_llm):
    glossary = Glossary(ROOT / "glossary.yaml")
    extra = (cfg.get("terms") or {}).get("extra_titles") or []
    data, terms = collect(paths, chapters, extra)
    terms = [t for t in terms if t.count >= min_count]
    terms.sort(key=lambda t: (-t.count, t.name))
    print(f"{len(terms)} cụm xuất hiện ≥ {min_count} lần trong {len(data)} chương "
          f"({sum(1 for t in terms if t.fixed)} kính ngữ/chức danh nhận diện sẵn)", flush=True)

    results = {}
    to_classify = [t for t in terms if not t.fixed]
    if use_llm and to_classify:
        cached = classify(cfg, paths, to_classify, data, model)
        results = {t.name: cached[t.name] for t in to_classify if t.name in cached}
    records = make_records(terms, results)

    chars = [r["name"] for t, r in zip(terms, records)
             if r["loai"] == "nhan_vat" or (not results and not t.fixed and t.male + t.female >= 3)]
    pairs = scene_pairs(data, chars[:150])

    write_json(paths.cache.parent / "terms.json", {"chapters": len(data), "model": model if use_llm else None,
                                                    "terms": records, "pairs": pairs})
    new = [r for r in records if r["name"] not in glossary.known]
    out = ROOT / "glossary_draft.yaml"
    write_draft(out, new, pairs, len(data), model if use_llm else None)

    kinds = Counter(r["loai"] for r in records)
    print(f"→ {out} và data/terms.json\n  " + ", ".join(f"{LABELS.get(k, k)} {v}" for k, v in kinds.most_common())
          + f"; {len(pairs)} cặp nhân vật gợi ý xưng hô")
    warn = Counter(r["warn"][:1] for r in records if r["warn"])
    if warn:
        print(f"  giới tính: {sum(v for k, v in warn.items() if k != '⚠')} nhân vật điền theo thống kê đại từ, "
              f"{warn.get('⚠', 0)} mục ⚠ cần kiểm tra")
