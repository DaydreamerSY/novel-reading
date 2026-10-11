"""Hand-maintained glossary (glossary.yaml): matching per chunk and the prompt block sent to the model."""
import re

import yaml

LABELS = {
    "nhan_vat": "nhân vật",
    "kinh_ngu": "kính ngữ",
    "dia_danh": "địa danh",
    "to_chuc": "tổ chức",
    "vu_khi": "vũ khí",
    "ky_nang": "kỹ năng",
    "vat_pham": "vật phẩm",
    "chung_toc": "chủng tộc",
    "danh_hieu": "danh hiệu",
    "thuat_ngu": "thuật ngữ",
}
GENDERS = {"nam": "nam", "nu": "nữ", "nữ": "nữ"}
RANGE = re.compile(r"^\s*(\d*)\s*(-?)\s*(\d*)\s*$")


class Entry:
    def __init__(self, en, section, value):
        self.en = en
        self.section = section
        if isinstance(value, dict):
            self.vi = (value.get("vi") or "").strip()
            self.gender = GENDERS.get((value.get("gioitinh") or "").strip().lower(), "")
            self.third = (value.get("ngoi3") or "").strip()
            self.note = (value.get("ghichu") or "").strip()
        else:
            self.vi, self.gender, self.third, self.note = (value or "").strip(), "", "", ""
        # Characters are relevant to the whole chapter (he/she can refer to them anywhere);
        # other terms only matter where they literally appear.
        self.chapter_wide = section == "nhan_vat" or bool(self.third or self.gender)
        self.pattern = term_pattern(en)
        self.vi_pattern = term_pattern(self.vi) if self.vi else self.pattern

    @property
    def is_honorific(self):
        return self.section == "kinh_ngu"

    def prompt_line(self):
        info = [LABELS.get(self.section, self.section.replace("_", " "))]
        if self.gender:
            info.append(self.gender)
        if self.third:
            info.append(f'ngôi thứ 3: "{self.third}"')
        if self.note:
            info.append(self.note)
        return f"- {self.en} → {self.vi} ({'; '.join(info)})"


class Rule:
    """Xưng hô of one speaker towards one listener, optionally limited to a chapter range."""

    def __init__(self, speaker, listener, value, lo=None, hi=None):
        self.speaker, self.listener = speaker, listener
        self.self_ref, self.address = (s.strip() for s in value.split("/", 1))
        self.lo, self.hi = lo, hi

    def applies(self, chapter, chapter_text):
        if chapter is not None and ((self.lo and chapter < self.lo) or (self.hi and chapter > self.hi)):
            return False
        return _mentions(self.speaker, chapter_text) and _mentions(self.listener, chapter_text)

    @property
    def width(self):
        return (self.hi or 10 ** 9) - (self.lo or 0)

    def prompt_line(self):
        return f'- {self.speaker} nói với {self.listener}: tự xưng "{self.self_ref}", gọi {self.listener} là "{self.address}"'


def _parse_range(key):
    """'1-150' -> (1, 150); '151-' -> (151, None); '-50' -> (None, 50); '7' -> (7, 7)."""
    m = RANGE.match(key)
    if not m or not (m.group(1) or m.group(3)):
        return None
    lo = int(m.group(1)) if m.group(1) else None
    hi = int(m.group(3)) if m.group(3) else None
    return (lo, lo) if not m.group(2) else (lo, hi)


