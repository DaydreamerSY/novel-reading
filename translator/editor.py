"""Local web editor for glossary.yaml:  python novel.py edit

Serves editor.html on http://127.0.0.1:<port>. The page shows every term from data/terms.json
merged with the current glossary.yaml, grouped so that variants of the same thing sit together
("Empire" / "Terst Empire", "Shadow Unit" / "Empire Shadow Unit", "Shadow Transfer" /
"Shadow Transference"), with honorifics and titles in a group of their own. Saving rewrites
glossary.yaml; the previous version is kept as glossary.yaml.bak.
"""
import json
import os
import re
import shutil
import webbrowser
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import combinations

import yaml

from common import ROOT, read_json, write_json
from glossary import LABELS, Glossary

GLOSSARY = ROOT / "glossary.yaml"
TERMS = ROOT / "data" / "terms.json"
STATE = ROOT / "data" / "editor_state.json"
PAGE = ROOT / "editor.html"
SECTIONS = ["nhan_vat", "kinh_ngu", "danh_hieu", "dia_danh", "to_chuc", "vu_khi", "ky_nang", "vat_pham",
            "chung_toc", "thuat_ngu"]
TITLE_SECTIONS = {"kinh_ngu", "danh_hieu"}
FIELDS = ("vi", "gioitinh", "ngoi3", "ghichu")
DEFAULT_HEADER = ["# BẢNG THUẬT NGỮ. Sửa bằng công cụ: python novel.py edit"]
XUNG_HO_HELP = [
    '# XƯNG HÔ: "Người nói > Người nghe": "tự xưng / gọi người nghe"',
    "# Được gửi kèm khi cả hai tên cùng xuất hiện trong chương.",
    '# Quan hệ thay đổi theo truyện thì chia theo khoảng chương ("151-" = từ chương 151 trở đi):',
    '#   "A > B":',
    '#     "1-150": "tôi / cô"',
    '#     "151-": "anh / em"',
]


# ---------------------------------------------------------------- reading

def read_glossary():
    """(entries by name, xưng hô rules, leading comment block) of the current glossary.yaml."""
    if not GLOSSARY.exists():
        return {}, [], DEFAULT_HEADER
    text = GLOSSARY.read_text(encoding="utf-8")
    header = []
    for line in text.splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            break
        header.append(line)
    while header and not header[-1].strip():
        header.pop()
    data = yaml.load(text, Loader=yaml.BaseLoader) or {}
    entries, rules = {}, []
    for section, items in data.items():
        if not isinstance(items, dict):
            continue
        if section == "xung_ho":
            for key, value in items.items():
                if ">" not in key:
                    continue
                a, b = (s.strip() for s in key.split(">", 1))
                for rng, v in (value.items() if isinstance(value, dict) else [("", value)]):
                    self_ref, _, address = (v or "").partition("/")
                    rules.append({"speaker": a, "listener": b, "range": rng.strip(),
                                  "self": self_ref.strip(), "addr": address.strip()})
            continue
        for name, v in items.items():
            e = {k: ((v.get(k) if isinstance(v, dict) else (v if k == "vi" else "")) or "").strip() for k in FIELDS}
            entries[name.strip()] = dict(e, section=section)
    return entries, rules, header or DEFAULT_HEADER


