"""Download the free English chapters from novelight.net into data/en_novelight/NNNN.json.

The site numbers chapters like the Korean original ("0" prologue, "1.1"/"1.2" for the two halves of
chapter 1, ..., "607" side stories), so files are numbered by reading order (0001 = prologue) and keep
the site's label. Locked (paid) chapters are skipped. Chapters download in parallel threads, with a
shared rate limit so the whole pool never sends more than one request per `min_interval` seconds.
Raw responses are kept in data/cache/novelight/, so `--force` re-parses without downloading again.
"""
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from bs4 import BeautifulSoup

from common import available, chapter_path, read_json, write_json
from scraper import JUNK, USER_AGENT, Blocked

LABEL = re.compile(r"^\s*(\d+)(?:\.(\d+))?\s+chapter\s*-\s*(.*)$", re.I)
# The site stamps its name into sentences: in "mathematical bold" letters ("an ★ 𝐍... ★ event"), or spelled
# out between brackets ("[N O V E L I G H T]", "{N•o•v•e•l•i•g•h•t}", "«N.o.v.e.l.i.g.h.t»").
_NAME = r"n\W{0,2}[o0]\W{0,2}v\W{0,2}[e3]\W{0,2}l\W{0,2}[i1]\W{0,2}g\W{0,2}h\W{0,2}t(?:\W{0,2}net)?"
STAMP = re.compile("\\s*[★☆✦✧]*\\s*(?:[\U0001D400-\U0001D7FF][\U0001D400-\U0001D7FF\\s.]*"
                   r"|[\[{(«<【]\s*" + _NAME + r"\s*[\]})»>】]|" + _NAME + ")"
                   "\\s*[★☆✦✧]*\\s*", re.I)
# Fan translator's notes: inline "[T/N: ...]" and whole lines. Kept in "tl_notes", not translated.
TN_INLINE = re.compile(r"\s*\[\s*(?:T/?N|TL ?Note)\s*:?([^\]]*)\]", re.I)
NOTE_LINE = re.compile(r"^\s*(?:T/?N|TL ?Note)\s*:|mass release|catch up to (?:the )?previous translator"
                       r"|chapters will be released", re.I)


class Client:
    """One requests.Session per thread, a pool-wide minimum gap between requests,
    and a pool-wide pause after HTTP 429."""

    def __init__(self, base, min_interval):
        self.base = base
        self.min_interval = min_interval
        self.local = threading.local()
        self.lock = threading.Lock()
        self.next_at = 0.0
        self.stop = threading.Event()

    def _session(self):
        s = getattr(self.local, "s", None)
        if s is None:
            s = self.local.s = requests.Session()
            s.headers["User-Agent"] = USER_AGENT
        return s

    def _wait_turn(self):
        with self.lock:
            now = time.monotonic()
            at = max(now, self.next_at)
            self.next_at = at + self.min_interval
        time.sleep(at - now)

    def _backoff(self, seconds):
        with self.lock:
            self.next_at = max(self.next_at, time.monotonic() + seconds)

    def get(self, path, ajax=False, referer=None, **params):
        headers = {"X-Requested-With": "XMLHttpRequest"} if ajax else {}
        if referer:
            headers["Referer"] = self.base + referer
        err = None
        for attempt in range(4):
            if self.stop.is_set():
                raise Blocked("đã dừng")
            self._wait_turn()
            try:
                r = self._session().get(self.base + path, params=params or None, headers=headers, timeout=30)
            except requests.RequestException as e:
                err = e
            else:
                if r.status_code == 200:
                    return r
                low = r.text[:5000].lower()
                if r.status_code in (403, 503) and ("challenge" in low or "captcha" in low or "cf-chl" in low):
                    self.stop.set()
                    raise Blocked(f"HTTP {r.status_code}: trang yêu cầu xác minh chống bot")
                err = f"HTTP {r.status_code}"
                if r.status_code in (401, 402, 403, 404):
                    break
                if r.status_code == 429:
                    self._backoff(60)
            time.sleep(3 * 2 ** attempt)
        raise RuntimeError(f"{path}: {err}")


