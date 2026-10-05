"""Download English chapters from novellunar.com into data/en/NNNN.json."""
import re
import time

import requests
from bs4 import BeautifulSoup

from common import chapter_path, write_json

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")

# Watermark lines injected by aggregators, and the fan translator's end-of-chapter notes.
JUNK = re.compile(
    r"n[o0]v[e3]l\W{0,2}b[i1]n|novellunar|freewebnovel|lightnovelpub|lightnovelworld"
    r"|\bwww\.|\.(com|net|org|me)\b"
    r"|review this novel|bonus chapters? on reaching|^happy reading\W*$",
    re.I,
)
TITLE = re.compile(r"chapter\s*\d+", re.I)


class Blocked(Exception):
    pass


def _join(pieces):
    """Sentence spans of one paragraph. A span with no letters (a lone closing or opening quote, "...")
    sticks to its neighbour; two sentences get a space."""
    out = ""
    for p in pieces:
        out += (" " if re.search(r"\w", out) and re.search(r"\w", p) else "") + p
    return out


def parse_chapter(html, n):
    soup = BeautifulSoup(html, "lxml")
    box = soup.select_one("article > div.text-gray-800")
    if box is None:
        return None
    # The site wraps every sentence in its own span and marks paragraph breaks with an empty span,
    # so a closing quote can be a span of its own: group spans between separators into paragraphs.
    groups, cur = [], []
    for el in box.find_all("span", recursive=False):
        text = " ".join(el.get_text(" ").split())
        if "transition-all" in (el.get("class") or []):
            if text:
                cur.append(text)
        elif not text and cur:
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    paragraphs, dropped = [], 0
    for pieces in groups:
        text = _join(pieces)
        if JUNK.search(text):
            dropped += 1
            continue
        paragraphs.append(text)
    if not paragraphs:
        return None
    title = next((h.get_text(" ", strip=True) for h in soup.find_all("h1")
                  if TITLE.match(h.get_text(strip=True))), f"Chapter {n}")
    return {"number": n, "title": title, "paragraphs": paragraphs, "dropped_lines": dropped}


def fetch(session, url):
    err = None
    for attempt in range(4):
        try:
            r = session.get(url, timeout=30)
        except requests.RequestException as e:
            err = e
        else:
            if r.status_code == 200:
                return r.text
            if r.status_code in (403, 503) and ("challenge" in r.text.lower() or "captcha" in r.text.lower()):
                raise Blocked(f"HTTP {r.status_code}: trang yêu cầu xác minh chống bot")
            err = f"HTTP {r.status_code}"
            if r.status_code == 429:
                time.sleep(60)
        time.sleep(5 * 2 ** attempt)
    raise RuntimeError(f"Không tải được {url}: {err}")


def scrape(cfg, paths, chapters, open_ended, force):
    """Download chapters; when open_ended, keep going until the site has no more chapters."""
    sc = cfg["source"]
    base, slug, delay = sc["base_url"].rstrip("/"), sc["slug"], float(sc["delay_seconds"])
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    saved, empty_streak = 0, 0
    n_iter = iter(chapters)
    while True:
        n = next(n_iter, None)
        if n is None:
            break
        out = chapter_path(paths.en, n)
        if out.exists() and not force:
            continue
        url = f"{base}/novel/{slug}/chapter/{n}"
        try:
            ch = fetch(session, url)
        except Blocked as e:
            print(f"Dừng ở chương {n}: {e}. Hãy thử lại sau, không vượt chặn.")
            break
        ch = parse_chapter(ch, n)
        if ch is None:
            empty_streak += 1
            print(f"Chương {n}: không có nội dung")
            if open_ended and empty_streak >= 2:
                print("Có vẻ đã hết truyện.")
                break
        else:
            empty_streak = 0
            ch["url"] = url
            write_json(out, ch)
            saved += 1
            note = f", bỏ {ch['dropped_lines']} dòng rác" if ch["dropped_lines"] else ""
            print(f"Chương {n}: {len(ch['paragraphs'])} đoạn, {sum(map(len, ch['paragraphs']))} ký tự{note}")
        time.sleep(delay)
    print(f"Đã lưu {saved} chương vào {paths.en}")