class Glossary:
    def __init__(self, path):
        self.entries, self.rules = [], []
        self.known = set()
        if not path.exists():
            return
        with open(path, encoding="utf-8") as f:
            # BaseLoader keeps every value a string: names like "Yes" or "On" stay names.
            data = yaml.load(f, Loader=yaml.BaseLoader) or {}
        for section, items in data.items():
            if not isinstance(items, dict):
                continue
            if section == "xung_ho":
                self._load_rules(items)
                continue
            for en, value in items.items():
                entry = Entry(en.strip(), section, value)
                self.known.add(entry.en)
                if entry.vi:
                    self.entries.append(entry)

    def _load_rules(self, items):
        for key, value in items.items():
            if ">" not in key:
                print(f"glossary.yaml: bỏ qua xưng hô sai định dạng (thiếu '>'): {key}")
                continue
            speaker, listener = (s.strip() for s in key.split(">", 1))
            if isinstance(value, dict):  # different pronouns for different chapter ranges
                for rng, v in value.items():
                    bounds = _parse_range(rng)
                    if bounds is None or "/" not in (v or ""):
                        print(f"glossary.yaml: bỏ qua xưng hô sai định dạng: {key} / {rng}: {v}")
                        continue
                    self.rules.append(Rule(speaker, listener, v, *bounds))
            elif "/" in (value or ""):
                self.rules.append(Rule(speaker, listener, value))
            elif value:
                print(f"glossary.yaml: bỏ qua xưng hô sai định dạng (thiếu '/'): {key}: {value}")

    @property
    def pairs(self):
        return self.rules

    def entries_in(self, text):
        return [e for e in self.entries if e.pattern.search(text)]

    def rule_for(self, speaker, listener, chapter=None):
        """The xưng hô rule of one pair for this chapter (the narrowest range wins), or None."""
        best = None
        for r in self.rules:
            if r.speaker != speaker or r.listener != listener:
                continue
            if chapter is not None and ((r.lo and chapter < r.lo) or (r.hi and chapter > r.hi)):
                continue
            if best is None or r.width <= best.width:
                best = r
        return best

    def prompt_block(self, chunk_text, chapter_text, chapter=None, scene_text=None, always=()):
        """scene_text: the chunk plus the lines right before it; a xưng hô pair is sent only when both people
        are in that scene (names in `always`, e.g. the first-person narrator, always count as present)."""
        found = [e for e in self.entries if e.pattern.search(chapter_text if e.chapter_wide else chunk_text)]
        lines = [e.prompt_line() for e in found if not e.is_honorific]
        honorifics = [f"- {e.en} → {e.vi}" + (f" ({e.note})" if e.note else "") for e in found if e.is_honorific]
        out = []
        if lines:
            out.append("BẢNG THUẬT NGỮ (bắt buộc dùng đúng bản dịch):\n" + "\n".join(lines))
        if honorifics:
            out.append("KÍNH NGỮ / CÁCH GỌI (chọn theo quan hệ giữa hai người; lược bỏ nếu tiếng Việt tự nhiên hơn):\n"
                       + "\n".join(honorifics))
        # When ranges overlap ("151-" and "200"), the narrowest range wins for that pair.
        scene = (scene_text or chapter_text) + ("\n" + " ".join(always) if always else "")
        chosen = {}
        for r in self.rules:
            if r.applies(chapter, scene):
                key = (r.speaker, r.listener)
                if key not in chosen or r.width <= chosen[key].width:
                    chosen[key] = r
        if chosen:
            out.append("XƯNG HÔ (bắt buộc cho mọi câu thoại giữa hai người này, kể cả lúc căng thẳng, nguy cấp, "
                       "giận dữ; chỉ cách gọi tên mới được linh hoạt, vd biệt danh khi riêng tư thân mật):\n"
                       + "\n".join(r.prompt_line() for r in chosen.values()))
        return "\n\n".join(out)

    def name_swaps(self, src, out):
        """Hard errors: a character named in the English is missing from the translation while another
        character, absent from the English, shows up instead (e.g. "Esther" rendered as "Cain")."""
        people = [e for e in self.entries if e.section == "nhan_vat"]
        errs = []
        for i, vi in out.items():
            en = src[i - 1]
            lost = [e for e in people if e.pattern.search(en) and not e.vi_pattern.search(vi)]
            if not lost:
                continue
            extra = [e for e in people if e.vi_pattern.search(vi) and not e.pattern.search(en)
                     and not any(e.vi in x.vi or x.vi in e.vi for x in lost)]
            if extra:
                errs.append(f"đoạn {i} đổi tên {lost[0].en} thành {extra[0].vi}")
        return errs

    def misses(self, en, vi):
        """Glossary terms present in the source paragraph whose translation is absent from the output.
        "thầy / cô (tùy giới tính)" counts as present when either alternative appears."""
        low = vi.lower()
        out = []
        for e in self.entries_in(en):
            if e.is_honorific:
                continue
            alts = [re.sub(r"\(.*?\)", "", a).strip().lower() for a in e.vi.split("/")]
            if not any(a and a in low for a in alts):
                out.append(e)
        return out


def term_pattern(term):
    """Whole-word match. Word boundaries only on sides that are letters, so a suffix entry such as
    "-nim" still matches inside "Frondier-nim". All-lowercase terms match case-insensitively."""
    left = r"(?<!\w)" if re.match(r"\w", term) else ""
    right = r"(?!\w)" if re.search(r"\w$", term) else ""
    flags = 0 if any(c.isupper() for c in term) else re.I
    return re.compile(left + re.escape(term) + right, flags)


def _mentions(name, text):
    return term_pattern(name).search(text) is not None