def sort_key(label):
    major, _, part = label.partition(".")
    return int(major), int(part or 0)


def fetch_index(client, book):
    """All chapters listed on the book page (free and locked), in reading order."""
    page = client.get(f"/book/{book}").text
    m = re.search(r'const\s+BOOK_ID\s*=\s*"(\d+)"', page)
    if not m:
        raise RuntimeError("Không tìm thấy BOOK_ID trên trang truyện")
    book_id = m.group(1)
    pages = [int(v) for v in re.findall(r'<option value="(\d+)"', page)] or [1]
    items = {}
    for p in sorted(set(pages)):
        html = client.get("/book/ajax/chapter-pagination", ajax=True, referer=f"/book/{book}",
                          book_id=book_id, page=p).json()["html"]
        for a in BeautifulSoup(html, "lxml").select("a.chapter[href]"):
            title = " ".join(a.select_one(".title").get_text(" ").split()) if a.select_one(".title") else ""
            lm = LABEL.match(title)
            if not lm:
                print(f"  bỏ qua mục không rõ số chương: {title!r}")
                continue
            label = lm.group(1) + (f".{lm.group(2)}" if lm.group(2) else "")
            cid = int(a["href"].rstrip("/").rsplit("/", 1)[-1])
            items[cid] = {"id": cid, "label": label, "name": lm.group(3).strip(), "title": title,
                          "locked": a.select_one(".fa-lock") is not None}
    ordered = []
    for it in sorted(items.values(), key=lambda it: (sort_key(it["label"]), it["id"])):
        # The same chapter uploaded twice in a row ("554 Niflheim (6)" then "555 Niflheim (6)"):
        # keep the later upload, which carries the right label.
        if ordered and ordered[-1]["name"] == it["name"]:
            dup = ordered.pop()
            print(f"  bỏ bản đăng trùng: {dup['label']} {dup['name']} (id {dup['id']}), giữ {it['label']} (id {it['id']})")
        ordered.append(it)
    for n, it in enumerate(ordered, 1):
        it["number"] = n
    return book_id, ordered


def _heading(name):
    """'The Human Sloth Frondier (1) Part 1' -> 'the human sloth frondier (1)' for matching the in-text heading."""
    return re.sub(r"\s*part\s*\d+\s*$", "", name, flags=re.I).strip().lower()


def parse_content(data, item, base):
    soup = BeautifulSoup(data.get("content") or "", "lxml")
    cls = data.get("class")
    box = soup.select_one(f".{cls}") if cls else None
    if box is None:
        box = soup.select_one(".chapter-text")
    if box is None:
        return None
    paragraphs, dropped, notes = [], 0, []
    for el in box.find_all(recursive=False):
        if el.name in ("script", "style", "ins") or "advertisment" in (el.get("class") or []):
            continue
        for junk in el.find_all(["script", "style", "ins"]):
            junk.decompose()
        raw = " ".join(el.get_text(" ").split())
        text = STAMP.sub(" ", raw)
        for m in TN_INLINE.finditer(text):
            notes.append({"paragraph": len(paragraphs), "text": m.group(1).strip()})
        text = re.sub(r"\s+([,.!?;:])", r"\1", " ".join(TN_INLINE.sub(" ", text).split()))
        if text and NOTE_LINE.search(text):
            notes.append({"paragraph": len(paragraphs), "text": text})
            text = ""
        if not text or JUNK.search(text):
            if raw:
                dropped += 1
            continue
        paragraphs.append(text)
    # The first line repeats the chapter heading ("The Human Sloth Frondier (1)"); the title keeps it.
    if paragraphs and _heading(paragraphs[0]).strip(" .") == _heading(item["name"]).strip(" ."):
        paragraphs.pop(0)
    if not paragraphs:
        return None
    return {"number": item["number"], "label": item["label"], "title": item["title"],
            "paragraphs": paragraphs, "dropped_lines": dropped, "tl_notes": notes, "source": "novelight",
            "source_id": item["id"], "url": f"{base}/book/chapter/{item['id']}"}