def load():
    terms = read_json(TERMS) if TERMS.exists() else {"terms": [], "pairs": []}
    entries, rules, _ = read_glossary()
    state = read_json(STATE) if STATE.exists() else {}
    seen = set(state.get("seen", []))

    items = []
    for t in terms["terms"]:
        item = {k: t[k] for k in ("name", "count", "first", "last", "he", "she", "mota", "warn")}
        item["suggest"] = t["loai"]
        e = entries.pop(t["name"], None)
        if e:  # already in glossary.yaml: the user's values win
            item.update(e, included=True, new=False)
        else:
            loai = t["loai"] if t["loai"] in SECTIONS or t["loai"] == "khong_phai" else "thuat_ngu"
            # the model's description stays a hint (shown under the name); only notes the user
            # writes or confirms go into the prompt
            item.update(section=loai, vi=t["vi"], gioitinh=t["gioitinh"], ngoi3="", ghichu="",
                        included=t["name"] not in seen and loai != "khong_phai" and t["loai"] != "chua_phan_loai",
                        new=bool(seen) and t["name"] not in seen)
        items.append(item)
    for name, e in entries.items():  # added by hand, unknown to terms.json
        items.append(dict(e, name=name, count=0, first=0, last=0, he=0, she=0, mota="", warn="",
                          suggest="", included=True, new=False))
    groups = group(items)
    for k, g in enumerate(groups):
        g["id"] = f"g{k}"
    return {
        "items": items, "groups": groups, "rules": rules + state.get("draft_rules", []),
        "pairs": terms.get("pairs", []),
        "sections": [[k, LABELS.get(k, k)] for k in SECTIONS] + [["khong_phai", "không phải tên riêng"]],
        "reviewed": state.get("reviewed", []), "chapters": terms.get("chapters"),
    }


# ---------------------------------------------------------------- grouping

def _words(name):
    out = []
    for w in re.findall(r"[a-z0-9]+", name.lower().replace("’", "'")):
        if w in ("the", "of", "a", "an"):
            continue
        out.append(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith(("ss", "us", "is")) else w)
    return out


def _contains(long, short):
    return any(long[i:i + len(short)] == short for i in range(len(long) - len(short) + 1))


def _related(a, b, both_people):
    """Same thing written differently? a, b: normalised word lists."""
    if not a or not b:
        return False
    if a == b:
        return True
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    if len(short) < len(long) and _contains(long, short):
        # "Shadow Unit" in "Empire Shadow Unit"; "Empire" as the head of "Terst Empire";
        # a first or family name inside a full name. Not "Empire" in "Empire Shadow Unit".
        return len(short) >= 2 or long[-1] == short[0] or both_people
    if len(a) == len(b):
        diff = [(x, y) for x, y in zip(a, b) if x != y]
        if len(diff) == 1:  # "Shadow Transfer" / "Shadow Transference"
            x, y = diff[0]
            p = os.path.commonprefix([x, y])
            return len(p) >= 5 and len(p) >= min(len(x), len(y)) - 1
    return False


def group(items):
    """Ordered groups: honorifics & titles, then clusters of variants, then the rest per section."""
    words = [_words(it["name"]) for it in items]
    titles = [i for i, it in enumerate(items) if it["section"] in TITLE_SECTIONS]
    title_keys = {tuple(words[i]) for i in titles}
    in_titles = set(titles) | {i for i, it in enumerate(items)
                               if it["section"] != "khong_phai" and tuple(words[i]) in title_keys}
    junk = [i for i, it in enumerate(items) if it["section"] == "khong_phai" and i not in in_titles]
    rest = [i for i in range(len(items)) if i not in in_titles and i not in set(junk)]

    parent = {i: i for i in rest}

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a, b in combinations(rest, 2):
        people = items[a]["section"] == items[b]["section"] == "nhan_vat"
        if _related(words[a], words[b], people):
            parent[find(a)] = find(b)
    clusters = defaultdict(list)
    for i in rest:
        clusters[find(i)].append(i)

    def by_count(ids):
        return sorted(ids, key=lambda i: (-items[i]["count"], items[i]["name"]))

    out = []
    if in_titles:
        # keep variants next to their title: "Zodiac" then "Zodiacs"
        order = sorted(in_titles, key=lambda i: (-max(items[j]["count"] for j in in_titles if words[j] == words[i]),
                                                  tuple(words[i]), -items[i]["count"]))
        out.append({"kind": "title", "label": "Kính ngữ & chức danh", "members": order})
    dups = [by_count(ids) for ids in clusters.values() if len(ids) > 1]
    dups.sort(key=lambda ids: -sum(items[i]["count"] for i in ids))
    out += [{"kind": "dup", "label": items[ids[0]]["name"], "members": ids} for ids in dups]
    singles = defaultdict(list)
    for ids in clusters.values():
        if len(ids) == 1:
            singles[items[ids[0]]["section"]].append(ids[0])
    for sec in SECTIONS + sorted(set(singles) - set(SECTIONS)):
        if singles.get(sec):
            out.append({"kind": "single", "label": f"{LABELS.get(sec, sec).capitalize()} (không trùng)",
                        "members": by_count(singles[sec])})
    if junk:
        out.append({"kind": "junk", "label": "Model cho là không phải tên riêng", "members": by_count(junk)})
    return out


