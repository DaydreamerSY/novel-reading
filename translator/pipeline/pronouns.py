"""Checks a Vietnamese dialogue line against a xưng hô rule (self-reference / form of address).

Shared by the translator (to re-translate a line that breaks its pair's rule) and the audit. Pronouns may be
dropped, which is natural in Vietnamese; a line is wrong only when another first-person word or another form of
address shows up instead of the required one.
"""
import re

# Clear first-person words. "mình" is left out: it is just as often reflexive ("themselves").
FIRST = ["tôi", "ta", "tớ", "tao", "tui"]
ADDRESS = ["ngươi", "cậu chủ", "cậu", "anh", "em", "cô", "chị", "ông", "bà", "mày", "ngài", "bệ hạ", "điện hạ",
           "chủ nhân", "tiền bối", "thầy", "con", "nàng", "hiệu trưởng", "công chúa", "phu nhân", "chỉ huy"]
# Third-person and plural phrases ("anh ta", "chúng ta", "các ngươi"), dropped before looking for pronouns.
NOISE = re.compile(r"(?<!\w)(?:chúng|bọn|các|anh|cô|hắn|ông|bà|cậu|gã|y|nàng)\s+(?:ta|ấy|bé)(?!\w)"
                   r"|(?<!\w)(?:các|bọn|chúng|mọi)\s+\w+", re.I)
QUOTED = re.compile(r"[“\"«‘']([^”\"»’']+)[”\"»’']|^\s*[—–-]\s*(.+)$", re.M)


def has(word, text):
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text, re.I) is not None


def speech(vi):
    """The spoken part of a line (inside quotes / after a dash), or the whole line."""
    parts = [a or b for a, b in QUOTED.findall(vi)]
    return " ".join(parts) if parts else vi


def issues(rule, vi):
    """What in this line contradicts the rule, e.g. ['tự xưng "ta" thay vì "tôi"']."""
    s = NOISE.sub(" ", speech(vi))
    self_ref, address = rule.self_ref.lower(), rule.address.lower()
    out = []
    other_first = [f for f in FIRST if f != self_ref and has(f, s)]
    if other_first and not has(self_ref, s):
        out.append(f'tự xưng "{other_first[0]}" thay vì "{rule.self_ref}"')
    other_addr = [a for a in ADDRESS if a not in (address, self_ref) and a not in address and has(a, s)]
    if other_addr and not has(address, s):
        out.append(f'gọi "{other_addr[0]}" thay vì "{rule.address}"')
    return out


def status(rule, vi):
    """'sai' (breaks the rule), 'dung' (uses the rule's words) or 'luoc' (pronouns dropped)."""
    if issues(rule, vi):
        return "sai"
    s = NOISE.sub(" ", speech(vi))
    return "dung" if has(rule.self_ref, s) or has(rule.address, s) else "luoc"


def fix_self(rule, vi):
    """Last resort for a line that keeps the wrong self-reference after every retry: swap that word for the
    rule's, inside the spoken part only. Returns the new line, or None when there is nothing safe to change.
    (The form of address is never swapped: "cô", "anh"... may as well be about a third person.)"""
    wrong = [f for f in FIRST if f != rule.self_ref.lower()]
    changed = False

    def fix_part(part):
        nonlocal changed
        protected = {m.span() for m in NOISE.finditer(part)}

        def one(m):
            nonlocal changed
            if any(a <= m.start() < b for a, b in protected):
                return m.group(0)
            changed = True
            new = rule.self_ref
            return new[:1].upper() + new[1:] if m.group(0)[:1].isupper() else new
        return re.sub(r"(?<!\w)(?:" + "|".join(map(re.escape, wrong)) + r")(?!\w)", one, part, flags=re.I)

    out = QUOTED.sub(lambda m: m.group(0).replace(m.group(1) or m.group(2), fix_part(m.group(1) or m.group(2))), vi)
    if not changed and not QUOTED.search(vi):
        out = fix_part(vi)
    return out if changed and not issues(rule, out) else None