def download(client, item, out, raw_dir):
    cid = item["id"]
    raw = raw_dir / f"{cid}.json"
    if raw.exists():
        data = read_json(raw)
    else:
        r = client.get(f"/book/ajax/read-chapter/{cid}", ajax=True, referer=f"/book/chapter/{cid}")
        try:
            data = r.json()
        except ValueError:
            return None
        write_json(raw, data)
    ch = parse_content(data, item, client.base)
    if ch is not None:
        write_json(out, ch)
    return ch


def scrape(cfg, paths, chapters=None, workers=None, force=False):
    sc = cfg.get("novelight", {})
    base = sc.get("base_url", "https://novelight.net").rstrip("/")
    book = sc.get("book", "the-academys-weapon-replicatorreplikator-iz-akademii-novella")
    workers = int(workers or sc.get("workers", 4))
    client = Client(base, float(sc.get("min_interval", 0.3)))
    folder = paths.en_novelight
    raw_dir = paths.cache / "novelight"

    print("Đang đọc mục lục...")
    book_id, index = fetch_index(client, book)
    write_json(folder / "_index.json", {"book_id": book_id, "base_url": base, "book": book, "chapters": index})
    free = [it for it in index if not it["locked"]]
    locked = [it for it in index if it["locked"]]
    # Numbers shift when the site's list changes: a file whose source_id no longer matches its number
    # is removed and rebuilt below (from the raw cache, no download).
    by_number = {it["number"]: it for it in free}
    stale = [n for n in available(folder)
             if n not in by_number or read_json(chapter_path(folder, n)).get("source_id") != by_number[n]["id"]]
    for n in stale:
        chapter_path(folder, n).unlink()
    if stale:
        print(f"Mục lục đã đổi: dựng lại {len(stale)} file lệch số ({stale[0]}–{stale[-1]})")
    print(f"Mục lục: {len(index)} chương, {len(free)} miễn phí, {len(locked)} bị khoá"
          + (f" ({locked[0]['label']} → {locked[-1]['label']}, bỏ qua)" if locked else ""))

    wanted = set(chapters) if chapters else None
    todo = [it for it in free
            if (wanted is None or it["number"] in wanted)
            and (force or not chapter_path(folder, it["number"]).exists())]
    if not todo:
        print("Không còn chương nào cần tải.")
        return
    print(f"Tải {len(todo)} chương với {workers} luồng...")

    saved, failed, empty, t0 = 0, [], [], time.monotonic()
    pool = ThreadPoolExecutor(max_workers=workers)
    futures = {pool.submit(download, client, it, chapter_path(folder, it["number"]), raw_dir): it for it in todo}
    try:
        for i, fut in enumerate(as_completed(futures), 1):
            it = futures[fut]
            try:
                ch = fut.result()
            except Blocked as e:
                print(f"Dừng: {e}. Hãy thử lại sau, không vượt chặn.")
                break
            except Exception as e:  # noqa: BLE001 - report and keep going with the others
                failed.append(it["number"])
                print(f"  [{it['number']:04d}] {it['label']}: lỗi {e}")
                continue
            if ch is None:
                empty.append(it["number"])
                print(f"  [{it['number']:04d}] {it['label']}: không có nội dung")
                continue
            saved += 1
            if i % 25 == 0 or i == len(todo):
                rate = i / max(time.monotonic() - t0, 1e-6)
                print(f"  {i}/{len(todo)} ({rate:.1f} chương/s), vừa xong {it['label']} "
                      f"– {len(ch['paragraphs'])} đoạn" + (f", bỏ {ch['dropped_lines']} dòng rác" if ch["dropped_lines"] else ""))
    except KeyboardInterrupt:
        print("Đang dừng...")
        client.stop.set()
        raise
    finally:
        client.stop.set()
        pool.shutdown(wait=True, cancel_futures=True)

    print(f"Đã lưu {saved} chương vào {folder} ({time.monotonic() - t0:.0f}s)")
    if failed:
        print(f"Lỗi {len(failed)} chương (chạy lại lệnh để thử lại): {failed}")
    if empty:
        print(f"Không có nội dung {len(empty)} chương: {empty}")
    have = available(folder)
    print(f"Hiện có {len(have)}/{len(free)} chương miễn phí trong {folder}")