# ---------------------------------------------------------------- writing

def dump(items, rules, header):
    def q(s):
        return json.dumps(s, ensure_ascii=False)

    by = defaultdict(list)
    for it in items:
        if it.get("included") and it.get("name", "").strip():
            by[it.get("section")].append(it)
    lines = list(header)
    for sec in SECTIONS + sorted(k for k in by if k not in SECTIONS and k != "khong_phai"):
        lines += ["", f"{sec}:"]
        for it in sorted(by.get(sec, []), key=lambda x: (-int(x.get("count") or 0), x["name"])):
            name = it["name"].strip()
            note = f"  # {it['count']} lần" if it.get("count") else ""
            vals = {k: (it.get(k) or "").strip() for k in FIELDS}
            if sec == "nhan_vat" or any(vals[k] for k in ("gioitinh", "ngoi3", "ghichu")):
                lines.append(f"  {q(name)}:{note}")
                lines.append(f"    vi: {q(vals['vi'])}")
                for k in ("gioitinh", "ngoi3", "ghichu"):
                    if sec == "nhan_vat" or vals[k]:
                        lines.append(f"    {k}: {q(vals[k])}")
            else:
                lines.append(f"  {q(name)}: {q(vals['vi'])}{note}")

    lines += [""] + XUNG_HO_HELP + ["xung_ho:"]
    pairs = defaultdict(list)
    for r in rules:
        a, b = (r.get("speaker") or "").strip(), (r.get("listener") or "").strip()
        s, t = (r.get("self") or "").strip(), (r.get("addr") or "").strip()
        if a and b and s and t:
            pairs[(a, b)].append((((r.get("range") or "").strip()), f"{s} / {t}"))
    for (a, b), rs in pairs.items():
        if len(rs) == 1 and not rs[0][0]:
            lines.append(f"  {q(f'{a} > {b}')}: {q(rs[0][1])}")
        else:
            lines.append(f"  {q(f'{a} > {b}')}:")
            lines += [f"    {q(rng or '1-')}: {q(v)}" for rng, v in rs]
    return "\n".join(lines) + "\n"


def _complete(r):
    return all((r.get(k) or "").strip() for k in ("speaker", "listener", "self", "addr"))


def save(payload):
    _, _, header = read_glossary()
    rules = payload.get("rules", [])
    text = dump(payload["items"], rules, header)
    yaml.load(text, Loader=yaml.BaseLoader)  # refuse to write anything that would not load
    if GLOSSARY.exists():
        shutil.copy2(GLOSSARY, GLOSSARY.with_name("glossary.yaml.bak"))
    tmp = GLOSSARY.with_name("glossary.yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, GLOSSARY)
    # unfinished xưng hô rows cannot go into glossary.yaml; keep them for the next session
    drafts = [r for r in rules if not _complete(r) and any((r.get(k) or "").strip() for k in r)]
    write_json(STATE, {"seen": [it["name"] for it in payload["items"]], "reviewed": payload.get("reviewed", []),
                       "draft_rules": drafts})
    g = Glossary(GLOSSARY)
    return {"ok": True, "entries": len(g.entries), "rules": len(g.rules), "draft_rules": len(drafts)}


# ---------------------------------------------------------------- server

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/data":
            self._json(load())
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/save":
            return self._send(404, b"not found", "text/plain")
        try:
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            self._json(save(payload))
        except Exception as e:  # report to the page instead of dropping the connection
            self._json({"ok": False, "error": repr(e)}, 500)

    def log_message(self, *args):
        pass


def serve(port, open_browser):
    if not TERMS.exists():
        print("Chưa có data/terms.json, hãy chạy: python novel.py terms")
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}/"
    print(f"Công cụ glossary: {url}  (Ctrl+C để tắt)", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