def _alias_pattern(mapping):
    """One regex for all variants, longest first, so "Ria Liss" wins over "Liss" and "Lirih" over "Liri".
    Hyphens count as edges: "P-Pielot", "Heukcheon-covered", "Atjie-nim"."""
    if not mapping:
        return None
    names = sorted(mapping, key=len, reverse=True)
    return re.compile(r"(?<!\w)(" + "|".join(re.escape(n) for n in names) + r")(?!\w)")


def build_source(cfg, paths):
    """Rebuild data/en from data/en_novelight, renaming the variant spellings listed in aliases.yaml,
    so analysis, glossary and translation see one name per character. data/en_novelight stays untouched."""
    import yaml

    from common import ROOT

    src, dst = paths.en_novelight, paths.en
    have = available(src)
    if not have:
        print(f"Chưa có chương nào trong {src}. Chạy: python novel.py scrape --source novelight")
        return
    foreign = [n for n in available(dst) if read_json(chapter_path(dst, n)).get("source") != "novelight"]
    if foreign:
        print(f"{dst} đang chứa {len(foreign)} chương không phải từ novelight. "
              f"Hãy chuyển chúng sang chỗ khác trước (vd data/novellunar/en), lệnh này sẽ không ghi đè.")
        return

    a_path = ROOT / "aliases.yaml"
    a = (yaml.safe_load(open(a_path, encoding="utf-8")) or {}) if a_path.exists() else {}
    every, late, start = a.get("doi_ten_moi_chuong") or {}, a.get("doi_ten") or {}, int(a.get("tu_chuong") or 1)
    # "theo_khoang": {"970-971": {May: Mei}} — names that are only safe to rename inside a chapter range
    ranged = []
    for key, table in (a.get("theo_khoang") or {}).items():
        lo, _, hi = str(key).partition("-")
        ranged.append((int(lo), int(hi or lo), table or {}))
    patterns = {}

    totals, every_table = {}, {}
    for n in have:
        ch = read_json(chapter_path(src, n))
        table = {**every, **(late if n >= start else {})}
        for lo, hi, extra in ranged:
            if lo <= n <= hi:
                table.update(extra)
        key = frozenset(table.items())
        if key not in patterns:
            patterns[key] = _alias_pattern(table)
        pat = patterns[key]
        every_table.update(table)
        used = {}

        def rename(text):
            if pat is None:
                return text

            def one(m):
                used[m.group(1)] = used.get(m.group(1), 0) + 1
                return table[m.group(1)]
            return pat.sub(one, text)

        m = LABEL.match(ch["title"])
        name = m.group(3).strip() if m else ch["title"]
        out = {"number": n, "title": rename(name), "label": ch["label"],
               "paragraphs": [rename(p) for p in ch["paragraphs"]],
               "source": "novelight", "source_id": ch["source_id"], "url": ch["url"]}
        if used:
            out["aliases"] = used
        if ch.get("tl_notes"):
            out["tl_notes"] = ch["tl_notes"]
        write_json(chapter_path(dst, n), out)
        for k, v in used.items():
            totals[k] = totals.get(k, 0) + v

    stale = [n for n in available(dst) if n not in set(have)]
    for n in stale:
        chapter_path(dst, n).unlink()
    print(f"Đã dựng {len(have)} chương vào {dst} từ {src}" + (f", xoá {len(stale)} file thừa" if stale else ""))
    if totals:
        print("Đổi tên theo aliases.yaml: " + ", ".join(
            f"{k} → {every_table[k]} ({v})" for k, v in sorted(totals.items(), key=lambda kv: -kv[1])))
